// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title CSIDataRegistry
 * @dev CSIデータのIPFS CIDをブロックチェーンに記録するスマートコントラクト
 * @notice このコントラクトはCSIデータの透明性と改ざん防止を提供します
 */
contract CSIDataRegistry {

    // ===== 構造体定義 =====

    /**
     * @dev CSIデータレコード構造体
     */
    struct CSIDataRecord {
        string deviceId;           // デバイスID
        string ipfsCid;            // IPFS CID（combined_hash）
        string metadataHash;       // メタデータのIPFS CID
        uint256 timestamp;         // 記録時刻（Unixタイムスタンプ）
        address recorder;          // 記録者のアドレス
        bool exists;               // レコード存在フラグ
    }

    // ===== 状態変数 =====

    // CID → CSIDataRecord のマッピング
    mapping(string => CSIDataRecord) private cidToRecord;

    // デバイスID → CIDリスト のマッピング
    mapping(string => string[]) private deviceToCids;

    // 全CIDリスト（オプション：全データ参照用）
    string[] private allCids;

    // コントラクトオーナー
    address public owner;

    // 記録者ホワイトリスト（アクセス制御用）
    mapping(address => bool) public authorizedRecorders;

    // ===== イベント定義 =====

    /**
     * @dev CSIデータが記録された際に発行されるイベント
     */
    event CSIDataRecorded(
        string indexed deviceId,
        string ipfsCid,
        string metadataHash,
        uint256 timestamp,
        address indexed recorder
    );

    /**
     * @dev 記録者が追加された際のイベント
     */
    event RecorderAuthorized(address indexed recorder, address indexed authorizer);

    /**
     * @dev 記録者が削除された際のイベント
     */
    event RecorderRevoked(address indexed recorder, address indexed revoker);

    // ===== 修飾子 =====

    /**
     * @dev オーナーのみ実行可能
     */
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    /**
     * @dev 認可された記録者のみ実行可能
     */
    modifier onlyAuthorizedRecorder() {
        require(
            authorizedRecorders[msg.sender] || msg.sender == owner,
            "Not authorized to record data"
        );
        _;
    }

    // ===== コンストラクタ =====

    /**
     * @dev コンストラクタ：デプロイ者をオーナーとして設定
     */
    constructor() {
        owner = msg.sender;
        authorizedRecorders[msg.sender] = true;
        emit RecorderAuthorized(msg.sender, msg.sender);
    }

    // ===== メイン機能 =====

    /**
     * @dev CSIデータのCIDをブロックチェーンに記録
     * @param deviceId デバイスID
     * @param ipfsCid IPFS CID（combined_hash）
     * @param metadataHash メタデータのIPFS CID
     * @return bool 記録成功フラグ
     */
    function recordCSIData(
        string memory deviceId,
        string memory ipfsCid,
        string memory metadataHash
    ) public onlyAuthorizedRecorder returns (bool) {
        // 入力バリデーション
        require(bytes(deviceId).length > 0, "Device ID cannot be empty");
        require(bytes(ipfsCid).length > 0, "IPFS CID cannot be empty");
        require(bytes(metadataHash).length > 0, "Metadata hash cannot be empty");

        // 重複チェック
        require(!cidToRecord[ipfsCid].exists, "CID already recorded");

        // レコード作成
        CSIDataRecord memory newRecord = CSIDataRecord({
            deviceId: deviceId,
            ipfsCid: ipfsCid,
            metadataHash: metadataHash,
            timestamp: block.timestamp,
            recorder: msg.sender,
            exists: true
        });

        // マッピングに保存
        cidToRecord[ipfsCid] = newRecord;
        deviceToCids[deviceId].push(ipfsCid);
        allCids.push(ipfsCid);

        // イベント発行
        emit CSIDataRecorded(
            deviceId,
            ipfsCid,
            metadataHash,
            block.timestamp,
            msg.sender
        );

        return true;
    }

    /**
     * @dev CIDからCSIデータ情報を取得
     * @param ipfsCid IPFS CID
     * @return CSIDataRecord データレコード
     */
    function getCSIDataByCID(string memory ipfsCid)
        public
        view
        returns (CSIDataRecord memory)
    {
        require(cidToRecord[ipfsCid].exists, "CID not found");
        return cidToRecord[ipfsCid];
    }

    /**
     * @dev デバイスIDから関連するCIDリストを取得
     * @param deviceId デバイスID
     * @return string[] CIDリスト
     */
    function getDeviceCIDs(string memory deviceId)
        public
        view
        returns (string[] memory)
    {
        return deviceToCids[deviceId];
    }

    /**
     * @dev デバイスIDから最新のCIDを取得
     * @param deviceId デバイスID
     * @return string 最新のCID
     */
    function getLatestDeviceCID(string memory deviceId)
        public
        view
        returns (string memory)
    {
        string[] memory cids = deviceToCids[deviceId];
        require(cids.length > 0, "No CIDs found for device");
        return cids[cids.length - 1];
    }

    /**
     * @dev デバイスの記録件数を取得
     * @param deviceId デバイスID
     * @return uint256 記録件数
     */
    function getDeviceRecordCount(string memory deviceId)
        public
        view
        returns (uint256)
    {
        return deviceToCids[deviceId].length;
    }

    /**
     * @dev CIDが記録されているか確認
     * @param ipfsCid IPFS CID
     * @return bool 存在フラグ
     */
    function cidExists(string memory ipfsCid) public view returns (bool) {
        return cidToRecord[ipfsCid].exists;
    }

    /**
     * @dev 全記録件数を取得
     * @return uint256 全記録件数
     */
    function getTotalRecordCount() public view returns (uint256) {
        return allCids.length;
    }

    /**
     * @dev ページネーション付きでCIDリストを取得
     * @param offset 開始位置
     * @param limit 取得件数
     * @return string[] CIDリスト
     */
    function getAllCIDsPaginated(uint256 offset, uint256 limit)
        public
        view
        returns (string[] memory)
    {
        require(offset < allCids.length, "Offset out of bounds");

        uint256 end = offset + limit;
        if (end > allCids.length) {
            end = allCids.length;
        }

        uint256 resultLength = end - offset;
        string[] memory result = new string[](resultLength);

        for (uint256 i = 0; i < resultLength; i++) {
            result[i] = allCids[offset + i];
        }

        return result;
    }

    // ===== アクセス制御機能 =====

    /**
     * @dev 記録者を認可リストに追加
     * @param recorder 認可する記録者のアドレス
     */
    function authorizeRecorder(address recorder) public onlyOwner {
        require(recorder != address(0), "Invalid recorder address");
        require(!authorizedRecorders[recorder], "Recorder already authorized");

        authorizedRecorders[recorder] = true;
        emit RecorderAuthorized(recorder, msg.sender);
    }

    /**
     * @dev 記録者を認可リストから削除
     * @param recorder 削除する記録者のアドレス
     */
    function revokeRecorder(address recorder) public onlyOwner {
        require(recorder != owner, "Cannot revoke owner");
        require(authorizedRecorders[recorder], "Recorder not authorized");

        authorizedRecorders[recorder] = false;
        emit RecorderRevoked(recorder, msg.sender);
    }

    /**
     * @dev アドレスが認可されているか確認
     * @param recorder 確認するアドレス
     * @return bool 認可フラグ
     */
    function isAuthorizedRecorder(address recorder) public view returns (bool) {
        return authorizedRecorders[recorder] || recorder == owner;
    }

    /**
     * @dev オーナー権限を移譲
     * @param newOwner 新オーナーのアドレス
     */
    function transferOwnership(address newOwner) public onlyOwner {
        require(newOwner != address(0), "Invalid new owner address");
        require(newOwner != owner, "New owner is the same as current owner");

        address oldOwner = owner;
        owner = newOwner;
        authorizedRecorders[newOwner] = true;

        emit RecorderAuthorized(newOwner, oldOwner);
    }

    // ===== バッチ処理機能 =====

    /**
     * @dev 複数のCSIデータを一括記録（ガスコスト最適化）
     * @param deviceIds デバイスIDの配列
     * @param ipfsCids IPFS CIDの配列
     * @param metadataHashes メタデータハッシュの配列
     * @return bool 記録成功フラグ
     */
    function batchRecordCSIData(
        string[] memory deviceIds,
        string[] memory ipfsCids,
        string[] memory metadataHashes
    ) public onlyAuthorizedRecorder returns (bool) {
        require(
            deviceIds.length == ipfsCids.length &&
            ipfsCids.length == metadataHashes.length,
            "Array lengths must match"
        );
        require(deviceIds.length > 0, "Empty arrays not allowed");
        require(deviceIds.length <= 50, "Batch size too large");

        for (uint256 i = 0; i < deviceIds.length; i++) {
            // 重複チェック
            if (!cidToRecord[ipfsCids[i]].exists) {
                // レコード作成
                CSIDataRecord memory newRecord = CSIDataRecord({
                    deviceId: deviceIds[i],
                    ipfsCid: ipfsCids[i],
                    metadataHash: metadataHashes[i],
                    timestamp: block.timestamp,
                    recorder: msg.sender,
                    exists: true
                });

                cidToRecord[ipfsCids[i]] = newRecord;
                deviceToCids[deviceIds[i]].push(ipfsCids[i]);
                allCids.push(ipfsCids[i]);

                emit CSIDataRecorded(
                    deviceIds[i],
                    ipfsCids[i],
                    metadataHashes[i],
                    block.timestamp,
                    msg.sender
                );
            }
        }

        return true;
    }

    // ===== ビューヘルパー関数 =====

    /**
     * @dev コントラクト情報を取得
     * @return address オーナーアドレス
     * @return uint256 総記録件数
     * @return uint256 デプロイ時のブロック番号（取得不可なのでダミー）
     */
    function getContractInfo()
        public
        view
        returns (
            address,
            uint256,
            uint256
        )
    {
        return (
            owner,
            allCids.length,
            block.number
        );
    }
}
