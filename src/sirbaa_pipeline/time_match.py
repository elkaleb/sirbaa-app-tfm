from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd


def parse_clock_value(value) -> pd.Timestamp:
    """Parse values like 7.46, 11.08, 14:40 or 7:46 into a timestamp-less time.

    Returns a pandas NaT when parsing fails.
    """
    if pd.isna(value):
        return pd.NaT

    text = str(value).strip()
    if not text:
        return pd.NaT

    # Already looks like HH:MM or HH:MM:SS
    if ":" in text:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.notna(parsed):
            return pd.Timestamp(year=2000, month=1, day=1, hour=parsed.hour, minute=parsed.minute, second=parsed.second)
        return parsed

    # Values from the field often arrive as HH.MM (minutes after the dot)
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", text)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return pd.Timestamp(year=2000, month=1, day=1, hour=hh, minute=mm)

    # Fallback: try to interpret as numeric HH.MM and convert the decimal part to minutes.
    try:
        num = float(text)
    except Exception:
        return pd.NaT

    hh = int(num)
    mm = round((num - hh) * 100)
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return pd.Timestamp(year=2000, month=1, day=1, hour=hh, minute=mm)
    return pd.NaT


def _normalize_header_token(value) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^\w]+", "", text, flags=re.UNICODE)
    return text


