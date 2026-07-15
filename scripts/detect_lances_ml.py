#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from sirbaa_pipeline import detect_lance_segments_ml, prepare_sensor_readings, read_csv_with_header_detection  # noqa: E402


def load_table(path: Path, time_col: str, temp_col: str) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = read_csv_with_header_detection(path)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Formato no soportado: {suffix}")
    return prepare_sensor_readings(df, time_col, temp_col)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detecta lances desde termómetro usando clustering simple.")
    parser.add_argument("input_file", type=Path, help="CSV/XLSX del termómetro")
    parser.add_argument("--time-col", default="reading_ts", help="Columna de fecha/hora")
    parser.add_argument("--temp-col", default="temp_c", help="Columna de temperatura")
    parser.add_argument("--rolling-window", type=int, default=5)
    parser.add_argument("--smoothing-window", type=int, default=3)
    parser.add_argument("--n-clusters", type=int, default=3)
    parser.add_argument("--merge-gap-minutes", type=int, default=15)
    parser.add_argument("--min-points", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("lances_detectados_ml.csv"))
    parser.add_argument("--points-output", type=Path, default=None)
    args = parser.parse_args()

    sensor = load_table(args.input_file, args.time_col, args.temp_col)
    result = detect_lance_segments_ml(
        sensor,
        time_col="reading_ts",
        temp_col="temp_c",
        n_clusters=args.n_clusters,
        rolling_window=args.rolling_window,
        smoothing_window=args.smoothing_window,
        merge_gap_minutes=args.merge_gap_minutes,
        min_segment_points=args.min_points,
    )

    result.segments.to_csv(args.output, index=False)
    if args.points_output:
        result.points.to_csv(args.points_output, index=False)

    print(result.segments.to_string(index=False) if not result.segments.empty else "No se detectaron lances.")
    print(f"\nGuardado: {args.output}")
    if args.points_output:
        print(f"Guardado: {args.points_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
