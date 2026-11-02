"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../upload/constants";

type Patient = { id: string; label: string };
type Measurement = {
  id: string;
  observed_at: number;
  duration: number;
  status: string;
};
type Result = {
  status: string;
  isNormal?: boolean;
  observedAt?: number;
  durationSeconds?: number;
  debugInput?: boolean;
};
const selectClass =
  "mt-2 w-full min-w-0 rounded-xl border border-neutral-300 bg-white p-3 text-base text-neutral-900 focus:border-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-100 disabled:bg-neutral-100";
const dateLabel = (seconds: number) =>
  new Date(seconds * 1000).toLocaleString("ja-JP", { timeZoneName: "short" });

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v2/observations${path}`, {
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "照会できませんでした。時間をおいて再度お試しください。",
    );
  }
  return response.json();
}

export function PatientResults() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patient, setPatient] = useState("");
  const [day, setDay] = useState("");
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [measurement, setMeasurement] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState("一覧を読み込み中");
  const [error, setError] = useState("");
  const version = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    request<{ patients: Patient[] }>("/patients", { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setPatients(data.patients);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy("");
      });
    return () => {
      controller.abort();
    };
  }, []);

  async function choosePatient(id: string, date = day) {
    const current = ++version.current;
    setPatient(id);
    setMeasurements([]);
    setMeasurement("");
    setResult(null);
    setError("");
    if (!id) {
      setBusy("");
      return;
    }
    setBusy("計測時刻を読み込み中");
    try {
      let query = "";
      if (date) {
        const start = new Date(`${date}T00:00:00`);
        const end = new Date(start);
        end.setDate(end.getDate() + 1);
        query = `?start_at=${Math.floor(start.getTime() / 1000)}&end_at=${Math.floor(end.getTime() / 1000)}`;
      }
      const data = await request<{ measurements: Measurement[] }>(
        `/patients/${id}/measurements${query}`,
      );
      if (current === version.current) setMeasurements(data.measurements);
    } catch (failure) {
      if (current === version.current) setError((failure as Error).message);
    } finally {
      if (current === version.current) setBusy("");
    }
  }

  async function verify() {
    const current = ++version.current;
    setResult(null);
    setError("");
    setBusy("記録された証明を検証しています");
    try {
      const data = await request<Result>(
        `/measurements/${measurement}/verify`,
        { method: "POST" },
      );
      if (current !== version.current) return;
      if (data.status === "verified" && typeof data.isNormal === "boolean")
        setResult(data);
      else
        setError(
          data.status === "failed"
            ? "この計測の処理に失敗しています。運用者に確認してください。"
            : "証明の記録またはブロックの確定を待っています。時間をおいて再照会してください。",
        );
    } catch (failure) {
      if (current === version.current) setError((failure as Error).message);
    } finally {
      if (current === version.current) setBusy("");
    }
  }

  const selected = measurements.find((item) => item.id === measurement);
  return (
    <main className="min-h-screen bg-[#f5f8f6] px-5 py-8 text-[#193e34] sm:px-8">
      <div className="mx-auto max-w-3xl">
        <header className="flex items-center justify-between border-b border-[#dce6df] pb-5">
          <Link
            href="/patients"
            className="text-xl font-semibold tracking-tight"
          >
            CSI <span className="font-normal">Care</span>
          </Link>
          <span className="rounded-full bg-white px-3 py-1 text-xs text-neutral-600">
            呼吸判定の照会
          </span>
        </header>
        <div className="py-10 sm:py-14">
          <p className="text-xs font-semibold tracking-widest text-teal-700">
            PATIENT RESULTS
          </p>
          <h1 className="mt-3 text-3xl font-semibold leading-tight sm:text-4xl">
            その時刻の呼吸判定を、
            <br />
            確かめる。
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-7 text-neutral-600">
            患者と計測時刻を選んでください。記録された証明を検証した後に、呼吸判定結果を表示します。
          </p>
        </div>
        <section
          aria-label="計測の選択"
          className="rounded-2xl border border-[#dce6df] bg-white p-6 shadow-sm sm:p-8"
        >
          <label className="mb-5 block max-w-xs text-sm font-semibold">
            計測日で絞り込む（任意）
            <input
              type="date"
              aria-label="計測日で絞り込む"
              value={day}
              className={selectClass}
              onChange={(event) => {
                setDay(event.target.value);
                void choosePatient(patient, event.target.value);
              }}
            />
          </label>
          <div className="grid gap-6 sm:grid-cols-2">
            <label className="min-w-0 text-sm font-semibold">
              患者
              <select
                aria-label="患者"
                value={patient}
                className={selectClass}
                onChange={(event) => void choosePatient(event.target.value)}
              >
                <option value="">患者を選択</option>
                {patients.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-0 text-sm font-semibold">
              計測開始時刻
              <select
                aria-label="計測開始時刻"
                value={measurement}
                disabled={!patient || !measurements.length}
                className={selectClass}
                onChange={(event) => {
                  version.current++;
                  setMeasurement(event.target.value);
                  setResult(null);
                  setError("");
                  setBusy("");
                }}
              >
                <option value="">時刻を選択</option>
                {measurements.map((item) => (
                  <option key={item.id} value={item.id}>
                    {dateLabel(item.observed_at)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selected && (
            <p className="mt-4 text-xs text-neutral-500">
              選択した計測期間：{selected.duration}秒間
            </p>
          )}
          {!busy && !error && !patients.length && (
            <p className="mt-4 text-sm text-neutral-600">
              登録された患者はまだいません。
            </p>
          )}
          {patient && !busy && !error && !measurements.length && (
            <p className="mt-4 text-sm text-neutral-600">
              この患者の計測はまだありません。
            </p>
          )}
          <button
            type="button"
            disabled={!measurement || !!busy}
            onClick={() => void verify()}
            className="mt-7 w-full rounded-xl bg-[#245847] px-5 py-4 text-sm font-semibold text-white hover:bg-[#193e34] disabled:bg-neutral-200 disabled:text-neutral-500"
          >
            {busy || "証明を検証して結果を取得"}
          </button>
        </section>
        <div aria-live="polite" aria-busy={!!busy}>
          {error && (
            <p
              role="alert"
              className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-900"
            >
              {error}
            </p>
          )}
          {result && (
            <section
              aria-label="呼吸判定結果"
              className={`mt-6 rounded-2xl border p-7 sm:p-9 ${result.isNormal ? "border-teal-200 bg-teal-50" : "border-amber-200 bg-amber-50"}`}
            >
              <p className="text-xs font-semibold tracking-widest text-neutral-600">
                証明の検証が完了しました
              </p>
              <h2 className="mt-4 text-3xl font-semibold">
                {result.isNormal
                  ? "判定条件を満たしています"
                  : "判定条件を満たしていません"}
              </h2>
              <p className="mt-3 font-mono text-sm">
                isNormal: {String(result.isNormal)}
              </p>
              <p className="mt-5 text-sm text-neutral-600">
                {result.observedAt && dateLabel(result.observedAt)} から{" "}
                {result.durationSeconds}秒間（収集側の指定期間）
              </p>
              <p className="mt-3 text-xs leading-6 text-neutral-600">
                設定された周波数帯域と狭帯域条件による判定です。証明の有効性と判定結果は別の情報です。
              </p>
              {result.debugInput && (
                <p className="mt-4 rounded-lg border border-amber-300 bg-white/70 p-3 text-sm leading-6 text-amber-950">
                  デバッグ計測です。短い入力の補完を許可した検証先を使用しています。通常運用の計測条件を満たすことは確認していません。
                </p>
              )}
            </section>
          )}
        </div>
        <footer className="mt-9 flex flex-wrap justify-between gap-3 border-t border-[#dce6df] py-5 text-xs leading-6 text-neutral-500">
          <p>
            患者は表示用IDで識別しています。計測時刻は端末のタイムゾーンで表示します。
          </p>
          <Link className="underline" href="/capture">
            収集管理・デバッグ
          </Link>
        </footer>
      </div>
    </main>
  );
}
