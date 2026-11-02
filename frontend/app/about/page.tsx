import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16 text-slate-800">
      <Link href="/" className="text-emerald-800">
        ← 検証コンソールに戻る
      </Link>
      <h1 className="mt-10 text-3xl font-semibold">プライバシーと検証範囲</h1>
      <div className="mt-8 space-y-8 leading-8">
        <section>
          <h2 className="text-xl font-semibold">チェーンに公開される情報</h2>
          <p>
            Groth16証明、回路の識別子、公開入力、送信ウォレット、トランザクション時刻が公開されます。生のCSI、ファイル名、デバイスIDはこの検証フローから送信しません。公開入力には回路に応じて判定値やコミットメントが含まれます。送信前に内容を確認してください。公開後の削除はできません。
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold">「検証済み」が意味すること</h2>
          <p>
            指定された検証鍵に対応する回路の制約を、秘密入力が満たすことをSolidityのVerifierが確認したという意味です。検証済みと「正常判定」は別です。公開判定が0でも、有効な証明として記録される場合があります。
          </p>
          <p>
            標準のbreathing_certificate回路は、モードの再構成性や帯域判定を検証します。センサーの真正性、元のCSIとの対応、VMDアルゴリズム全体の正しい実行、医学的な正常性を保証するものではありません。複数回路を登録しても、回路間のデータの連続性が自動的に証明されるわけではありません。
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold">ファイルとアクセス権限</h2>
          <p>
            証明JSONを読み込む場合、サーバーには証明と公開入力だけを送ります。CSIから生成する場合は運用者トークンが必要で、サーバーがCSIを処理します。この経路ではCSIをデータベースに保存せず、処理後に一時ファイルを削除します。サーバー内での処理まで秘密にする仕組みではありません。ブラウザ履歴には送信ハッシュ、チェーン、送信先、時刻だけを保存します。
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold">確認数と費用</h2>
          <p>
            ウォレットからの送信にはガス代がかかります。送信前検証の成功は、ブロックへの取り込みを保証しません。画面は検証成功イベントと所定の確認数を照合しますが、ブロックの再編成やネットワーク障害によって状況が変わることがあります。履歴から改めて照会できます。
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold">
            研究用システムとしての位置づけ
          </h2>
          <p>
            このシステムは研究用で、医療診断には使用できません。公開ネットワークでの信頼は、回路、検証鍵、trusted
            setupの信頼性にも依存します。既存の開発用セットアップ鍵を、本番向けに監査された鍵として扱わないでください。
          </p>
        </section>
      </div>
    </main>
  );
}
