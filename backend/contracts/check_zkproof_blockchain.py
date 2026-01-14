#!/usr/bin/env python3
"""
ZKProofブロックチェーン記録確認スクリプト

使い方:
  python check_zkproof_blockchain.py                    # コントラクト情報のみ表示
  python check_zkproof_blockchain.py --proof-id 0xXXXX  # 特定の証明IDを確認
  python check_zkproof_blockchain.py --recent 5         # 最近の5件の記録を表示
  python check_zkproof_blockchain.py --device test_device  # デバイスの証明を表示
"""

import sys
import json
from pathlib import Path
from web3 import Web3
from datetime import datetime
import argparse

# 設定
GANACHE_URL = "http://localhost:8545"
CONTRACT_BUILD_PATH = Path(__file__).parent / "build" / "ZKProofRegistry.json"


def connect_to_blockchain():
    """ブロックチェーンに接続"""
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

    if not w3.is_connected():
        print("❌ Ganacheに接続できません")
        print(f"   URL: {GANACHE_URL}")
        sys.exit(1)

    print("✅ Ganacheに接続しました")
    print(f"   チェーンID: {w3.eth.chain_id}")
    print(f"   ブロック番号: {w3.eth.block_number}")
    print()

    return w3


def load_contract(w3):
    """スマートコントラクトを読み込み"""
    if not CONTRACT_BUILD_PATH.exists():
        print(f"❌ コントラクトファイルが見つかりません: {CONTRACT_BUILD_PATH}")
        print("   先にコントラクトをデプロイしてください:")
        print("   python backend/contracts/deploy_zkproof_contract.py")
        sys.exit(1)

    with open(CONTRACT_BUILD_PATH, 'r') as f:
        contract_data = json.load(f)

    contract_address = contract_data.get('address')
    if not contract_address:
        print("❌ コントラクトアドレスが見つかりません")
        sys.exit(1)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_data['abi']
    )

    print(f"✅ コントラクトを読み込みました")
    print(f"   アドレス: {contract_address}")
    print()

    return contract, contract_address


def show_contract_info(contract):
    """コントラクト情報を表示"""
    try:
        info = contract.functions.getContractInfo().call()
        owner = info[0]
        total_records = info[1]
        current_block = info[2]

        print("=" * 60)
        print("📊 ZKProof Registry コントラクト情報")
        print("=" * 60)
        print(f"オーナー: {owner}")
        print(f"総証明記録件数: {total_records}")
        print(f"現在のブロック: {current_block}")
        print()

        return total_records
    except Exception as e:
        print(f"❌ コントラクト情報取得エラー: {e}")
        return 0


