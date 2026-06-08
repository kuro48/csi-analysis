"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts";
import type { SpectrumPoint } from "./types";
import { BREATHING_BAND_HZ } from "./constants";

interface Props {
  title: string;
  points: SpectrumPoint[];
}

export function SpectrumChart({ title, points }: Props) {
  if (points.length === 0) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-4">
        <p className="mb-2 text-sm font-semibold text-neutral-700">{title}</p>
        <p className="text-xs text-neutral-400">データなし</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4">
      <p className="mb-3 text-sm font-semibold text-neutral-700">{title}</p>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="frequency"
            tickFormatter={(v: number) => v.toFixed(2)}
            label={{ value: "Hz", position: "insideBottomRight", offset: -4, fontSize: 10 }}
            tick={{ fontSize: 10 }}
          />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip
            formatter={(v) => [typeof v === "number" ? v.toFixed(2) : v, "振幅"]}
            labelFormatter={(l) => `${Number(l).toFixed(3)} Hz`}
          />
          <ReferenceArea
            x1={BREATHING_BAND_HZ[0]}
            x2={BREATHING_BAND_HZ[1]}
            fill="#bbf7d0"
            fillOpacity={0.4}
            label={{ value: "呼吸帯域", position: "top", fontSize: 9, fill: "#16a34a" }}
          />
          <Line
            type="monotone"
            dataKey="magnitude"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
