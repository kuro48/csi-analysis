"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserProvider, Interface, type Eip1193Provider } from "ethers";
import { API_BASE } from "../upload/constants";
import {
  parseBundle,
  type ChainStatus,
  type Prepared,
  type ProofBundle,
  type Receipt,
} from "./types";
import s from "./console.module.css";

type WalletProvider = Eip1193Provider & {
  on?: (event: string, listener: () => void) => void;
  removeListener?: (event: string, listener: () => void) => void;
};
type HistoryItem = {
  hash: string;
  chainId: number;
  registry: string;
  date: string;
};
const STORE = "csi-verified-transactions-v1";
const short = (value?: string) =>
  value ? `${value.slice(0, 8)}…${value.slice(-6)}` : "—";
const labels: Record<Receipt["status"], string> = {
  pending: "承認待ち",
  confirming: "ブロック確認中",
  confirmed: "オンチェーン検証済み",
  reverted: "トランザクション失敗",
  not_found: "未記録",
};
function ethereum() {
  return (window as Window & { ethereum?: WalletProvider }).ethereum;
}
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v2${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(25_000),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `リクエストに失敗しました (${response.status})`,
    );
  return body as T;
}
function errorText(error: unknown) {
  if (
    typeof error === "object" &&
    error &&
    "code" in error &&
    [4001, "ACTION_REJECTED"].includes(error.code as string | number)
  )
    return "ウォレットで署名がキャンセルされました。再度送信できます。";
  return error instanceof Error
    ? error.message
    : "処理に失敗しました。接続を確認して再試行してください。";
}
function download(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
function Glyph({ kind = "grid" }: { kind?: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
    >
      {kind === "shield" ? (
        <>
          <path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z" />
          <path d="m8 12 3 3 5-6" />
        </>
      ) : kind === "arrow" ? (
        <>
          <path d="M5 12h14m-5-5 5 5-5 5" />
        </>
      ) : kind === "upload" ? (
        <>
          <path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" />
        </>
      ) : kind === "chain" ? (
        <>
          <path d="m9 15 6-6m-5-3 2-2a5 5 0 0 1 7 7l-2 2m-3 5-2 2a5 5 0 0 1-7-7l2-2" />
        </>
      ) : (
        <>
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </>
      )}
    </svg>
  );
}

export function VerificationConsole() {
  const [chain, setChain] = useState<ChainStatus | null>(null);
  const [wallet, setWallet] = useState("");
  const [bundle, setBundle] = useState<ProofBundle | null>(null);
  const [fileName, setFileName] = useState("");
  const [mode, setMode] = useState<"proof" | "csi">("proof");
  const [token, setToken] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [txHash, setTxHash] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [lookup, setLookup] = useState("");
  const [prepared, setPrepared] = useState(false);
  const [lookupVersion, setLookupVersion] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadAbort = useRef<AbortController | null>(null);
  const lock = useRef(false);

  const refreshChain = useCallback(async () => {
    try {
      setChain(await api<ChainStatus>("/onchain/status"));
    } catch {
      setChain({
        connected: false,
        message: "APIに接続できません。時間をおいて再接続してください。",
        circuits: [],
      });
    }
  }, []);
  useEffect(() => {
    let disposed = false;
    async function initialize() {
      await refreshChain();
      if (disposed) return;
      try {
        const saved: unknown = JSON.parse(localStorage.getItem(STORE) || "[]");
        if (Array.isArray(saved))
          setHistory(
            saved
              .filter(
                (item) =>
                  item &&
                  /^0x[\da-f]{64}$/i.test(item.hash) &&
                  typeof item.chainId === "number" &&
                  typeof item.registry === "string" &&
                  typeof item.date === "string",
              )
              .slice(0, 20),
          );
      } catch {
        /* Storage can be disabled by browser policy. */
      }
      const shared = new URLSearchParams(window.location.search).get("tx");
      if (shared && /^0x[\da-f]{64}$/i.test(shared)) {
        setLookup(shared);
        setTxHash(shared);
      }
    }
    void initialize();
    const provider = ethereum();
    const reset = () => {
      setWallet("");
      setPrepared(false);
      setNotice(
        "ウォレットの変更を検知しました。送信時に接続先を再確認します。",
      );
    };
    provider?.on?.("accountsChanged", reset);
    provider?.on?.("chainChanged", reset);
    return () => {
      disposed = true;
      provider?.removeListener?.("accountsChanged", reset);
      provider?.removeListener?.("chainChanged", reset);
      uploadAbort.current?.abort();
    };
  }, [refreshChain]);

  useEffect(() => {
    if (!txHash || !chain?.connected) return;
    let stopped = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api<Receipt>(`/onchain/transactions/${txHash}`, {
          signal: controller.signal,
        });
        if (stopped) return;
        setReceipt(result);
        setError("");
        if (["confirmed", "reverted"].includes(result.status)) {
          setNotice(
            result.status === "confirmed"
              ? "検証成功イベントと必要なブロック確認数を確認しました。"
              : "トランザクションが失敗しました。証明は記録されていません。",
          );
          void refreshChain();
          return;
        }
      } catch (e) {
        if (!stopped) setError(errorText(e));
      }
      if (!stopped) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [txHash, chain?.connected, refreshChain, lookupVersion]);

  async function connect() {
    const injected = ethereum();
    if (!injected)
      throw new Error(
        "MetaMaskなど、EVM対応のブラウザウォレットを接続してください。",
      );
    const provider = new BrowserProvider(injected);
    const signer = await provider.getSigner();
    setWallet(await signer.getAddress());
    return { provider, signer, injected };
  }
  async function loadFile(file: File) {
    if (lock.current) return;
    setError("");
    setNotice("");
    setBundle(null);
    setConsent(false);
    setPrepared(false);
    setFileName(file.name);
    setReceipt(null);
    setTxHash("");
    if (mode === "proof") {
      if (file.size > 128 * 1024) {
        setError("証明JSONは128 KB以下で指定してください。");
        return;
      }
      lock.current = true;
      setBusy("証明JSONを確認中…");
      try {
        setBundle(
          parseBundle(
            JSON.parse(await file.text()),
            "csi_breathing_certificate",
          ),
        );
      } catch (e) {
        setError(errorText(e));
      } finally {
        lock.current = false;
        setBusy("");
      }
      return;
    }
    if (
      !file.name.toLowerCase().endsWith(".csi") ||
      file.size === 0 ||
      file.size > 50 * 1024 * 1024
    ) {
      setError(
        "空でないPicoScenes .csiファイル（50 MB以下）を選択してください。",
      );
      return;
    }
    if (!token) {
      setError("CSI解析用の運用者アクセストークンを入力してください。");
      return;
    }
    lock.current = true;
    setBusy("CSIを解析して証明を生成しています。数分かかる場合があります。");
    const form = new FormData();
    form.append("file", file);
    const abort = new AbortController();
    uploadAbort.current = abort;
    const timeout = setTimeout(() => abort.abort(), 15 * 60_000);
    try {
      const result = await api<unknown>("/breathing/analyze-certificate", {
        method: "POST",
        body: form,
        headers: { Authorization: `Bearer ${token}` },
        signal: abort.signal,
      });
      setBundle(parseBundle(result, "csi_breathing_certificate"));
      setNotice(
        "証明を生成しました。公開入力を確認し、ウォレットから送信してください。",
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      clearTimeout(timeout);
      lock.current = false;
      setBusy("");
    }
  }
  async function submit() {
    if (!bundle || !chain?.connected || !consent || lock.current) return;
    lock.current = true;
    setBusy("検証コントラクトで送信前検証を実行中…");
    setError("");
    setNotice("");
    try {
      const result = await api<Prepared>("/onchain/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bundle),
      });
      setPrepared(true);
      if (result.alreadyVerified) {
        setTxHash("");
        setReceipt(result.record ?? null);
        setNotice("この証明はすでに記録されています。再送信は不要です。");
        return;
      }
      // Independently encode the transaction: the API cannot substitute a transfer or another call.
      const circuit = chain.circuits.find((c) => c.name === bundle.circuit);
      if (
        !circuit ||
        result.chainId !== chain.chainId ||
        result.to.toLowerCase() !== chain.registryAddress?.toLowerCase() ||
        result.value !== "0x0"
      )
        throw new Error("送信先の設定が一致しません。");
      const { pi_a: a, pi_b: b, pi_c: c } = bundle.proof;
      const iface = new Interface([
        "function verifyAndRecord(bytes32,uint256[2],uint256[2][2],uint256[2],uint256[])",
      ]);
      const data = iface.encodeFunctionData("verifyAndRecord", [
        circuit.circuitId,
        a.slice(0, 2),
        [
          [b[0][1], b[0][0]],
          [b[1][1], b[1][0]],
        ],
        c.slice(0, 2),
        bundle.publicSignals,
      ]);
      if (data !== result.data)
        throw new Error("証明とトランザクションの内容が一致しません。");
      setBusy("ウォレットのネットワークと署名を確認してください…");
      let connection = await connect();
      if (
        Number((await connection.provider.getNetwork()).chainId) !==
        chain.chainId
      ) {
        await connection.injected.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: `0x${chain.chainId!.toString(16)}` }],
        });
        connection = await connect();
      }
      if (
        Number((await connection.provider.getNetwork()).chainId) !==
        chain.chainId
      )
        throw new Error("ウォレットを対象ネットワークに切り替えてください。");
      const tx = await connection.signer.sendTransaction({
        to: result.to,
        data,
        value: 0,
        chainId: result.chainId,
      });
      setReceipt({
        status: "pending",
        transactionHash: tx.hash,
        proofId: result.proofId,
        confirmations: 0,
      });
      setTxHash(tx.hash);
      setLookup(tx.hash);
      const next = [
        {
          hash: tx.hash,
          chainId: result.chainId,
          registry: result.to,
          date: new Date().toISOString(),
        },
        ...history,
      ].slice(0, 20);
      setHistory(next);
      try {
        localStorage.setItem(STORE, JSON.stringify(next));
      } catch {
        setNotice(
          "履歴を保存できません。トランザクションハッシュを控えてください。",
        );
      }
      setNotice("送信しました。ブロックへの取り込みと確認数を確認しています。");
    } catch (e) {
      setError(errorText(e));
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  function inspectTransaction(hash: string) {
    setError("");
    setNotice("");
    setBundle(null);
    setFileName("");
    setConsent(false);
    setPrepared(false);
    setReceipt(null);
    setTxHash(hash);
    setLookup(hash);
    setLookupVersion((version) => version + 1);
  }
  const pending =
    receipt?.status === "pending" || receipt?.status === "confirming";
  const matching =
    bundle && chain?.circuits.find((c) => c.name === bundle.circuit);
  const explorer = chain?.explorerUrl?.startsWith("https://")
    ? chain.explorerUrl.replace(/\/$/, "")
    : "";
  const stages = [
    !!bundle,
    prepared,
    !!txHash,
    receipt?.status === "confirmed",
  ];

  return (
    <div className={s.shell}>
      <a className={s.skip} href="#workspace">
        メインコンテンツへ
      </a>
      <aside className={s.sidebar}>
        <Link className={s.brand} href="/">
          <span className={s.brandIcon}>
            <Glyph kind="shield" />
          </span>
          <span>
            CSI <strong>Proof</strong>
            <small>VERIFIABLE SENSING</small>
          </span>
        </Link>
        <div className={s.workspaceLabel}>WORKSPACE</div>
        <nav aria-label="メインナビゲーション">
          <Link href="/" className={s.active}>
            <Glyph />
            検証コンソール<span>01</span>
          </Link>
          <a href="#activity">
            <Glyph kind="chain" />
            送信履歴
          </a>
          <Link href="/about">
            <Glyph kind="shield" />
            検証とプライバシー
          </Link>
        </nav>
        <div className={s.sidebarBottom}>
          <span className={s.tinyLabel}>BUILT FOR PRIVACY</span>
          <p>
            データの価値を、
            <br />
            データを明かさずに。
          </p>
          <div className={s.protocol}>
            Groth16 <span>×</span> EVM
          </div>
        </div>
      </aside>
      <div className={s.main}>
        <header className={s.topbar}>
          <div className={s.breadcrumb}>
            Workspace <span>/</span> <strong>検証コンソール</strong>
          </div>
          <button
            className={s.wallet}
            onClick={() => {
              void connect().catch((e) => setError(errorText(e)));
            }}
          >
            <span className={wallet ? s.liveDot : s.dot} />
            {wallet ? short(wallet) : "ウォレットを接続"}
            <Glyph kind="arrow" />
          </button>
        </header>
        <main id="workspace" className={s.content}>
          <div className={s.heading}>
            <div>
              <div className={s.eyebrow}>
                <span /> PRIVATE DATA. PUBLIC TRUST.
              </div>
              <h1>
                プライバシーを守り、
                <br />
                <span>確かさを証明する。</span>
              </h1>
              <p>
                Wi-Fi CSIから生成したゼロ知識証明を、ブロックチェーンで検証。
                <br className={s.desktopBreak} />
                生の計測データを公開せずに、検証結果を共有できます。
              </p>
            </div>
            <div className={s.heroArt} aria-hidden="true">
              <div className={s.orbit} />
              <div className={s.orbitTwo} />
              <div className={s.artShield}>
                <Glyph kind="shield" />
              </div>
              <span className={s.artLabel}>ZERO-KNOWLEDGE PROOF</span>
              <span className={s.artNode}>01</span>
              <span className={s.artNodeTwo}>✓</span>
            </div>
          </div>
          <section className={s.metrics} aria-label="接続状態">
            <div>
              <span className={s.tinyLabel}>NETWORK</span>
              <strong>
                <span className={chain?.connected ? s.liveDot : s.dot} />
                {chain?.connected
                  ? chain.networkName
                  : chain
                    ? "未接続"
                    : "接続を確認中"}
              </strong>
              <small>
                {chain?.connected
                  ? `${chain.chainId === 11155111 ? "テストネット" : "ローカル"} · Chain ID ${chain.chainId}`
                  : "ネットワーク設定が必要です"}
              </small>
            </div>
            <div>
              <span className={s.tinyLabel}>VERIFIED PROOFS</span>
              <strong>
                {chain?.connected ? chain.totalVerified?.toLocaleString() : "—"}
                <em>件</em>
              </strong>
              <small>このコントラクトの検証済み証明</small>
            </div>
            <div>
              <span className={s.tinyLabel}>LATEST BLOCK</span>
              <strong>
                {chain?.connected
                  ? `#${chain.currentBlock?.toLocaleString()}`
                  : "—"}
              </strong>
              <small>RPCから取得した最新ブロック</small>
            </div>
            <div>
              <span className={s.tinyLabel}>DATA DISCLOSURE</span>
              <strong className={s.privacyValue}>
                生データ非公開
                <Glyph kind="shield" />
              </strong>
              <small>証明・公開入力はチェーンに公開</small>
            </div>
          </section>
          {chain && !chain.connected && (
            <div className={s.connectionNotice} role="status">
              <span>
                {chain.message ||
                  "検証コントラクトを設定するとオンチェーン検証を開始できます。"}
              </span>
              <button onClick={() => void refreshChain()}>再接続 ↻</button>
            </div>
          )}
          <div className={s.workGrid}>
            <section className={s.card} aria-labelledby="new-proof">
              <div className={s.cardHeading}>
                <div>
                  <span className={s.tinyLabel}>NEW VERIFICATION</span>
                  <h2 id="new-proof">証明を検証する</h2>
                </div>
                <span className={s.stepTag}>STEP 01 — 04</span>
              </div>
              <div className={s.tabs} role="group" aria-label="入力方法">
                <button
                  className={mode === "proof" ? s.selected : ""}
                  disabled={!!busy || pending}
                  onClick={() => {
                    setMode("proof");
                    setBundle(null);
                    setFileName("");
                    setConsent(false);
                    setPrepared(false);
                    setReceipt(null);
                    setTxHash("");
                  }}
                >
                  証明JSONを読み込む
                </button>
                <button
                  className={mode === "csi" ? s.selected : ""}
                  disabled={!!busy || pending}
                  onClick={() => {
                    setMode("csi");
                    setBundle(null);
                    setFileName("");
                    setConsent(false);
                    setPrepared(false);
                    setReceipt(null);
                    setTxHash("");
                  }}
                >
                  CSIから証明を生成
                </button>
              </div>
              {mode === "csi" && (
                <label className={s.tokenLabel}>
                  運用者アクセストークン
                  <input
                    type="password"
                    autoComplete="off"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="解析権限を持つトークンを入力"
                  />
                  <small>
                    トークンはこの画面のメモリ内だけで保持します。CSIファイルはサーバーで解析後、一時ファイルを削除します。
                  </small>
                </label>
              )}
              <input
                ref={fileRef}
                type="file"
                className={s.hiddenFile}
                aria-label={
                  mode === "proof" ? "証明JSONファイル" : "CSIファイル"
                }
                accept={mode === "proof" ? ".json,application/json" : ".csi"}
                disabled={!!busy || pending}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void loadFile(file);
                  e.target.value = "";
                }}
              />
              <button
                className={`${s.dropzone} ${bundle ? s.loaded : ""}`}
                disabled={!!busy || pending}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!busy && !pending && e.dataTransfer.files[0])
                    void loadFile(e.dataTransfer.files[0]);
                }}
              >
                <span className={s.uploadIcon}>
                  <Glyph kind={bundle ? "shield" : "upload"} />
                </span>
                <strong>
                  {bundle ? fileName : "ファイルをドロップ、または選択"}
                </strong>
                <span>
                  {bundle
                    ? "証明を読み込みました・公開入力を確認してください"
                    : mode === "proof"
                      ? "Groth16 証明JSON · 最大128 KB"
                      : "PicoScenes .csi · 最大50 MB"}
                </span>
                <span className={s.fileButton}>
                  {bundle ? "別のファイルを選択" : "ファイルを選択"} ↗
                </span>
              </button>
              {bundle && (
                <div className={s.proofDetails}>
                  <div>
                    <span>回路</span>
                    <code>{bundle.circuit}</code>
                  </div>
                  <div>
                    <span>公開入力</span>
                    <code>{bundle.publicSignals.join(", ")}</code>
                  </div>
                  {!matching && (
                    <p>この回路は接続先にデプロイされていません。</p>
                  )}
                  <button onClick={() => download(bundle, "csi-proof.json")}>
                    証明JSONを保存 ↓
                  </button>
                </div>
              )}
              <label className={s.consent}>
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={!!busy || pending}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>
                  証明・公開入力・ウォレットアドレスが公開され、送信後は削除できないことを確認しました。
                </span>
              </label>
              <button
                className={s.primary}
                disabled={
                  !bundle ||
                  !matching ||
                  !consent ||
                  !chain?.connected ||
                  !!busy ||
                  pending
                }
                onClick={() => void submit()}
              >
                {busy
                  ? "処理中…"
                  : pending
                    ? "ブロックの確認を待っています"
                    : "オンチェーンで検証する"}
                <Glyph kind="arrow" />
              </button>
              <p className={s.gasNote}>
                ウォレットで署名します。ネットワークのガス代が必要です。
              </p>
              {chain?.registryAddress && (
                <p className={s.gasNote}>
                  Registry:{" "}
                  <code title={chain.registryAddress}>
                    {short(chain.registryAddress)}
                  </code>
                </p>
              )}
              <div aria-live="polite">
                {busy && <p className={s.info}>{busy}</p>}
                {notice && <p className={s.info}>{notice}</p>}
              </div>
              {error && (
                <div role="alert" className={s.error}>
                  {error}
                </div>
              )}
            </section>
            <aside className={s.rightColumn}>
              <section className={`${s.card} ${s.progressCard}`}>
                <div className={s.cardHeading}>
                  <div>
                    <span className={s.tinyLabel}>VERIFICATION FLOW</span>
                    <h2>検証の進捗</h2>
                  </div>
                  <span className={s.liveLabel}>LIVE</span>
                </div>
                <ol className={s.timeline}>
                  {[
                    ["証明の準備", "CSI解析、または証明JSONの読み込み"],
                    ["送信前検証", "デプロイ済みVerifierで実行確認"],
                    [
                      "トランザクション送信",
                      "ウォレット署名・ネットワークへ送信",
                    ],
                    ["オンチェーン検証", "成功イベントと確認ブロック数を照合"],
                  ].map(([title, detail], i) => (
                    <li key={title} className={stages[i] ? s.done : ""}>
                      <span className={s.stageNumber}>
                        {stages[i] ? "✓" : `0${i + 1}`}
                      </span>
                      <div>
                        <strong>{title}</strong>
                        <p>{detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                {receipt && (
                  <div className={s.receipt} aria-live="polite">
                    <strong>{labels[receipt.status]}</strong>
                    <span>
                      確認数 {receipt.confirmations} /{" "}
                      {chain?.confirmationsRequired ?? "—"}
                    </span>
                    {receipt.proofId && (
                      <code>Proof {short(receipt.proofId)}</code>
                    )}
                    {receipt.blockNumber && (
                      <span>Block #{receipt.blockNumber.toLocaleString()}</span>
                    )}
                    {receipt.gasUsed && (
                      <span>Gas {receipt.gasUsed.toLocaleString()}</span>
                    )}
                    {txHash &&
                      (explorer ? (
                        <a
                          href={`${explorer}/tx/${txHash}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Explorerで確認 ↗
                        </a>
                      ) : (
                        <code>{txHash}</code>
                      ))}
                    <button
                      onClick={() =>
                        download(
                          {
                            ...receipt,
                            chainId: chain?.chainId,
                            registryAddress: chain?.registryAddress,
                          },
                          "verification-receipt.json",
                        )
                      }
                    >
                      検証記録を保存 ↓
                    </button>
                    {txHash && (
                      <button
                        onClick={() => {
                          navigator.clipboard
                            .writeText(
                              `${window.location.origin}/verify?tx=${txHash}`,
                            )
                            .then(() =>
                              setNotice("検証ページのURLをコピーしました。"),
                            )
                            .catch(() =>
                              setError(
                                "URLをコピーできませんでした。トランザクションハッシュで照会できます。",
                              ),
                            );
                        }}
                      >
                        共有リンクをコピー ↗
                      </button>
                    )}
                  </div>
                )}
              </section>
              <section className={s.privacyCard}>
                <span className={s.privacyIcon}>
                  <Glyph kind="shield" />
                </span>
                <h3>公開するのは、確かめるための情報。</h3>
                <p>
                  生のCSI波形はチェーンに送信しません。証明と公開入力のみで、回路の制約を満たすことを検証します。
                </p>
                <Link href="/about">
                  検証で保証できる範囲を知る <span>↗</span>
                </Link>
              </section>
            </aside>
          </div>
          <section id="activity" className={`${s.card} ${s.activity}`}>
            <div className={s.cardHeading}>
              <div>
                <span className={s.tinyLabel}>TRANSACTION ACTIVITY</span>
                <h2>送信履歴・照会</h2>
              </div>
              <span className={s.historyNote}>履歴はこのブラウザに保存</span>
            </div>
            <form
              className={s.lookup}
              onSubmit={(e) => {
                e.preventDefault();
                if (!/^0x[\da-f]{64}$/i.test(lookup.trim())) {
                  setError(
                    "0xから始まる64桁のトランザクションハッシュを入力してください。",
                  );
                  return;
                }
                inspectTransaction(lookup.trim());
              }}
            >
              <label htmlFor="tx-hash" className={s.srOnly}>
                トランザクションハッシュ
              </label>
              <input
                id="tx-hash"
                placeholder="トランザクションハッシュを入力（0x…）"
                value={lookup}
                onChange={(e) => setLookup(e.target.value)}
              />
              <button type="submit" disabled={!chain?.connected}>
                照会 <Glyph kind="arrow" />
              </button>
            </form>
            <div className={s.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>トランザクション</th>
                    <th>ネットワーク</th>
                    <th>送信日時</th>
                    <th>検証記録</th>
                  </tr>
                </thead>
                <tbody>
                  {history.length ? (
                    history.map((item) => (
                      <tr key={item.hash}>
                        <td>
                          <span className={s.txIcon}>↗</span>
                          <code>{short(item.hash)}</code>
                        </td>
                        <td>Chain {item.chainId}</td>
                        <td>{new Date(item.date).toLocaleString("ja-JP")}</td>
                        <td>
                          <button
                            disabled={
                              item.chainId !== chain?.chainId ||
                              item.registry.toLowerCase() !==
                                chain?.registryAddress?.toLowerCase()
                            }
                            onClick={() => {
                              inspectTransaction(item.hash);
                            }}
                          >
                            チェーンで照会 ↗
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className={s.empty}>
                        <Glyph kind="chain" />
                        <strong>まだ送信した証明はありません</strong>
                        <span>
                          最初の証明を送信すると、ここから検証記録を確認できます。
                        </span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
          <footer className={s.footer}>
            <span>
              <span className={s.footerMark}>◈</span> CSI Proof{" "}
              <span className={s.footerDivider}>/</span> Verifiable sensing
              infrastructure
            </span>
            <Link href="/about">プライバシーと検証範囲 ↗</Link>
          </footer>
        </main>
      </div>
    </div>
  );
}