def check_proof_exists(contract, proof_id):
    """特定の証明IDが記録されているか確認"""
    try:
        print("=" * 60)
        print(f"🔍 証明ID確認: {proof_id}")
        print("=" * 60)

        # 証明IDを bytes32 に変換
        if isinstance(proof_id, str):
            if proof_id.startswith('0x'):
                proof_id_bytes = bytes.fromhex(proof_id[2:])
            else:
                proof_id_bytes = bytes.fromhex(proof_id)
        else:
            proof_id_bytes = proof_id

        exists = contract.functions.proofExists(proof_id_bytes).call()

        if exists:
            print("✅ この証明IDは記録されています")

            # 詳細情報を取得
            record = contract.functions.getZKProofById(proof_id_bytes).call()
            device_id = record[0]
            proof_data = record[1]
            public_signals = record[2]
            proof_type = record[3]
            data_hash = record[4]
            timestamp = record[5]
            recorder = record[6]
            verified = record[7]

            dt = datetime.fromtimestamp(timestamp)

            print(f"   デバイスID: {device_id}")
            print(f"   証明タイプ: {proof_type}")
            print(f"   記録日時: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   記録者: {recorder}")
            print(f"   検証済み: {'はい' if verified else 'いいえ'}")
            print(f"   データハッシュ: {data_hash.hex()}")
            print(f"\n   証明データ（先頭100文字）:")
            print(f"   {proof_data[:100]}...")
            print(f"\n   公開信号（先頭100文字）:")
            print(f"   {public_signals[:100]}...")
        else:
            print("❌ この証明IDは記録されていません")

        print()
        return exists

    except Exception as e:
        print(f"❌ 証明ID確認エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_device_proofs(contract, device_id, limit=5):
    """デバイスの証明を表示"""
    try:
        print("=" * 60)
        print(f"📱 デバイス証明確認: {device_id}")
        print("=" * 60)

        proof_ids = contract.functions.getDeviceProofIds(device_id).call()

        if not proof_ids:
            print("このデバイスの証明記録はありません")
            print()
            return

        print(f"証明件数: {len(proof_ids)}")
        print(f"表示件数: 最新{min(limit, len(proof_ids))}件\n")

        # 最新のものから表示
        for i, proof_id in enumerate(reversed(proof_ids[-limit:])):
            record = contract.functions.getZKProofById(proof_id).call()
            proof_type = record[3]
            timestamp = record[5]
            verified = record[7]

            dt = datetime.fromtimestamp(timestamp)

            print(f"【証明 #{len(proof_ids) - i}】")
            print(f"  証明ID: {proof_id.hex()}")
            print(f"  証明タイプ: {proof_type}")
            print(f"  検証済み: {'はい' if verified else 'いいえ'}")
            print(f"  記録日時: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

    except Exception as e:
        print(f"❌ デバイス証明取得エラー: {e}")
        import traceback
        traceback.print_exc()


def show_recent_records(contract, w3, limit=5):
    """最近の記録を表示"""
    try:
        # ZKProofRecordedイベントを取得
        event_filter = contract.events.ZKProofRecorded.create_filter(fromBlock=0)
        events = event_filter.get_all_entries()

        print("=" * 60)
        print(f"📝 最近の記録（最大{limit}件）")
        print("=" * 60)

        if not events:
            print("記録がありません")
            print()
            return

        # 最新のものから表示
        for i, event in enumerate(reversed(events[-limit:])):
            args = event['args']
            block = w3.eth.get_block(event['blockNumber'])
            dt = datetime.fromtimestamp(block['timestamp'])

            print(f"\n【記録 #{len(events) - i}】")
            print(f"  証明ID: {args['proofId'].hex()}")
            print(f"  デバイスID: {args['deviceId']}")
            print(f"  証明タイプ: {args['proofType']}")
            print(f"  データハッシュ: {args['dataHash'].hex()}")
            print(f"  記録者: {args['recorder']}")
            print(f"  ブロック: {event['blockNumber']}")
            print(f"  日時: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  TxHash: {event['transactionHash'].hex()}")

        print()

    except Exception as e:
        print(f"❌ イベント取得エラー: {e}")
        import traceback
        traceback.print_exc()


def show_proof_types_stats(contract):
    """証明タイプ別の統計を表示"""
    try:
        print("=" * 60)
        print("📈 証明タイプ別統計")
        print("=" * 60)

        # 一般的な証明タイプをチェック
        proof_types = [
            "cosine_similarity",
            "full_similarity",
            "breathing_analysis",
            "custom"
        ]

        for proof_type in proof_types:
            try:
                count = contract.functions.getProofCountByType(proof_type).call()
                if count > 0:
                    print(f"  {proof_type}: {count}件")
            except:
                pass

        print()

    except Exception as e:
        print(f"❌ 統計取得エラー: {e}")


def main():
    parser = argparse.ArgumentParser(description='ZKProofブロックチェーン記録確認ツール')
    parser.add_argument('--proof-id', help='確認する証明ID（0xプレフィックス付き）')
    parser.add_argument('--device', help='確認するデバイスID')
    parser.add_argument('--recent', type=int, default=5, help='最近のN件を表示（デフォルト: 5）')
    parser.add_argument('--no-recent', action='store_true', help='最近の記録を表示しない')
    parser.add_argument('--stats', action='store_true', help='証明タイプ別統計を表示')

    args = parser.parse_args()

    # 接続
    w3 = connect_to_blockchain()
    contract, contract_address = load_contract(w3)

    # コントラクト情報表示
    total_records = show_contract_info(contract)

    # 特定の証明ID確認
    if args.proof_id:
        check_proof_exists(contract, args.proof_id)

    # デバイスの証明表示
    if args.device:
        show_device_proofs(contract, args.device, args.recent)

    # 統計表示
    if args.stats:
        show_proof_types_stats(contract)

    # 最近の記録表示
    if not args.no_recent and total_records > 0 and not args.device:
        show_recent_records(contract, w3, args.recent)

    print("=" * 60)
    print("✅ 確認完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
