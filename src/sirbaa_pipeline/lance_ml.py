from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class LanceMLResult:
    points: pd.DataFrame
    segments: pd.DataFrame
    meta: dict[str, Any]


def _low_quantile_threshold(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 3 or values.nunique() < 2:
        return None
    return float(values.quantile(0.25))


def _high_quantile_threshold(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 3 or values.nunique() < 2:
        return None
    return float(values.quantile(0.75))


def _add_false_lance_guidance(segments: pd.DataFrame, min_segment_points: int) -> pd.DataFrame:
    """Add explainable, data-adaptive warnings for possible false lances.

    These are analyst hints, not automatic labels. Thresholds are based on the
    distribution of the current file's detected segments, so they adapt to each
    trip/sensor instead of relying on fixed temperature cutoffs.
    """
    if segments.empty:
        return segments

    out = segments.copy()
    duration_low = _low_quantile_threshold(out["duration_min"])
    delta_low = _low_quantile_threshold(out["delta_temp"])
    std_low = _low_quantile_threshold(out["std_temp"])
    std_high = _high_quantile_threshold(out["std_temp"])
    iqr_low = _low_quantile_threshold(out["iqr_temp"])
    contrast_low = _low_quantile_threshold(out["env_contrast_temp"])

    risk_rows: list[str] = []
    flags_rows: list[str] = []
    hint_rows: list[str] = []

    for _, seg in out.iterrows():
        flags: list[str] = []
        score = 0

        duration = seg.get("duration_min")
        n_points = seg.get("n_points")
        delta = seg.get("delta_temp")
        std = seg.get("std_temp")
        iqr = seg.get("iqr_temp")
        contrast = seg.get("env_contrast_temp")

        if pd.notna(duration) and duration_low is not None and duration <= duration_low:
            flags.append("duración corta vs otros segmentos")
            score += 1
        if pd.notna(n_points) and n_points <= max(min_segment_points, int(round(min_segment_points * 1.5))):
            flags.append("pocas lecturas para sostener el lance")
            score += 1
        if pd.notna(contrast) and contrast_low is not None and contrast <= contrast_low:
            flags.append("poco contraste térmico contra el entorno")
            score += 2
        if pd.notna(contrast) and contrast <= 0:
            flags.append("segmento no está más frío que su entorno")
            score += 2
        if pd.notna(delta) and delta_low is not None and delta <= delta_low:
            flags.append("delta térmico bajo dentro del segmento")
            score += 1
        if pd.notna(std) and std_low is not None and std <= std_low:
            flags.append("baja variabilidad interna; posible tramo plano")
            score += 1
        elif pd.notna(std) and std_high is not None and std >= std_high:
            flags.append("alta variabilidad interna; posible mezcla de eventos")
            score += 1
        if pd.notna(iqr) and iqr_low is not None and iqr <= iqr_low:
            flags.append("IQR bajo; señal térmica poco diferenciada")
            score += 1

        if score >= 5:
            risk = "alto"
            hint = "Revisar como posible falso lance: acumula varias señales débiles o contradictorias."
        elif score >= 3:
            risk = "medio"
            hint = "Revisar visualmente: hay señales que podrían indicar falso positivo o mala delimitación."
        elif score >= 1:
            risk = "bajo"
            hint = "Tiene alguna alerta menor; validar contra gráfica/observador."
        else:
            risk = "sin_alertas"
            hint = "Sin alertas estadísticas relevantes bajo los parámetros actuales."

        risk_rows.append(risk)
        flags_rows.append("; ".join(flags) if flags else "sin alertas")
        hint_rows.append(hint)

    out["false_lance_risk"] = risk_rows
    out["false_lance_flags"] = flags_rows
    out["validation_hint"] = hint_rows
    return out


def detect_lance_segments_ml(
    sensor: pd.DataFrame,
    time_col: str = "reading_ts",
    temp_col: str = "temp_c",
    n_clusters: int = 3,
    rolling_window: int = 5,
    smoothing_window: int = 3,
    merge_gap_minutes: int = 15,
    context_window_minutes: int = 60,
    min_segment_points: int = 5,
) -> LanceMLResult:
    """Detect likely lance segments from temperature series.

    Strategy:
    - smooth temperature with a rolling mean,
    - cluster point features with KMeans (2 clusters),
    - select the cluster with the lower smoothed temperature as lance,
    - collapse contiguous lance points into segments.
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "scikit-learn no está instalado. Ejecuta el bootstrap del proyecto o instala requirements.txt."
        ) from exc

    if time_col not in sensor.columns or temp_col not in sensor.columns:
        raise ValueError(f"Se requieren las columnas '{time_col}' y '{temp_col}'.")

    df = sensor[[time_col, temp_col] + [c for c in sensor.columns if c not in {time_col, temp_col}]].copy()
    df = df.rename(columns={time_col: "reading_ts", temp_col: "temp_c"})
    df["reading_ts"] = pd.to_datetime(df["reading_ts"], errors="coerce")
    df["temp_c"] = pd.to_numeric(df["temp_c"], errors="coerce")
    df = df.dropna(subset=["reading_ts", "temp_c"]).sort_values("reading_ts").reset_index(drop=True)

    if df.empty:
        return LanceMLResult(points=df, segments=pd.DataFrame(), meta={"status": "empty"})

    roll = max(2, int(rolling_window))
    smooth = max(1, int(smoothing_window))

    df["temp_smooth"] = df["temp_c"].rolling(roll, center=True, min_periods=max(2, roll // 2)).mean()
    df["temp_smooth"] = df["temp_smooth"].bfill().ffill().fillna(df["temp_c"])
    df["temp_diff"] = df["temp_smooth"].diff().abs().fillna(0)
    df["temp_std"] = df["temp_c"].rolling(roll, center=True, min_periods=max(2, roll // 2)).std()
    df["temp_std"] = df["temp_std"].bfill().ffill().fillna(0)

    features = df[["temp_smooth"]].to_numpy()
    scaled = StandardScaler().fit_transform(features)

    cluster_count = min(max(2, int(n_clusters)), len(df))
    model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
    df["ml_cluster"] = model.fit_predict(scaled)

    cluster_means = df.groupby("ml_cluster", as_index=True)["temp_smooth"].mean().sort_values()
    lance_cluster = int(cluster_means.index[0])
    raw_is_lance = df["ml_cluster"] == lance_cluster
    df["is_lance_ml_raw"] = raw_is_lance
    df["is_lance_ml"] = (
        raw_is_lance.astype(int)
        .rolling(smooth, center=True, min_periods=1)
        .mean()
        .ge(0.5)
    )

    cadence = df["reading_ts"].diff().median()
    if pd.isna(cadence):
        cadence = pd.Timedelta(minutes=5)
    gap_limit = cadence * 2.5

    segment_break = df["is_lance_ml"].ne(df["is_lance_ml"].shift(fill_value=False)) | (
        df["reading_ts"].diff() > gap_limit
    )
    df["segment_id"] = segment_break.cumsum().where(df["is_lance_ml"], pd.NA)

    raw_segments = (
        df[df["is_lance_ml"]]
        .groupby("segment_id", dropna=True)
        .agg(
            start_ts=("reading_ts", "min"),
            end_ts=("reading_ts", "max"),
        )
        .reset_index(drop=True)
        .sort_values(["start_ts", "end_ts"], na_position="last")
    )

    merged_intervals = []
    merge_gap = pd.Timedelta(minutes=max(0, int(merge_gap_minutes)))

    for _, seg in raw_segments.iterrows():
        start_ts = seg["start_ts"]
        end_ts = seg["end_ts"]
        if not merged_intervals:
            merged_intervals.append({"start_ts": start_ts, "end_ts": end_ts})
            continue

        last = merged_intervals[-1]
        if start_ts - last["end_ts"] <= merge_gap:
            last["end_ts"] = max(last["end_ts"], end_ts)
        else:
            merged_intervals.append({"start_ts": start_ts, "end_ts": end_ts})

    final_rows = []
    df["segment_id"] = pd.NA
    df["is_lance_ml"] = False
    context_window = pd.Timedelta(minutes=max(0, int(context_window_minutes)))

    for idx, interval in enumerate(merged_intervals, start=1):
        mask = (df["reading_ts"] >= interval["start_ts"]) & (df["reading_ts"] <= interval["end_ts"])
        interval_points = df.loc[mask].copy()
        if interval_points.empty:
            continue

        df.loc[mask, "segment_id"] = idx
        df.loc[mask, "is_lance_ml"] = True
        q1_temp = float(interval_points["temp_c"].quantile(0.25))
        q3_temp = float(interval_points["temp_c"].quantile(0.75))
        mean_temp = float(interval_points["temp_c"].mean())
        before_mask = (df["reading_ts"] >= interval["start_ts"] - context_window) & (df["reading_ts"] < interval["start_ts"])
        after_mask = (df["reading_ts"] > interval["end_ts"]) & (df["reading_ts"] <= interval["end_ts"] + context_window)
        before_points = df.loc[before_mask].copy()
        after_points = df.loc[after_mask].copy()
        context_points = pd.concat([before_points, after_points], ignore_index=True)
        before_mean = float(before_points["temp_c"].mean()) if not before_points.empty else pd.NA
        after_mean = float(after_points["temp_c"].mean()) if not after_points.empty else pd.NA
        context_mean = float(context_points["temp_c"].mean()) if not context_points.empty else pd.NA
        contrast_temp = context_mean - mean_temp if not pd.isna(context_mean) else pd.NA

        final_rows.append(
            {
                "segment_id": idx,
                "start_ts": interval["start_ts"],
                "end_ts": interval["end_ts"],
                "n_points": int(len(interval_points)),
                "mean_temp": mean_temp,
                "median_temp": float(interval_points["temp_c"].median()),
                "min_temp": float(interval_points["temp_c"].min()),
                "max_temp": float(interval_points["temp_c"].max()),
                "delta_temp": float(interval_points["temp_c"].max() - interval_points["temp_c"].min()),
                "std_temp": float(interval_points["temp_c"].std(ddof=0)),
                "q1_temp": q1_temp,
                "q3_temp": q3_temp,
                "iqr_temp": q3_temp - q1_temp,
                "env_mean_temp": context_mean,
                "env_contrast_temp": contrast_temp,
                "env_before_mean_temp": before_mean,
                "env_after_mean_temp": after_mean,
                "env_n_points": int(len(context_points)),
                "mean_temp_smooth": float(interval_points["temp_smooth"].mean()),
            }
        )

    segments = pd.DataFrame(final_rows)

    if not segments.empty:
        segments["duration_min"] = (
            (segments["end_ts"] - segments["start_ts"]).dt.total_seconds() / 60.0
        )
        segments["duration_hhmm"] = segments["duration_min"].apply(
            lambda minutes: f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"
        )
        segments = segments[segments["n_points"] >= min_segment_points].copy()
        segments = segments.sort_values(["start_ts", "end_ts"], na_position="last").reset_index(drop=True)
        segments["segment_id"] = range(1, len(segments) + 1)
        segments["segment_label"] = [f"Lance {i + 1}" for i in range(len(segments))]
        segments = _add_false_lance_guidance(segments, min_segment_points=min_segment_points)

    df["segment_id"] = pd.NA
    df["is_lance_ml"] = False
    if not segments.empty:
        for _, seg in segments.iterrows():
            mask = (df["reading_ts"] >= seg["start_ts"]) & (df["reading_ts"] <= seg["end_ts"])
            df.loc[mask, "segment_id"] = int(seg["segment_id"])
            df.loc[mask, "is_lance_ml"] = True

    meta = {
        "status": "ok",
        "lance_cluster": lance_cluster,
        "cluster_means": {int(k): float(v) for k, v in cluster_means.items()},
        "n_clusters": cluster_count,
        "rows_used": int(len(df)),
        "rolling_window": roll,
        "smoothing_window": smooth,
        "context_window_minutes": int(context_window_minutes),
        "min_segment_points": int(min_segment_points),
    }

    return LanceMLResult(points=df, segments=segments, meta=meta)
