// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ZKProofRegistry
 * @dev ZKP証明のみをブロックチェーンに記録するスマートコントラクト
 * @notice プライバシー保護のため、元データではなく証明のみを保存
 */
contract ZKProofRegistry {

    // ===== 構造体定義 =====

    /**
     * @dev ZKP証明レコード構造体
     */
    struct ZKProofRecord {
        string deviceId;           // デバイスID
        string proofData;          // ZKP証明データ（JSON文字列）
        string publicSignals;      // 公開信号（JSON配列文字列）
        string proofType;          // 証明タイプ（例: "cosine_similarity", "full_similarity"）
        bytes32 dataHash;          // 元データのハッシュ（オプション）
        uint256 timestamp;         // 記録時刻
        address recorder;          // 記録者アドレス
        bool verified;             // 検証済みフラグ
        bool exists;               // レコード存在フラグ
    }

    // ===== 状態変数 =====

    // 証明ID → ZKProofRecord のマッピング
    mapping(bytes32 => ZKProofRecord) private proofIdToRecord;

    // デバイスID → 証明IDリスト のマッピング
    mapping(string => bytes32[]) private deviceToProofIds;

    // 全証明IDリスト
    bytes32[] private allProofIds;

    // コントラクトオーナー
    address public owner;

    // 記録者ホワイトリスト
    mapping(address => bool) public authorizedRecorders;

    // 検証者ホワイトリスト
    mapping(address => bool) public authorizedVerifiers;

    // ===== イベント定義 =====

    /**
     * @dev ZKP証明が記録された際のイベント
     */
    event ZKProofRecorded(
        bytes32 indexed proofId,
        string indexed deviceId,
        string proofType,
        bytes32 dataHash,
        uint256 timestamp,
        address indexed recorder
    );

    /**
     * @dev ZKP証明が検証された際のイベント
     */
    event ZKProofVerified(
        bytes32 indexed proofId,
        address indexed verifier,
        bool isValid,
        uint256 timestamp
    );

    /**
     * @dev 記録者が追加された際のイベント
     */
    event RecorderAuthorized(address indexed recorder, address indexed authorizer);

    /**
     * @dev 記録者が削除された際のイベント
     */
    event RecorderRevoked(address indexed recorder, address indexed revoker);

    /**
     * @dev 検証者が追加された際のイベント
     */
    event VerifierAuthorized(address indexed verifier, address indexed authorizer);

    /**
     * @dev 検証者が削除された際のイベント
     */
    event VerifierRevoked(address indexed verifier, address indexed revoker);

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
            "Not authorized to record proofs"
        );
        _;
    }

    /**
     * @dev 認可された検証者のみ実行可能
     */
    modifier onlyAuthorizedVerifier() {
        require(
            authorizedVerifiers[msg.sender] || msg.sender == owner,
            "Not authorized to verify proofs"
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
        authorizedVerifiers[msg.sender] = true;
        emit RecorderAuthorized(msg.sender, msg.sender);
        emit VerifierAuthorized(msg.sender, msg.sender);
    }

    // ===== メイン機能 =====

    /**
     * @dev ZKP証明をブロックチェーンに記録
     * @param deviceId デバイスID
     * @param proofData ZKP証明データ（JSON文字列）
     * @param publicSignals 公開信号（JSON配列文字列）
     * @param proofType 証明タイプ
     * @param dataHash 元データのハッシュ（オプション、0x0でもOK）
     * @return bytes32 生成された証明ID
     */
    function recordZKProof(
        string memory deviceId,
        string memory proofData,
        string memory publicSignals,
        string memory proofType,
        bytes32 dataHash
    ) public onlyAuthorizedRecorder returns (bytes32) {
        // 入力バリデーション
        require(bytes(deviceId).length > 0, "Device ID cannot be empty");
        require(bytes(proofData).length > 0, "Proof data cannot be empty");
        require(bytes(publicSignals).length > 0, "Public signals cannot be empty");
        require(bytes(proofType).length > 0, "Proof type cannot be empty");

        // 証明IDを生成（デバイスID + タイムスタンプ + 証明データのハッシュ）
        bytes32 proofId = keccak256(abi.encodePacked(
            deviceId,
            block.timestamp,
            proofData,
            msg.sender
        ));

        // 重複チェック
        require(!proofIdToRecord[proofId].exists, "Proof ID already exists");

        // レコード作成
        ZKProofRecord memory newRecord = ZKProofRecord({
            deviceId: deviceId,
            proofData: proofData,
            publicSignals: publicSignals,
            proofType: proofType,
            dataHash: dataHash,
            timestamp: block.timestamp,
            recorder: msg.sender,
            verified: false,
            exists: true
        });

        // マッピングに保存
        proofIdToRecord[proofId] = newRecord;
        deviceToProofIds[deviceId].push(proofId);
        allProofIds.push(proofId);

        // イベント発行
        emit ZKProofRecorded(
            proofId,
            deviceId,
            proofType,
            dataHash,
            block.timestamp,
            msg.sender
        );

        return proofId;
    }

    /**
     * @dev 証明IDからZKP証明情報を取得
     * @param proofId 証明ID
     * @return ZKProofRecord 証明レコード
     */
    function getZKProofById(bytes32 proofId)
        public
        view
        returns (ZKProofRecord memory)
    {
        require(proofIdToRecord[proofId].exists, "Proof ID not found");
        return proofIdToRecord[proofId];
    }

    /**
     * @dev デバイスIDから関連する証明IDリストを取得
     * @param deviceId デバイスID
     * @return bytes32[] 証明IDリスト
     */
    function getDeviceProofIds(string memory deviceId)
        public
        view
        returns (bytes32[] memory)
    {
        return deviceToProofIds[deviceId];
    }

    /**
     * @dev デバイスIDから最新の証明IDを取得
     * @param deviceId デバイスID
     * @return bytes32 最新の証明ID
     */
    function getLatestDeviceProofId(string memory deviceId)
        public
        view
        returns (bytes32)
    {
        bytes32[] memory proofIds = deviceToProofIds[deviceId];
        require(proofIds.length > 0, "No proofs found for device");
        return proofIds[proofIds.length - 1];
    }

    /**
     * @dev デバイスの証明記録件数を取得
     * @param deviceId デバイスID
     * @return uint256 証明記録件数
     */
    function getDeviceProofCount(string memory deviceId)
        public
        view
        returns (uint256)
    {
        return deviceToProofIds[deviceId].length;
    }

    /**
     * @dev 証明IDが記録されているか確認
     * @param proofId 証明ID
     * @return bool 存在フラグ
     */
    function proofExists(bytes32 proofId) public view returns (bool) {
        return proofIdToRecord[proofId].exists;
    }

    /**
     * @dev 全証明記録件数を取得
     * @return uint256 全証明記録件数
     */
    function getTotalProofCount() public view returns (uint256) {
        return allProofIds.length;
    }

    /**
     * @dev ZKP証明を検証済みとしてマーク
     * @param proofId 証明ID
     * @param isValid 検証結果
     */
    function markProofAsVerified(bytes32 proofId, bool isValid)
        public
        onlyAuthorizedVerifier
    {
        require(proofIdToRecord[proofId].exists, "Proof ID not found");

        proofIdToRecord[proofId].verified = isValid;

        emit ZKProofVerified(
            proofId,
            msg.sender,
            isValid,
            block.timestamp
        );
    }

    /**
     * @dev ページネーション付きで証明IDリストを取得
     * @param offset 開始位置
     * @param limit 取得件数
     * @return bytes32[] 証明IDリスト
     */
    function getAllProofIdsPaginated(uint256 offset, uint256 limit)
        public
        view
        returns (bytes32[] memory)
    {
        require(offset < allProofIds.length, "Offset out of bounds");

        uint256 end = offset + limit;
        if (end > allProofIds.length) {
            end = allProofIds.length;
        }

        uint256 resultLength = end - offset;
        bytes32[] memory result = new bytes32[](resultLength);

        for (uint256 i = 0; i < resultLength; i++) {
            result[i] = allProofIds[offset + i];
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
     * @dev 検証者を認可リストに追加
     * @param verifier 認可する検証者のアドレス
     */
    function authorizeVerifier(address verifier) public onlyOwner {
        require(verifier != address(0), "Invalid verifier address");
        require(!authorizedVerifiers[verifier], "Verifier already authorized");

        authorizedVerifiers[verifier] = true;
        emit VerifierAuthorized(verifier, msg.sender);
    }

    /**
     * @dev 検証者を認可リストから削除
     * @param verifier 削除する検証者のアドレス
     */
    function revokeVerifier(address verifier) public onlyOwner {
        require(verifier != owner, "Cannot revoke owner");
        require(authorizedVerifiers[verifier], "Verifier not authorized");

        authorizedVerifiers[verifier] = false;
        emit VerifierRevoked(verifier, msg.sender);
    }

    /**
     * @dev アドレスが記録者として認可されているか確認
     * @param recorder 確認するアドレス
     * @return bool 認可フラグ
     */
    function isAuthorizedRecorder(address recorder) public view returns (bool) {
        return authorizedRecorders[recorder] || recorder == owner;
    }

    /**
     * @dev アドレスが検証者として認可されているか確認
     * @param verifier 確認するアドレス
     * @return bool 認可フラグ
     */
    function isAuthorizedVerifier(address verifier) public view returns (bool) {
        return authorizedVerifiers[verifier] || verifier == owner;
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
        authorizedVerifiers[newOwner] = true;

        emit RecorderAuthorized(newOwner, oldOwner);
        emit VerifierAuthorized(newOwner, oldOwner);
    }

    // ===== バッチ処理機能 =====

    /**
     * @dev 複数のZKP証明を一括記録（ガスコスト最適化）
     * @param deviceIds デバイスIDの配列
     * @param proofDataArray 証明データの配列
     * @param publicSignalsArray 公開信号の配列
     * @param proofTypes 証明タイプの配列
     * @param dataHashes データハッシュの配列
     * @return bytes32[] 生成された証明IDの配列
     */
    function batchRecordZKProofs(
        string[] memory deviceIds,
        string[] memory proofDataArray,
        string[] memory publicSignalsArray,
        string[] memory proofTypes,
        bytes32[] memory dataHashes
    ) public onlyAuthorizedRecorder returns (bytes32[] memory) {
        require(
            deviceIds.length == proofDataArray.length &&
            proofDataArray.length == publicSignalsArray.length &&
            publicSignalsArray.length == proofTypes.length &&
            proofTypes.length == dataHashes.length,
            "Array lengths must match"
        );
        require(deviceIds.length > 0, "Empty arrays not allowed");
        require(deviceIds.length <= 50, "Batch size too large");

        bytes32[] memory proofIds = new bytes32[](deviceIds.length);

        for (uint256 i = 0; i < deviceIds.length; i++) {
            // 証明IDを生成
            bytes32 proofId = keccak256(abi.encodePacked(
                deviceIds[i],
                block.timestamp,
                i,  // バッチ内のインデックスを含めて一意性を保証
                proofDataArray[i],
                msg.sender
            ));

            // 重複チェック
            if (!proofIdToRecord[proofId].exists) {
                // レコード作成
                ZKProofRecord memory newRecord = ZKProofRecord({
                    deviceId: deviceIds[i],
                    proofData: proofDataArray[i],
                    publicSignals: publicSignalsArray[i],
                    proofType: proofTypes[i],
                    dataHash: dataHashes[i],
                    timestamp: block.timestamp,
                    recorder: msg.sender,
                    verified: false,
                    exists: true
                });

                proofIdToRecord[proofId] = newRecord;
                deviceToProofIds[deviceIds[i]].push(proofId);
                allProofIds.push(proofId);

                emit ZKProofRecorded(
                    proofId,
                    deviceIds[i],
                    proofTypes[i],
                    dataHashes[i],
                    block.timestamp,
                    msg.sender
                );
            }

            proofIds[i] = proofId;
        }

        return proofIds;
    }

    // ===== ビューヘルパー関数 =====

    /**
     * @dev コントラクト情報を取得
     * @return address オーナーアドレス
     * @return uint256 総証明記録件数
     * @return uint256 現在のブロック番号
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
            allProofIds.length,
            block.number
        );
    }

    /**
     * @dev 特定タイプの証明数を取得
     * @param proofType 証明タイプ
     * @return uint256 該当する証明の数
     */
    function getProofCountByType(string memory proofType)
        public
        view
        returns (uint256)
    {
        uint256 count = 0;
        for (uint256 i = 0; i < allProofIds.length; i++) {
            if (keccak256(bytes(proofIdToRecord[allProofIds[i]].proofType)) == keccak256(bytes(proofType))) {
                count++;
            }
        }
        return count;
    }
}
