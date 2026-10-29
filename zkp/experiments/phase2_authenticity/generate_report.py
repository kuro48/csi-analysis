#!/usr/bin/env python3
"""Generate Markdown and dependency-free SVG summaries from method_runs.csv."""

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


def number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def summarize(rows: list[dict[str, str]]) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "completed":
            grouped[row["method"]].append(row)
    result = {}
    for method, items in grouped.items():
        errors = [value for item in items if (value := number(item.get("absolute_error_bpm"))) is not None]
        signed = [value for item in items if (value := number(item.get("signed_error_bpm"))) is not None]
        times = [value for item in items if (value := number(item.get("total_ms"))) is not None]
        result[method] = {
            "runs": len(items),
            "evaluated": len(errors),
            "mae": statistics.fmean(errors) if errors else None,
            "rmse": math.sqrt(statistics.fmean(value * value for value in signed)) if signed else None,
            "within_1": sum(value <= 1 for value in errors) / len(errors) if errors else None,
            "within_2": sum(value <= 2 for value in errors) / len(errors) if errors else None,
            "median_total_ms": statistics.median(times) if times else None,
        }
    return result


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "—"
    return str(value) if isinstance(value, int) else f"{value:.{digits}f}"


def make_svg(summary: dict[str, dict[str, float | int | None]], path: Path) -> None:
    width, height = 920, 420
    panels = [("MAE (BPM)", "mae", 60), ("Median total time (ms)", "median_total_ms", 500)]
    colors = ["#2563eb", "#059669", "#dc2626", "#7c3aed"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#171717}'
        ".title{font-size:17px;font-weight:700}.label{font-size:12px}"
        ".value{font-size:12px;font-weight:600}</style>",
    ]
    for title, key, left in panels:
        methods = [method for method, values in summary.items() if values[key] is not None]
        values = [float(summary[m][key] or 0) for m in methods]
        maximum = max(values, default=1) or 1
        parts.append(f'<text class="title" x="{left}" y="36">{title}</text>')
        for index, (method, value) in enumerate(zip(methods, values)):
            y = 70 + index * 72
            bar_width = value / maximum * 310
            parts.append(f'<text class="label" x="{left}" y="{y}">{method}</text>')
            parts.append(
                f'<rect x="{left}" y="{y + 10}" width="{bar_width:.1f}" height="25" '
                f'rx="4" fill="{colors[index % len(colors)]}"/>'
            )
            parts.append(
                f'<text class="value" x="{left + bar_width + 8:.1f}" '
                f'y="{y + 28}">{value:.3f}</text>'
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=Path(__file__).parent / "results" / "method_runs.csv"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    markdown = [
        "# Hybrid breathing benchmark report",
        "",
        "| Method | Runs | With ground truth | MAE BPM | RMSE BPM | Within 1 BPM | Within 2 BPM | Median total ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, values in summary.items():
        within_1 = None if values["within_1"] is None else f"{float(values['within_1']) * 100:.1f}%"
        within_2 = None if values["within_2"] is None else f"{float(values['within_2']) * 100:.1f}%"
        markdown.append(
            f"| {method} | {values['runs']} | {values['evaluated']} | {fmt(values['mae'])} | "
            f"{fmt(values['rmse'])} | {within_1 or '—'} | {within_2 or '—'} | "
            f"{fmt(values['median_total_ms'])} |"
        )
    (args.output_dir / "REPORT.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    make_svg(summary, args.output_dir / "comparison.svg")
    print(f"Wrote {args.output_dir / 'REPORT.md'}")
    print(f"Wrote {args.output_dir / 'comparison.svg'}")


if __name__ == "__main__":
    main()
