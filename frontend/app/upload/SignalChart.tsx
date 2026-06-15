"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { SignalPoint } from "./types";

interface Props {
  title: string;
  points: SignalPoint[];
  color?: string;
}

function formatTimestamp(ms: number): string {
  const d = new Date(ms);
  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  const ss = d.getSeconds().toString().padStart(2, "0");
  const tenth = Math.floor(d.getMilliseconds() / 100);
  return `${hh}:${mm}:${ss}.${tenth}`;
}

export function SignalChart({ title, points, color = "#3b82f6" }: Props) {
  if (points.length === 0) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-4">
        <p className="mb-2 text-sm font-semibold text-neutral-700">{title}</p>
        <p className="text-xs text-neutral-400">データなし</p>
      </div>
    );
  }

  const hasAbsoluteTs = points[0]?.ts != null;

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4">
      <p className="mb-3 text-sm font-semibold text-neutral-700">{title}</p>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart
          data={points}
          margin={{ top: 4, right: 8, bottom: 16, left: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          {hasAbsoluteTs ? (
            <XAxis
              dataKey="ts"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatTimestamp}
              label={{
                value: "時刻",
                position: "insideBottomRight",
                offset: -4,
                fontSize: 10,
              }}
              tick={{ fontSize: 9 }}
              interval="preserveStartEnd"
            />
          ) : (
            <XAxis
              dataKey="time"
              tickFormatter={(v: number) => v.toFixed(1)}
              label={{
                value: "秒",
                position: "insideBottomRight",
                offset: -4,
                fontSize: 10,
              }}
              tick={{ fontSize: 10 }}
            />
          )}
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip
            formatter={(v) => [typeof v === "number" ? v.toFixed(3) : v, "振幅"]}
            labelFormatter={(l) =>
              hasAbsoluteTs
                ? formatTimestamp(Number(l))
                : `${Number(l).toFixed(2)} 秒`
            }
          />
          <Line
            type="monotone"
            dataKey="amplitude"
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
