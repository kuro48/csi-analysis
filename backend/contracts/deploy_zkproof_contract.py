"""
ZKProofRegistry スマートコントラクトデプロイスクリプト

使用方法:
    python backend/contracts/deploy_zkproof_contract.py
"""

import json
import sys
from pathlib import Path
from web3 import Web3
from solcx import compile_standard, install_solc
import os

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

# 環境変数読み込み
from dotenv import load_dotenv
load_dotenv()


def compile_contract():
    """Solidityコントラクトをコンパイル"""
    print("📝 Solidityコンパイラをインストール中...")
    install_solc('0.8.20')

    contract_path = Path(__file__).parent / "ZKProofRegistry.sol"

    print(f"📄 コントラクトを読み込み中: {contract_path}")
    with open(contract_path, 'r') as f:
        contract_source = f.read()

    print("🔨 コントラクトをコンパイル中...")
    compiled = compile_standard({
        "language": "Solidity",
        "sources": {
            "ZKProofRegistry.sol": {
                "content": contract_source
            }
        },
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                }
            }
        }
    }, solc_version='0.8.20')

    # ABIとバイトコードを抽出
    contract_interface = compiled['contracts']['ZKProofRegistry.sol']['ZKProofRegistry']
    abi = contract_interface['abi']
    bytecode = contract_interface['evm']['bytecode']['object']

    print("✅ コンパイル完了")
    return abi, bytecode


def deploy_contract(w3, abi, bytecode, account_address):
    """コントラクトをデプロイ"""
    print(f"\n🚀 ZKProofRegistryコントラクトをデプロイ中...")
    print(f"   アカウント: {account_address}")
    print(f"   残高: {w3.from_wei(w3.eth.get_balance(account_address), 'ether')} ETH")

    # コントラクトオブジェクトを作成
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # トランザクションを構築してデプロイ
    tx_hash = Contract.constructor().transact({'from': account_address})

    print(f"   トランザクションハッシュ: {w3.to_hex(tx_hash)}")
    print("   トランザクション確認待機中...")

    # トランザクションレシートを待機
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    contract_address = tx_receipt.contractAddress
    print(f"\n✅ デプロイ完了!")
    print(f"   コントラクトアドレス: {contract_address}")
    print(f"   ブロック番号: {tx_receipt.blockNumber}")
    print(f"   ガス使用量: {tx_receipt.gasUsed}")

    return contract_address


def save_contract_artifacts(abi, address):
    """コントラクトのABIとアドレスを保存"""
    build_dir = Path(__file__).parent / "build"
    build_dir.mkdir(exist_ok=True)

    artifact_path = build_dir / "ZKProofRegistry.json"

    artifact = {
        "address": address,
        "abi": abi
    }

    with open(artifact_path, 'w') as f:
        json.dump(artifact, f, indent=2)

    print(f"\n💾 コントラクト情報を保存しました: {artifact_path}")


def update_env_file(contract_address):
    """環境変数ファイルにコントラクトアドレスを追記"""
    backend_dir = Path(__file__).parent.parent
    env_file = backend_dir / ".env"

    # 既存の.envファイルを読み込む
    env_lines = []
    zkproof_contract_exists = False

    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('ZKPROOF_CONTRACT_ADDRESS='):
                    env_lines.append(f'ZKPROOF_CONTRACT_ADDRESS={contract_address}\n')
                    zkproof_contract_exists = True
                else:
                    env_lines.append(line)

    # ZKPROOF_CONTRACT_ADDRESSが存在しない場合は追加
    if not zkproof_contract_exists:
        env_lines.append(f'\n# ZKProof Registry Contract Address\n')
        env_lines.append(f'ZKPROOF_CONTRACT_ADDRESS={contract_address}\n')

    # .envファイルに書き込む
    with open(env_file, 'w') as f:
        f.writelines(env_lines)

    print(f"✅ {env_file} を更新しました")


def main():
    """メイン処理"""
    print("=" * 60)
    print("ZKProof Registry スマートコントラクト デプロイツール")
    print("=" * 60)

    # Ethereumノードに接続
    ethereum_rpc_url = os.getenv('ETHEREUM_RPC_URL', 'http://localhost:8545')
    print(f"\n🔗 Ethereumノードに接続中: {ethereum_rpc_url}")

    w3 = Web3(Web3.HTTPProvider(ethereum_rpc_url))

    if not w3.is_connected():
        print("❌ エラー: Ethereumノードに接続できません")
        print("   Ganacheが起動していることを確認してください:")
        print("   docker-compose up ganache")
        sys.exit(1)

    print(f"✅ 接続成功")
    print(f"   チェーンID: {w3.eth.chain_id}")
    print(f"   ブロック番号: {w3.eth.block_number}")

    # アカウント取得
    accounts = w3.eth.accounts
    if not accounts:
        print("❌ エラー: 利用可能なアカウントがありません")
        sys.exit(1)

    account_address = accounts[0]

    # コントラクトをコンパイル
    abi, bytecode = compile_contract()

    # コントラクトをデプロイ
    contract_address = deploy_contract(w3, abi, bytecode, account_address)

    # コントラクト情報を保存
    save_contract_artifacts(abi, contract_address)

    # 環境変数ファイルを更新
    update_env_file(contract_address)

    print("\n" + "=" * 60)
    print("🎉 デプロイが正常に完了しました!")
    print("=" * 60)
    print("\n次のステップ:")
    print("1. バックエンドサービスを再起動してください:")
    print("   docker-compose restart backend")
    print("\n2. または、環境変数を読み込み直してください:")
    print("   export ZKPROOF_CONTRACT_ADDRESS=" + contract_address)
    print("\n3. コントラクトの動作確認:")
    print("   python backend/contracts/check_zkproof_blockchain.py")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  デプロイが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
