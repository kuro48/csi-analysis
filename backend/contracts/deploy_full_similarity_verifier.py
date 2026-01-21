"""
Full Similarity Verifier コントラクトデプロイスクリプト

使用方法:
    python backend/contracts/deploy_full_similarity_verifier.py
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


def compile_contract(solidity_path: Path):
    """Solidity検証コントラクトをコンパイル"""
    print("📝 Solidityコンパイラをインストール中...")
    install_solc("0.8.20")

    print(f"📄 コントラクトを読み込み中: {solidity_path}")
    source = solidity_path.read_text()

    print("🔨 コントラクトをコンパイル中...")
    compiled = compile_standard({
        "language": "Solidity",
        "sources": {
            solidity_path.name: {
                "content": source
            }
        },
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                }
            }
        }
    }, solc_version="0.8.20")

    contract_name = "Groth16Verifier"
    contract_interface = compiled["contracts"][solidity_path.name][contract_name]
    abi = contract_interface["abi"]
    bytecode = contract_interface["evm"]["bytecode"]["object"]

    print("✅ コンパイル完了")
    return abi, bytecode


def deploy_contract(w3, abi, bytecode, account_address):
    """コントラクトをデプロイ"""
    print("\n🚀 Full Similarity Verifierをデプロイ中...")
    print(f"   アカウント: {account_address}")
    print(f"   残高: {w3.from_wei(w3.eth.get_balance(account_address), 'ether')} ETH")

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    gas_limit = int(os.getenv("ZKPROOF_VERIFIER_DEPLOY_GAS", "300000000"))
    gas_price = w3.eth.gas_price
    tx = Contract.constructor().build_transaction({
        "from": account_address,
        "nonce": w3.eth.get_transaction_count(account_address),
        "gas": gas_limit,
        "maxFeePerGas": gas_price,
        "maxPriorityFeePerGas": 0
    })
    tx_hash = w3.eth.send_transaction(tx)

    print(f"   トランザクションハッシュ: {w3.to_hex(tx_hash)}")
    print("   トランザクション確認待機中...")

    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress

    print("\n✅ デプロイ完了!")
    print(f"   コントラクトアドレス: {contract_address}")
    print(f"   ブロック番号: {tx_receipt.blockNumber}")
    print(f"   ガス使用量: {tx_receipt.gasUsed}")

    return contract_address


def save_contract_artifacts(abi, address):
    """コントラクトのABIとアドレスを保存"""
    build_dir = Path(__file__).parent / "build"
    build_dir.mkdir(exist_ok=True)

    artifact_path = build_dir / "FullSimilarityVerifier.json"
    artifact = {
        "address": address,
        "abi": abi
    }

    artifact_path.write_text(json.dumps(artifact, indent=2))
    print(f"\n💾 コントラクト情報を保存しました: {artifact_path}")


def main():
    """メイン処理"""
    print("=" * 60)
    print("Full Similarity Verifier スマートコントラクト デプロイツール")
    print("=" * 60)

    solidity_path = project_root / "zkp" / "build" / "full_similarity_verifier.sol"
    if not solidity_path.exists():
        print("❌ エラー: 検証コントラクトのSolidityファイルが見つかりません")
        print("   例: npx snarkjs zkey export solidityverifier \\")
        print("       zkp/keys/csi_full_similarity_final.zkey \\")
        print("       zkp/build/full_similarity_verifier.sol")
        sys.exit(1)

    ethereum_rpc_url = os.getenv("ETHEREUM_RPC_URL", "http://localhost:8545")
    print(f"\n🔗 Ethereumノードに接続中: {ethereum_rpc_url}")
    w3 = Web3(Web3.HTTPProvider(ethereum_rpc_url))

    if not w3.is_connected():
        print("❌ エラー: Ethereumノードに接続できません")
        print("   Ganacheが起動していることを確認してください")
        sys.exit(1)

    accounts = w3.eth.accounts
    if not accounts:
        print("❌ エラー: 利用可能なアカウントがありません")
        sys.exit(1)

    account_address = accounts[0]

    abi, bytecode = compile_contract(solidity_path)
    contract_address = deploy_contract(w3, abi, bytecode, account_address)
    save_contract_artifacts(abi, contract_address)

    print("\n" + "=" * 60)
    print("🎉 デプロイが正常に完了しました!")
    print("=" * 60)


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
