#!/usr/bin/env python3
"""
ブロックチェーン記録確認スクリプト

使い方:
  python check_blockchain.py                    # コントラクト情報のみ表示
  python check_blockchain.py --cid QmXXXXXX     # 特定のCIDが記録されているか確認
  python check_blockchain.py --recent 5         # 最近の5件の記録を表示
"""

import sys
import json
from pathlib import Path
from web3 import Web3
from datetime import datetime
import argparse

# 設定
GANACHE_URL = "http://localhost:8545"
CONTRACT_BUILD_PATH = Path(__file__).parent / "build" / "CSIDataRegistry.json"

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
        print("📊 コントラクト情報")
        print("=" * 60)
        print(f"オーナー: {owner}")
        print(f"総記録件数: {total_records}")
        print(f"現在のブロック: {current_block}")
        print()

        return total_records
    except Exception as e:
        print(f"❌ コントラクト情報取得エラー: {e}")
        return 0

def check_cid_exists(contract, cid):
    """特定のCIDが記録されているか確認"""
    try:
        print("=" * 60)
        print(f"🔍 CID確認: {cid}")
        print("=" * 60)

        exists = contract.functions.cidExists(cid).call()

        if exists:
            print("✅ このCIDは記録されています")

            # 詳細情報を取得
            record = contract.functions.getCSIDataByCID(cid).call()
            device_id = record[0]
            timestamp = record[1]
            block_number = record[2]
            data_hash = record[3]

            # dt = datetime.fromtimestamp(timestamp)

            print(f"   デバイスID: {device_id}")
            # print(f"   記録日時: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   ブロック番号: {block_number}")
            print(f"   データハッシュ: {data_hash}")
        else:
            print("❌ このCIDは記録されていません")

        print()
        return exists

    except Exception as e:
        print(f"❌ CID確認エラー: {e}")
        return False

def show_recent_records(contract, w3, limit=5):
    """最近の記録を表示"""
    try:
        # DataRecordedイベントを取得
        event_filter = contract.events.DataRecorded.create_filter(fromBlock=0)
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
            print(f"  CID: {args['cid']}")
            print(f"  デバイスID: {args['deviceId']}")
            print(f"  データハッシュ: {args['dataHash']}")
            print(f"  記録者: {args['recorder']}")
            print(f"  ブロック: {event['blockNumber']}")
            print(f"  日時: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  TxHash: {event['transactionHash'].hex()}")

        print()

    except Exception as e:
        print(f"❌ イベント取得エラー: {e}")
        print()

def main():
    parser = argparse.ArgumentParser(description='ブロックチェーン記録確認ツール')
    parser.add_argument('--cid', help='確認するCID')
    parser.add_argument('--recent', type=int, default=5, help='最近のN件を表示（デフォルト: 5）')
    parser.add_argument('--no-recent', action='store_true', help='最近の記録を表示しない')

    args = parser.parse_args()

    # 接続
    w3 = connect_to_blockchain()
    contract, contract_address = load_contract(w3)

    # コントラクト情報表示
    total_records = show_contract_info(contract)

    # 特定のCID確認
    if args.cid:
        check_cid_exists(contract, args.cid)

    # 最近の記録表示
    if not args.no_recent and total_records > 0:
        show_recent_records(contract, w3, args.recent)

    print("=" * 60)
    print("✅ 確認完了")
    print("=" * 60)

if __name__ == "__main__":
    main()
