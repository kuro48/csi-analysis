"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ResearchAccess } from "../ResearchAccess";
import { operatorFetch } from "../operator-access";
import { API_BASE } from "../upload/constants";

const base = `${API_BASE}/api/v2/observations`;
const field = "mt-2 w-full rounded-lg border border-neutral-300 p-3";
export default function CapturePage() {
  const [patients, setPatients] = useState<{ id: string; label: string }[]>([]);
  const [ledger, setLedger] = useState("evm");
  const [proofProfile, setProofProfile] = useState("legacy");
  const [adaptiveAvailable, setAdaptiveAvailable] = useState<Record<string, boolean>>({});
  const [patient, setPatient] = useState("");
  const [time, setTime] = useState("");
  const [duration, setDuration] = useState(60);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState("");
  const id = useRef("");
  useEffect(() => {
    let active = true;
    fetch(`${base}/capabilities`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (active && data) setAdaptiveAvailable(data.adaptive4004 || {}); })
      .catch(() => {});
    fetch(`${base}/patients`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error("患者一覧を取得できません");
        return r.json();
      })
      .then((data) => {
        if (active) setPatients(data.patients);
      })
      .catch((error) => {
        if (active) setMessage(error.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function action(operation: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await operation();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function checked(response: Response) {
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "入力内容と運用者トークンを確認してください",
      );
    return data;
  }
  return (
    <main className="min-h-screen bg-neutral-50 px-5 py-10 text-neutral-900">
      <div className="mx-auto max-w-2xl space-y-6">
        <header>
          <p className="text-sm text-teal-700">CSI Care · Operator</p>
          <h1 className="mt-2 text-2xl font-bold">収集管理・デバッグ</h1>
          <p className="mt-3 text-sm leading-6 text-neutral-600">
            通常運用は収集端末から自動送信します。このフォームは保存済みCSIを使う動作確認用です。運用者トークンが必要です。
          </p>
        </header>
        <ResearchAccess />
        <form
          className="space-y-5 rounded-xl border bg-white p-6"
          onSubmit={(event) => {
            event.preventDefault();
            void action(async () => {
              if (!file) throw new Error("CSIを選択してください");
              if (!id.current) id.current = crypto.randomUUID();
              const data = new FormData();
              data.set("patient_id", patient);
              data.set("capture_id", id.current);
              data.set("observed_at", new Date(time).toISOString());
              data.set("duration_seconds", String(duration));
              data.set("file", file);
              data.set("ledger", ledger);
              data.set("proof_profile", proofProfile);
              const result = await checked(
                await operatorFetch(`${base}/captures`, {
                  method: "POST",
                  body: data,
                }),
              );
              setJob(result.id);
              setMessage(
                "収集を受け付けました。ワーカーが証明生成とチェーンへの記録を行います。",
              );
            });
          }}
        >
          <label className="block text-sm">
            証明の記録先
            <select
              className={field}
              value={ledger}
              onChange={(event) => {
                setLedger(event.target.value);
                setProofProfile("legacy");
                id.current = "";
              }}
            >
              <option value="evm">
                Ethereum（設定済みのSepolia / ローカル環境）
              </option>
              <option value="fabric">
                Hyperledger Fabric（コンソーシアム）
              </option>
            </select>
          </label>
          <label className="block text-sm">
            呼吸判定の方式
            <select
              className={field}
              value={proofProfile}
              onChange={(event) => {
                setProofProfile(event.target.value);
                id.current = "";
              }}
            >
              <option value="legacy">既存の解析方式（デバッグ・比較用）</option>
              <option value="adaptive4004" disabled={!adaptiveAvailable[ledger]}>
                Circom内で全候補から選択（最大4,004列）
              </option>
            </select>
            <span className="mt-2 block text-xs leading-5 text-neutral-500">
              {proofProfile === "adaptive4004"
                ? "サブキャリアの評価・選択から呼吸判定までを証明します。全列を処理するため、証明生成に時間がかかります。"
                : !adaptiveAvailable[ledger]
                  ? "全候補選択は、この記録先の検証回路を設定すると利用できます。"
                  : "保存済みCSIを両方式で処理して比較できます。"}
            </span>
          </label>
          <label className="block text-sm">
            患者
            <select
              required
              className={field}
              value={patient}
              onChange={(e) => {
                setPatient(e.target.value);
                id.current = "";
              }}
            >
              <option value="">患者を選択</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            className="text-sm text-teal-800 underline"
            onClick={() =>
              void action(async () => {
                const p = await checked(
                  await operatorFetch(`${base}/patients`, { method: "POST" }),
                );
                setPatients((old) => [...old, p]);
                setPatient(p.id);
                id.current = "";
              })
            }
          >
            表示用の患者IDを新規登録
          </button>
          {patient && (
            <p className="break-all font-mono text-xs text-neutral-500">
              収集端末の CSI_PATIENT_ID: {patient}
            </p>
          )}
          <label className="block text-sm">
            計測開始時刻（この端末の現地時刻）
            <input
              required
              type="datetime-local"
              step="1"
              className={field}
              value={time}
              onChange={(e) => {
                setTime(e.target.value);
                id.current = "";
              }}
            />
          </label>
          <label className="block text-sm">
            計測期間（秒）
            <input
              required
              type="number"
              min="1"
              max="3600"
              className={field}
              value={duration}
              onChange={(e) => {
                setDuration(Number(e.target.value));
                id.current = "";
              }}
            />
          </label>
          <label className="block text-sm">
            CSIファイル
            <input
              required
              type="file"
              accept=".csi"
              className={field}
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                id.current = "";
              }}
            />
          </label>
          <button
            disabled={busy}
            type="submit"
            className="w-full rounded-lg bg-teal-800 p-3 text-white disabled:opacity-40"
          >
            {busy ? "処理中…" : "デバッグ用CSIを収集キューへ送信"}
          </button>
        </form>
        {message && (
          <p role="status" className="rounded-lg border bg-white p-4 text-sm">
            {message}
          </p>
        )}
        {job && (
          <div className="space-y-3">
            <p className="break-all font-mono text-xs">収集ID: {job}</p>
            <button
              disabled={busy}
              className="text-sm text-teal-800 underline"
              onClick={() =>
                void action(async () => {
                  const data = await checked(
                    await operatorFetch(`${base}/captures/${job}`),
                  );
                  setMessage(
                    `状態: ${data.status} / 試行: ${data.attempts}${data.error ? " / 運用者による確認が必要です" : ""}`,
                  );
                })
              }
            >
              処理状態を確認
            </button>
          </div>
        )}
        <nav className="flex flex-wrap gap-5 text-sm text-teal-800">
          <Link href="/patients">第三者用の照会画面 →</Link>
          <Link href="/research">既存の解析モニター</Link>
          <Link href="/verify">証明デバッグ</Link>
        </nav>
      </div>
    </main>
  );
}