def detect_csv_header_row(path: str | Path, expected_columns: list[str] | tuple[str, ...] | None = None, max_rows: int = 20, delimiter: str = ",") -> int:
    """Return the zero-based row index of the CSV header.

    This is useful when the first row is a legend/title and the real header
    appears a few rows below.
    """
    expected = {_normalize_header_token(col) for col in (expected_columns or []) if str(col).strip()}

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        for row_idx, row in enumerate(reader):
            if row_idx >= max_rows:
                break

            values = [cell.strip() for cell in row if cell and cell.strip()]
            if not values:
                continue

            normalized = {_normalize_header_token(cell) for cell in values}

            if expected:
                overlap = len(normalized & expected)
                if overlap >= max(1, min(2, len(expected) // 4)):
                    return row_idx
            else:
                # Heuristic: headers usually have several cells and at least
                # one textual token.
                if len(values) >= 3 and any(any(ch.isalpha() for ch in cell) for cell in values):
                    return row_idx

    return 0


def detect_csv_delimiter(path: str | Path, delimiters: tuple[str, ...] = (",", ";", "\t", "|"), max_rows: int = 20) -> str:
    """Detect the most likely delimiter in a CSV-like file.

    Some sensor exports use semicolon-separated rows even when the file has a
    `.csv` extension. This chooses the delimiter that produces the most stable
    multi-column rows in the first lines.
    """
    path = Path(path)
    lines: list[str] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for _, line in zip(range(max_rows), fh):
            if line.strip():
                lines.append(line.rstrip("\n\r"))

    if not lines:
        return ","

    best_delimiter = ","
    best_score = -1.0
    for delimiter in delimiters:
        counts = [len(next(csv.reader([line], delimiter=delimiter))) for line in lines]
        multi_counts = [count for count in counts if count > 1]
        if not multi_counts:
            score = 0.0
        else:
            # Prefer delimiters that create multiple columns consistently.
            score = (sum(multi_counts) / len(counts)) + (len(multi_counts) / len(counts))
            if len(set(multi_counts)) == 1:
                score += 1.0
        if score > best_score:
            best_score = score
            best_delimiter = delimiter

    return best_delimiter


def read_csv_with_header_detection(path: str | Path, expected_columns: list[str] | tuple[str, ...] | None = None, max_rows: int = 20, delimiter: str = ",", **kwargs) -> pd.DataFrame:
    """Read a CSV while automatically skipping a leading legend row if present."""
    header_row = detect_csv_header_row(path, expected_columns=expected_columns, max_rows=max_rows, delimiter=delimiter)
    return pd.read_csv(path, header=header_row, delimiter=delimiter, **kwargs)


def csv_has_header_in_first_row(path: str | Path, expected_columns: list[str] | tuple[str, ...] | None = None, delimiter: str = ",") -> bool:
    return detect_csv_header_row(path, expected_columns=expected_columns, delimiter=delimiter) == 0


def drop_rows_missing_column(df: pd.DataFrame, column: str) -> tuple[pd.DataFrame, int]:
    """Drop rows where a column is empty/blank and return the cleaned frame plus removed count."""
    if column not in df.columns:
        return df.copy(), 0

    out = df.copy()
    series = out[column].astype("string").str.strip()
    mask = series.notna() & (series != "")
    cleaned = out.loc[mask].copy()
    removed = int((~mask).sum())
    return cleaned, removed


def drop_empty_columns(df: pd.DataFrame, preserve_columns: list[str] | tuple[str, ...] | set[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Drop columns that are completely empty/blank and return the cleaned frame plus removed names."""
    preserve = set(preserve_columns or [])
    kept = []
    removed = []

    for column in df.columns:
        if column in preserve:
            kept.append(column)
            continue

        series = df[column]
        if series.notna().any():
            non_empty = series.astype("string").str.strip().replace({"<NA>": pd.NA, "nan": pd.NA, "None": pd.NA})
            if non_empty.notna().any():
                kept.append(column)
                continue

        removed.append(column)

    return df[kept].copy(), removed


def build_lance_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["fecha"] = pd.to_datetime(out["fecha"], dayfirst=True, errors="coerce").dt.normalize()
    start_times = out["hr_inical"].apply(parse_clock_value)
    end_times = out["hr_fincal"].apply(parse_clock_value)
    out["lance_inicio_ts"] = out["fecha"] + (start_times - pd.Timestamp(year=2000, month=1, day=1))
    out["lance_fin_ts"] = out["fecha"] + (end_times - pd.Timestamp(year=2000, month=1, day=1))
    out = out.sort_values(["lance_inicio_ts", "lance_fin_ts"], na_position="last").reset_index(drop=True)
    return out


def parse_lance_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    return build_lance_timestamps(df)


def prepare_sensor_readings(df: pd.DataFrame, time_col: str, temp_col: str) -> pd.DataFrame:
    out = df.copy()
    out = out.rename(columns={time_col: "reading_ts", temp_col: "temp_c"})
    out["reading_ts"] = pd.to_datetime(out["reading_ts"], errors="coerce")
    if out["temp_c"].dtype == object:
        out["temp_c"] = (
            out["temp_c"]
            .astype(str)
            .str.strip()
            .str.replace(",", ".", regex=False)
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
        )
    out["temp_c"] = pd.to_numeric(out["temp_c"], errors="coerce")
    return out[["reading_ts", "temp_c"] + [c for c in out.columns if c not in {"reading_ts", "temp_c"}]]


def match_sensor_to_lances(lances: pd.DataFrame, sensor: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, lance in lances.iterrows():
        start = lance["lance_inicio_ts"]
        end = lance["lance_fin_ts"]
        if pd.isna(start) or pd.isna(end):
            rows.append({
                "clave_viaje": lance.get("clave_viaje"),
                "clave_lance": lance.get("clave_lance"),
                "tfm_promedio": pd.NA,
                "tfm_min": pd.NA,
                "tfm_max": pd.NA,
                "tfm_n_lecturas": 0,
                "tfm_match_status": "hora_invalida",
            })
            continue
        if end < start:
            end = end + pd.Timedelta(days=1)
        subset = sensor[(sensor["reading_ts"] >= start) & (sensor["reading_ts"] <= end)]
        valid_subset = subset.dropna(subset=["temp_c"])
        rows.append({
            "clave_viaje": lance.get("clave_viaje"),
            "clave_lance": lance.get("clave_lance"),
            "lance_inicio_ts": start,
            "lance_fin_ts": end,
            "tfm_promedio": valid_subset["temp_c"].mean() if len(valid_subset) else pd.NA,
            "tfm_mediana": valid_subset["temp_c"].median() if len(valid_subset) else pd.NA,
            "tfm_min": valid_subset["temp_c"].min() if len(valid_subset) else pd.NA,
            "tfm_max": valid_subset["temp_c"].max() if len(valid_subset) else pd.NA,
            "tfm_delta": (valid_subset["temp_c"].max() - valid_subset["temp_c"].min()) if len(valid_subset) else pd.NA,
            "tfm_std": valid_subset["temp_c"].std(ddof=0) if len(valid_subset) else pd.NA,
            "tfm_q1": valid_subset["temp_c"].quantile(0.25) if len(valid_subset) else pd.NA,
            "tfm_q3": valid_subset["temp_c"].quantile(0.75) if len(valid_subset) else pd.NA,
            "tfm_iqr": (valid_subset["temp_c"].quantile(0.75) - valid_subset["temp_c"].quantile(0.25)) if len(valid_subset) else pd.NA,
            "tfm_n_lecturas": int(len(valid_subset)),
            "tfm_match_status": "ok" if len(valid_subset) else "sin_lecturas",
        })
    return pd.DataFrame(rows)


def sensor_readings_within_lance(lance: pd.Series, sensor: pd.DataFrame) -> pd.DataFrame:
    """Return the sensor rows that fall inside a lance interval."""
    start = lance.get("lance_inicio_ts")
    end = lance.get("lance_fin_ts")
    if pd.isna(start) or pd.isna(end):
        return sensor.iloc[0:0].copy()
    if end < start:
        end = end + pd.Timedelta(days=1)
    subset = sensor[(sensor["reading_ts"] >= start) & (sensor["reading_ts"] <= end)].copy()
    return subset.sort_values("reading_ts")
