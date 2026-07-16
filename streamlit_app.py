from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import altair as alt

sys.path.append(str(Path(__file__).resolve().parent / "src"))
from sirbaa_pipeline import (  # noqa: E402
    build_lance_timestamps,
    detect_csv_header_row,
    detect_csv_delimiter,
    drop_empty_columns,
    drop_rows_missing_column,
    detect_lance_segments_ml,
    match_sensor_to_lances,
    normalize_date_series,
    prepare_sensor_readings,
    sensor_readings_within_lance,
)

st.set_page_config(page_title="SIRBAA Sensores", layout="wide")
st.title("SIRBAA Sensores — TFM v1")
st.caption("Carga lances y sensores, detecta encabezados raros y calcula TFM por intervalo.")

if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "ml_analysis" not in st.session_state:
    st.session_state.ml_analysis = None
if "ml_signature" not in st.session_state:
    st.session_state.ml_signature = None
if "ml_selected_segment_id" not in st.session_state:
    st.session_state.ml_selected_segment_id = None
if "ml_result_version" not in st.session_state:
    st.session_state.ml_result_version = 0
if "observed_selected_lance_idx" not in st.session_state:
    st.session_state.observed_selected_lance_idx = 0
if "ml_segment_validation" not in st.session_state:
    st.session_state.ml_segment_validation = {}
if "exclude_rejected_ml_segments" not in st.session_state:
    st.session_state.exclude_rejected_ml_segments = True

LANCE_EXPECTED_COLS = ["clave_viaje", "clave_lance", "fecha", "hr_inical", "hr_fincal", "hr_inicob", "hr_fincob", "Hora_1", "Hora_2", "Hora_3", "Hora_4"]
LANCE_REQUIRED_ID_COLS = ["clave_lance"]
TIME_AXIS = alt.Axis(format="%d %b\n%H:%M", title="Fecha y hora")
APP_DIR = Path(__file__).resolve().parent
PRESETS_DIR = APP_DIR / "data" / "presets"
ML_DEFAULTS = {
    "n_clusters": 3,
    "rolling_window": 5,
    "smoothing_window": 3,
    "merge_gap_minutes": 15,
    "context_window_minutes": 60,
    "min_segment_points": 5,
}

for param_name, default_value in ML_DEFAULTS.items():
    st.session_state.setdefault(f"ml_{param_name}", default_value)
st.session_state.setdefault("loaded_preset_name", "")

COLUMN_HELP = {
    "segment_label": "Etiqueta consecutiva del lance detectado por ML para facilitar revisión visual.",
    "segment_id": "Identificador interno del segmento detectado por ML; permite cruzar gráfica, tabla y auditoría de lecturas.",
    "start_ts": "Fecha y hora en que inicia el segmento detectado por ML.",
    "end_ts": "Fecha y hora en que termina el segmento detectado por ML.",
    "duration_hhmm": "Duración del segmento en formato horas:minutos; sirve para revisar si el lance es razonable.",
    "duration_min": "Duración total en minutos; ayuda a detectar segmentos demasiado cortos o demasiado largos.",
    "n_points": "Número de lecturas del sensor dentro del segmento ML; más puntos suelen dar estadísticas más confiables.",
    "mean_temp": "Temperatura promedio del segmento ML; equivalente a la TFM estimada para el lance detectado.",
    "median_temp": "Temperatura mediana del segmento ML; es menos sensible a valores extremos que el promedio.",
    "min_temp": "Temperatura mínima registrada dentro del segmento.",
    "max_temp": "Temperatura máxima registrada dentro del segmento.",
    "delta_temp": "Diferencia entre temperatura máxima y mínima; ayuda a identificar segmentos inestables o transiciones.",
    "std_temp": "Desviación estándar de temperatura; mide variabilidad interna del segmento y puede señalar falsos positivos.",
    "iqr_temp": "Rango intercuartílico Q3-Q1; variabilidad robusta sin depender tanto de valores extremos.",
    "env_contrast_temp": "Diferencia entre promedio del entorno y promedio del segmento; ayuda a confirmar si el lance destaca térmicamente.",
    "env_mean_temp": "Temperatura promedio antes/después del segmento, usando la ventana de entorno configurada.",
    "env_before_mean_temp": "Temperatura promedio antes del segmento ML.",
    "env_after_mean_temp": "Temperatura promedio después del segmento ML.",
    "env_n_points": "Número de lecturas usadas para calcular el entorno térmico.",
    "q1_temp": "Primer cuartil de temperatura dentro del segmento ML.",
    "q3_temp": "Tercer cuartil de temperatura dentro del segmento ML.",
    "mean_temp_smooth": "Promedio de la temperatura suavizada usada por el modelo; útil para auditar la detección.",
    "false_lance_risk": "Nivel de alerta estadística para posible falso lance: sin_alertas, bajo, medio o alto. Es una sugerencia, no una decisión automática.",
    "false_lance_flags": "Razones que dispararon la alerta: duración corta, poco contraste, poca variabilidad, pocas lecturas, etc.",
    "validation_hint": "Sugerencia práctica para que el analista revise el segmento en la gráfica y contra el observador.",
    "reading_ts": "Fecha y hora exacta de la lectura del sensor.",
    "temp_c": "Temperatura original registrada por el sensor en grados Celsius.",
    "temp_smooth": "Temperatura suavizada usada para reducir ruido antes de clasificar puntos.",
    "ml_cluster": "Cluster asignado por el modelo a esa lectura; el cluster frío se interpreta como posible lance.",
    "is_lance_ml": "Indica si esta lectura pertenece a un segmento detectado como lance por ML.",
    "clave_viaje": "Identificador original del viaje en el archivo de lances.",
    "clave_lance": "Identificador original del lance en el archivo de lances.",
    "lance_inicio_ts": "Fecha y hora de inicio del lance observado, calculada desde el archivo original.",
    "lance_fin_ts": "Fecha y hora de fin del lance observado, calculada desde el archivo original.",
    "tfm_promedio": "Temperatura promedio del sensor dentro del lance observado.",
    "tfm_mediana": "Mediana de temperatura dentro del lance observado; útil cuando hay valores extremos.",
    "tfm_min": "Temperatura mínima dentro del lance observado.",
    "tfm_max": "Temperatura máxima dentro del lance observado.",
    "tfm_delta": "Rango térmico del lance observado: temperatura máxima menos mínima.",
    "tfm_std": "Desviación estándar del lance observado; mide estabilidad térmica durante el lance.",
    "tfm_q1": "Primer cuartil de temperatura del lance observado.",
    "tfm_q3": "Tercer cuartil de temperatura del lance observado.",
    "tfm_iqr": "Rango intercuartílico del lance observado; variabilidad robusta.",
    "tfm_n_lecturas": "Número de lecturas del sensor encontradas dentro del lance observado.",
    "tfm_match_status": "Estado del cruce lance-sensor: ok, sin lecturas u hora inválida.",
    "ml_segment_id": "Segmento ML con mayor solapamiento temporal con el lance observado.",
    "ml_segment_label": "Etiqueta del segmento ML asociado al lance observado.",
    "ml_overlap_min": "Minutos de traslape entre el lance observado y el segmento ML asociado.",
    "ml_overlap_ratio_observed": "Proporción del lance observado cubierta por el segmento ML; 1.0 significa cobertura completa.",
    "ml_start_ts": "Inicio del segmento ML asociado.",
    "ml_end_ts": "Fin del segmento ML asociado.",
    "ml_duration_min": "Duración en minutos del segmento ML asociado.",
    "ml_n_points": "Número de lecturas dentro del segmento ML asociado.",
    "ml_mean_temp": "Temperatura promedio del segmento ML asociado.",
    "ml_median_temp": "Mediana de temperatura del segmento ML asociado.",
    "ml_min_temp": "Temperatura mínima del segmento ML asociado.",
    "ml_max_temp": "Temperatura máxima del segmento ML asociado.",
    "ml_delta_temp": "Rango térmico del segmento ML asociado.",
    "ml_std_temp": "Desviación estándar del segmento ML asociado.",
    "ml_iqr_temp": "Rango intercuartílico del segmento ML asociado.",
    "ml_env_contrast_temp": "Contraste térmico del segmento ML contra su entorno.",
    "ml_false_lance_risk": "Nivel de alerta del segmento ML asociado al lance observado.",
    "ml_false_lance_flags": "Razones estadísticas por las que el segmento ML asociado podría ser falso lance o mala delimitación.",
    "ml_validation_hint": "Sugerencia de validación para el segmento ML asociado.",
    "tfm_vs_ml_mean_delta": "Diferencia entre TFM observada y promedio ML; ayuda a revisar discrepancias.",
    "manual_validation": "Validación humana del segmento ML: sin revisar, sí es lance, no es lance o dudoso.",
    "include_in_report": "Indica si el segmento ML se usará en cruces, métricas y descargas filtradas.",
}


def _column_config_for(columns) -> dict:
    """Build Streamlit column help/tooltips for known report columns."""
    config = {}
    for column in columns:
        help_text = COLUMN_HELP.get(column)
        if help_text:
            config[column] = st.column_config.Column(str(column), help=help_text)
    return config


def _build_lance_report(lances_ts: pd.DataFrame, result: pd.DataFrame) -> pd.DataFrame:
    """Combine original lance rows with observed TFM and ML validation metrics."""
    original = lances_ts.reset_index(drop=True).copy()
    computed = result.reset_index(drop=True).copy()
    computed = computed[[c for c in computed.columns if c not in original.columns]]
    return pd.concat([original, computed], axis=1)


def _clean_csv_filename(value: str | None, default: str) -> str:
    """Return a safe CSV filename from a user-provided label."""
    raw = str(value or "").strip() or default
    if raw.lower().endswith(".csv"):
        raw = raw[:-4]
    cleaned = "".join(char if char.isalnum() or char in "-_ ." else "_" for char in raw).strip(" ._")
    if not cleaned:
        cleaned = default[:-4] if default.lower().endswith(".csv") else default
    return f"{cleaned}.csv"


VALIDATION_OPTIONS = ["sin revisar", "sí es lance", "no es lance", "dudoso"]


def _segment_validation_key(segment_id) -> str:
    return str(segment_id)


def _get_segment_validation(segment_id) -> str:
    value = st.session_state.ml_segment_validation.get(_segment_validation_key(segment_id), "sin revisar")
    return value if value in VALIDATION_OPTIONS else "sin revisar"


def _set_segment_validation(segment_id, value: str) -> None:
    if value not in VALIDATION_OPTIONS:
        value = "sin revisar"
    st.session_state.ml_segment_validation[_segment_validation_key(segment_id)] = value


def _apply_manual_segment_validation(segments: pd.DataFrame) -> pd.DataFrame:
    """Attach human validation and inclusion flags to ML segments."""
    if segments is None or segments.empty:
        return segments
    out = segments.copy()
    out["manual_validation"] = out["segment_id"].apply(_get_segment_validation)
    out["include_in_report"] = out["manual_validation"] != "no es lance"
    return out


def _filter_ml_segments_for_report(segments: pd.DataFrame | None) -> pd.DataFrame | None:
    """Optionally exclude manually rejected ML segments from comparisons/downloads."""
    if segments is None or segments.empty:
        return segments
    annotated = _apply_manual_segment_validation(segments)
    if st.session_state.exclude_rejected_ml_segments and "include_in_report" in annotated.columns:
        return annotated[annotated["include_in_report"]].copy()
    return annotated


def _show_methodology_note() -> None:
    st.info(
        "Nota metodológica: la detección ML es una herramienta de apoyo para auditoría, no una clasificación definitiva. "
        "El modelo agrupa patrones térmicos con K-Means y después resume cada segmento con estadística descriptiva "
        "(promedio, mediana, rango, desviación estándar, cuartiles/IQR y contraste contra el entorno). "
        "Las alertas de posible falso lance son sugerencias para priorizar revisión visual y comparación con el observador; "
        "no reemplazan el criterio del analista."
    )
    with st.expander("Fundamento metodológico y referencias"):
        st.markdown(
            """
            - **Agrupamiento no supervisado:** K-Means separa observaciones en grupos minimizando la variación interna. Aquí se usa para separar estados térmicos del sensor sin imponer umbrales fijos de temperatura. Referencias: MacQueen (1967), *Some Methods for Classification and Analysis of Multivariate Observations*; Lloyd (1982), *Least Squares Quantization in PCM*.
            - **Suavizado de serie temporal:** la media móvil reduce ruido puntual antes de agrupar, útil cuando la señal del sensor tiene oscilaciones pequeñas.
            - **Estadística descriptiva robusta:** mediana, cuartiles e IQR ayudan a evaluar dispersión sin depender tanto de valores extremos. Referencia: Tukey (1977), *Exploratory Data Analysis*.
            - **Contraste contra entorno:** comparar el segmento con lecturas antes/después ayuda a validar si el lance destaca térmicamente frente al contexto inmediato.

            Interpretación práctica: un segmento corto, con pocas lecturas, bajo contraste térmico, delta pequeño o señales estadísticas contradictorias debe revisarse como posible falso positivo o mala delimitación, no eliminarse automáticamente.
            """
        )


def _safe_preset_slug(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    slug = "_".join(part for part in slug.split("_") if part)
    return slug or "preset"


def _list_presets() -> list[Path]:
    if not PRESETS_DIR.exists():
        return []
    return sorted(PRESETS_DIR.glob("*.json"))


def _load_preset(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _current_ml_params() -> dict[str, int]:
    return {param_name: int(st.session_state[f"ml_{param_name}"]) for param_name in ML_DEFAULTS}


def _apply_preset_to_session(preset: dict) -> None:
    for param_name, value in preset.get("ml_params", {}).items():
        if param_name in ML_DEFAULTS and value is not None:
            st.session_state[f"ml_{param_name}"] = int(value)
    st.session_state.loaded_preset_name = preset.get("preset_name", "")


def _save_preset(
    *,
    name: str,
    description: str,
    sensor_file_name: str | None,
    lances_file_name: str | None,
    time_col: str | None,
    temp_col: str | None,
) -> Path:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    preset = {
        "preset_name": name.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description.strip(),
        "context": {
            "sensor_file": sensor_file_name,
            "lances_file": lances_file_name,
            "time_col": time_col,
            "temp_col": temp_col,
        },
        "ml_params": _current_ml_params(),
    }
    path = PRESETS_DIR / f"{_safe_preset_slug(name)}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(preset, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def _save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".tmp"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return Path(tmp.name)


def _excel_sheet_names(path: Path) -> list[str]:
    """Return sheet names for an Excel file."""
    return list(pd.ExcelFile(path).sheet_names)


def _select_excel_sheet(path: Path, label: str, key: str) -> str | int:
    """Show a sheet selector for Excel files and return the selected sheet."""
    names = _excel_sheet_names(path)
    if not names:
        return 0
    if len(names) == 1:
        st.caption(f"Hoja de {label}: `{names[0]}`")
        return names[0]
    return st.selectbox(
        f"Hoja de Excel para {label}",
        names,
        index=0,
        key=key,
        help="Si el archivo tiene varias pestañas, selecciona cuál usar para este análisis.",
    )


def _load_sensor_file(path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        delimiter = detect_csv_delimiter(path)
        header_row = detect_csv_header_row(path, delimiter=delimiter)
        delimiter_label = {",": "coma (,)", ";": "punto y coma (;)", "\t": "tabulador", "|": "barra vertical (|)"}.get(delimiter, delimiter)
        st.info(f"Header detectado en fila {header_row + 1} para el archivo de sensores CSV. Separador detectado: {delimiter_label}.")
        return pd.read_csv(path, header=header_row, delimiter=delimiter)
    return pd.read_excel(path, sheet_name=sheet_name)


def _detect_excel_header_row(path: Path, expected_columns: list[str] | tuple[str, ...] | None = None, max_rows: int = 20, sheet_name: str | int = 0) -> int:
    """Return the zero-based row index of the Excel header.

    This mirrors the CSV header detection used for field files that include a
    title/legend row before the real table header.
    """
    preview = pd.read_excel(path, header=None, nrows=max_rows, sheet_name=sheet_name)
    expected = {_normalize_column_name(col).replace(" ", "") for col in (expected_columns or []) if str(col).strip()}

    for row_idx, row in preview.iterrows():
        values = [str(cell).strip() for cell in row.tolist() if pd.notna(cell) and str(cell).strip()]
        if not values:
            continue

        normalized = {_normalize_column_name(cell).replace(" ", "") for cell in values}
        if expected:
            overlap = len(normalized & expected)
            if overlap >= max(1, min(2, len(expected) // 4)):
                return int(row_idx)
        elif len(values) >= 3 and any(any(ch.isalpha() for ch in cell) for cell in values):
            return int(row_idx)

    return 0


def _load_lances_file(path: Path, sheet_name: str | int = 0) -> tuple[pd.DataFrame, int, str]:
    """Load lances from CSV or Excel and return df, header row, and format note."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        delimiter = detect_csv_delimiter(path)
        header_row = detect_csv_header_row(path, expected_columns=LANCE_EXPECTED_COLS, delimiter=delimiter)
        delimiter_label = {",": "coma (,)", ";": "punto y coma (;)", "\t": "tabulador", "|": "barra vertical (|)"}.get(delimiter, delimiter)
        lances = pd.read_csv(path, header=header_row, delimiter=delimiter)
        return lances, header_row, f"CSV; separador detectado: {delimiter_label}"

    if suffix in {".xlsx", ".xls"}:
        header_row = _detect_excel_header_row(path, expected_columns=LANCE_EXPECTED_COLS, sheet_name=sheet_name)
        lances = pd.read_excel(path, header=header_row, sheet_name=sheet_name)
        return lances, header_row, f"Excel; hoja: {sheet_name}"

    raise ValueError(f"Formato de lances no soportado: {suffix or 'sin extensión'}")


def _normalize_for_select(values):
    return [str(v) for v in values if str(v).strip()]


def _find_column(columns, candidates: list[str], fallback_index: int = 0) -> str | None:
    if not columns:
        return None
    normalized_map = {_normalize_column_name(column): column for column in columns}
    for candidate in candidates:
        normalized = _normalize_column_name(candidate)
        if normalized in normalized_map:
            return normalized_map[normalized]
    for candidate in candidates:
        normalized = _normalize_column_name(candidate)
        for column in columns:
            if normalized and normalized in _normalize_column_name(column):
                return column
    return columns[min(fallback_index, len(columns) - 1)]


def _normalize_column_name(value) -> str:
    text = str(value).strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "°": "",
        ".": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split())


def _column_match_key(value) -> str:
    """Normalize a column name for tolerant matching.

    Examples that should match the same concept: `clave_lance`, `clave lance`,
    `Clave Lance`, `clave-lance`.
    """
    return "".join(ch for ch in _normalize_column_name(value) if ch.isalnum())


def _canonicalize_lance_columns(lances: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Rename common lances columns to the canonical names used internally."""
    out = lances.copy()
    rename_map: dict[str, str] = {}
    existing_keys = {_column_match_key(column): column for column in out.columns}

    for canonical in LANCE_EXPECTED_COLS:
        canonical_key = _column_match_key(canonical)
        source = existing_keys.get(canonical_key)
        if source is not None and source != canonical and canonical not in out.columns:
            rename_map[source] = canonical

    if rename_map:
        out = out.rename(columns=rename_map)
    return out, {str(old): str(new) for old, new in rename_map.items()}


def _looks_like_decimal_hour_column(series: pd.Series) -> bool:
    """Detect columns that likely store hours as decimals, not HH.MM text.

    Example: `10.9833` means 10 + 0.9833 hours ≈ 10:59. If interpreted as
    HH.MM it would become impossible minutes (`10:98`). This function only
    proposes a default; the user controls the normalization in the UI.
    """
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return False
    numeric = numeric[(numeric >= 0) & (numeric < 24)]
    if numeric.empty:
        return False

    fractions = (numeric - numeric.astype(int)).abs()
    impossible_hhmm_minutes = (fractions * 100).round(4) >= 60
    many_decimal_places = series.astype("string").str.extract(r"\.(\d+)", expand=False).str.len().fillna(0).astype(int) > 2
    return bool(impossible_hhmm_minutes.any() or many_decimal_places.any())


def _decimal_hour_to_hhmm(value):
    """Convert a decimal-hour value to HH:MM; leave blanks/invalid values empty."""
    if pd.isna(value):
        return pd.NA
    try:
        num = float(str(value).strip())
    except Exception:
        return value
    if not (0 <= num < 24):
        return value
    hh = int(num)
    total_seconds = round((num - hh) * 60 * 60)
    mm = total_seconds // 60
    if mm == 60:
        hh += 1
        mm = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return value
    return f"{hh:02d}:{mm:02d}"


def _normalize_date_column_for_processing(series: pd.Series) -> pd.Series:
    """Normalize a date column to ISO date strings for downstream processing."""
    normalized = normalize_date_series(series, dayfirst=True)
    return normalized.dt.strftime("%Y-%m-%d").where(normalized.notna(), pd.NA)


def _show_lance_normalization_controls(lances: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """UI-controlled preprocessing for lances before the existing analysis flow."""
    out = lances.copy()
    messages: list[str] = []
    columns = _normalize_for_select(out.columns.tolist())
    if not columns:
        return out, messages

    st.subheader("Normalización de fechas y horas")
    st.caption("Este paso prepara el archivo antes del cálculo. Después, el resto de la app trabaja con estas columnas normalizadas.")

    date_default = _find_column(columns, ["fecha", "date"], fallback_index=0)
    hour_candidates = [column for column in columns if _column_match_key(column).startswith("hora") or str(column).lower().startswith("hr")]
    suggested_decimal_hours = [column for column in hour_candidates if _looks_like_decimal_hour_column(out[column])]

    with st.expander("Configurar normalización", expanded=bool(suggested_decimal_hours)):
        has_probable_date_column = date_default is not None and any(token in _column_match_key(date_default) for token in ["fecha", "date"])
        normalize_date = st.checkbox(
            "Normalizar columna de fecha a formato YYYY-MM-DD",
            value=has_probable_date_column,
            help="Útil cuando la fecha viene como texto, Excel o con hora incluida.",
        )
        date_col_for_normalization = st.selectbox(
            "Columna de fecha a normalizar",
            columns,
            index=columns.index(date_default) if date_default in columns else 0,
            disabled=not normalize_date,
        )

        decimal_hour_cols = st.multiselect(
            "Columnas de hora en formato decimal a convertir a HH:MM",
            hour_candidates,
            default=suggested_decimal_hours,
            help="Usar para valores como 7.5 = 07:30 o 10.9833 ≈ 10:59. No activar en columnas que ya estén en HH.MM manual.",
        )

        if normalize_date and date_col_for_normalization:
            before = out[date_col_for_normalization].copy()
            out[date_col_for_normalization] = _normalize_date_column_for_processing(out[date_col_for_normalization])
            changed = int((before.astype("string") != out[date_col_for_normalization].astype("string")).fillna(False).sum())
            messages.append(f"Fecha normalizada en `{date_col_for_normalization}` ({changed} valores transformados).")

        for column in decimal_hour_cols:
            before = out[column].copy()
            out[column] = out[column].apply(_decimal_hour_to_hhmm)
            changed = int((before.astype("string") != out[column].astype("string")).fillna(False).sum())
            messages.append(f"Hora decimal normalizada en `{column}` ({changed} valores transformados).")

        if messages:
            preview_cols = [c for c in [date_col_for_normalization, *decimal_hour_cols] if c in out.columns]
            st.dataframe(out[preview_cols].head(10), use_container_width=True, hide_index=True)
        else:
            st.caption("No se aplicaron transformaciones de normalización.")

    return out, messages


def _is_probable_time_or_temp_column(column) -> bool:
    normalized = _normalize_column_name(column)
    useful_tokens = ["fecha", "tiempo", "time", "date", "temp", "temper", "tfm", "celsius"]
    return any(token in normalized for token in useful_tokens)


def _is_mostly_empty_or_none(series: pd.Series, min_ratio: float = 0.95) -> bool:
    if len(series) == 0:
        return True
    normalized = series.astype("string").str.strip().str.lower()
    empty_like = normalized.isna() | normalized.isin({"", "none", "nan", "na", "n/a", "null", "<na>"})
    return float(empty_like.mean()) >= min_ratio


def _is_sequential_counter(series: pd.Series, min_ratio: float = 0.90) -> bool:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 5:
        return False
    diffs = values.diff().dropna()
    if diffs.empty:
        return False
    return float((diffs == 1).mean()) >= min_ratio


def _drop_sensor_noise_columns(sensor: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Remove logger/index columns that do not help the temperature analysis.

    The cleanup is mostly content-based so it also works when logger files use
    different column names: keep likely time/temperature columns, remove blank
    columns, mostly-empty event/status columns, and sequential counters.
    """
    drop_names = []
    noise_exact = {"n", "no", "nº", "n°", "numero"}
    noise_contains = ["host conectado", "parado", "final de archivo"]

    for column in sensor.columns:
        normalized = _normalize_column_name(column)
        if _is_probable_time_or_temp_column(column):
            continue

        is_unnamed = normalized.startswith("unnamed") or normalized == ""
        is_named_counter = normalized in noise_exact
        is_event_flag_name = any(token in normalized for token in noise_contains)
        is_empty_status = _is_mostly_empty_or_none(sensor[column])
        is_counter_values = _is_sequential_counter(sensor[column])

        if is_unnamed or is_named_counter or is_event_flag_name or is_empty_status or is_counter_values:
            drop_names.append(column)

    if not drop_names:
        return sensor.copy(), []
    return sensor.drop(columns=drop_names).copy(), [str(c) for c in drop_names]


def _add_ml_overlap_to_observed_result(result: pd.DataFrame, ml_segments: pd.DataFrame | None) -> pd.DataFrame:
    """Add nearest/overlapping ML segment columns to observer-based TFM results."""
    out = result.copy()
    if ml_segments is None or ml_segments.empty or out.empty:
        return out

    match_rows = []
    for _, obs in out.iterrows():
        obs_start = obs.get("lance_inicio_ts")
        obs_end = obs.get("lance_fin_ts")
        best = {
            "ml_segment_id": pd.NA,
            "ml_segment_label": pd.NA,
            "ml_manual_validation": pd.NA,
            "ml_include_in_report": pd.NA,
            "ml_overlap_min": pd.NA,
            "ml_overlap_ratio_observed": pd.NA,
            "ml_start_ts": pd.NA,
            "ml_end_ts": pd.NA,
            "ml_duration_min": pd.NA,
            "ml_n_points": pd.NA,
            "ml_mean_temp": pd.NA,
            "ml_median_temp": pd.NA,
            "ml_min_temp": pd.NA,
            "ml_max_temp": pd.NA,
            "ml_delta_temp": pd.NA,
            "ml_std_temp": pd.NA,
            "ml_iqr_temp": pd.NA,
            "ml_env_contrast_temp": pd.NA,
            "ml_false_lance_risk": pd.NA,
            "ml_false_lance_flags": pd.NA,
            "ml_validation_hint": pd.NA,
            "tfm_vs_ml_mean_delta": pd.NA,
        }

        if pd.isna(obs_start) or pd.isna(obs_end):
            match_rows.append(best)
            continue
        if obs_end < obs_start:
            obs_end = obs_end + pd.Timedelta(days=1)

        obs_duration_min = max((obs_end - obs_start).total_seconds() / 60.0, 0)
        best_overlap_min = 0.0
        best_seg = None

        for _, seg in ml_segments.iterrows():
            seg_start = seg.get("start_ts")
            seg_end = seg.get("end_ts")
            if pd.isna(seg_start) or pd.isna(seg_end):
                continue
            overlap_start = max(obs_start, seg_start)
            overlap_end = min(obs_end, seg_end)
            overlap_min = max((overlap_end - overlap_start).total_seconds() / 60.0, 0)
            if overlap_min > best_overlap_min:
                best_overlap_min = overlap_min
                best_seg = seg

        if best_seg is not None:
            best["ml_segment_id"] = best_seg.get("segment_id")
            best["ml_segment_label"] = best_seg.get("segment_label")
            best["ml_manual_validation"] = best_seg.get("manual_validation", "sin revisar")
            best["ml_include_in_report"] = best_seg.get("include_in_report", True)
            best["ml_overlap_min"] = best_overlap_min
            best["ml_overlap_ratio_observed"] = best_overlap_min / obs_duration_min if obs_duration_min else pd.NA
            best["ml_start_ts"] = best_seg.get("start_ts")
            best["ml_end_ts"] = best_seg.get("end_ts")
            best["ml_duration_min"] = best_seg.get("duration_min")
            best["ml_n_points"] = best_seg.get("n_points")
            best["ml_mean_temp"] = best_seg.get("mean_temp")
            best["ml_median_temp"] = best_seg.get("median_temp")
            best["ml_min_temp"] = best_seg.get("min_temp")
            best["ml_max_temp"] = best_seg.get("max_temp")
            best["ml_delta_temp"] = best_seg.get("delta_temp")
            best["ml_std_temp"] = best_seg.get("std_temp")
            best["ml_iqr_temp"] = best_seg.get("iqr_temp")
            best["ml_env_contrast_temp"] = best_seg.get("env_contrast_temp")
            best["ml_false_lance_risk"] = best_seg.get("false_lance_risk")
            best["ml_false_lance_flags"] = best_seg.get("false_lance_flags")
            best["ml_validation_hint"] = best_seg.get("validation_hint")
            if pd.notna(obs.get("tfm_promedio")) and pd.notna(best_seg.get("mean_temp")):
                best["tfm_vs_ml_mean_delta"] = float(obs.get("tfm_promedio") - best_seg.get("mean_temp"))

        match_rows.append(best)

    return pd.concat([out.reset_index(drop=True), pd.DataFrame(match_rows)], axis=1)


col_left, col_right = st.columns(2)

with col_left:
    lances_file = st.file_uploader("Archivo de lances (CSV/XLSX)", type=["csv", "xlsx", "xls"])
with col_right:
    sensor_file = st.file_uploader("Archivo de sensores (CSV/XLSX)", type=["csv", "xlsx", "xls"])

if lances_file:
    lances_path = _save_upload(lances_file)
    lances_sheet_name = 0
    if lances_path.suffix.lower() in {".xlsx", ".xls"}:
        lances_sheet_name = _select_excel_sheet(lances_path, "lances", f"lances_sheet_{lances_file.name}")
    lances, header_row, lances_format_note = _load_lances_file(lances_path, sheet_name=lances_sheet_name)
    st.success(f"Encabezado de lances detectado en fila {header_row + 1}. Formato: {lances_format_note}.")
    lances, renamed_lance_columns = _canonicalize_lance_columns(lances)
    lances, removed_blank_lance_rows = drop_rows_missing_column(lances, "clave_lance")
    lances, removed_empty_columns = drop_empty_columns(lances, preserve_columns=LANCE_EXPECTED_COLS)

    missing = [c for c in LANCE_REQUIRED_ID_COLS if c not in lances.columns]
    if missing:
        st.error(f"Faltan columnas mínimas en lances: {', '.join(missing)}")
        st.stop()
    lances, normalization_messages = _show_lance_normalization_controls(lances)

    st.subheader("Lances normalizados")
    st.dataframe(lances.head(20), use_container_width=True)
    if renamed_lance_columns:
        st.info(
            "Se normalizaron nombres de columnas de lances: "
            + ", ".join(f"`{old}` → `{new}`" for old, new in renamed_lance_columns.items())
        )
    for message in normalization_messages:
        st.info(message)
    if removed_blank_lance_rows:
        st.warning(f"Se eliminaron {removed_blank_lance_rows} filas sin `clave_lance`.")
    if removed_empty_columns:
        st.info(f"Se ocultaron columnas vacías: {', '.join(removed_empty_columns)}")

    lance_cols = _normalize_for_select(lances.columns.tolist())
    date_default = _find_column(lance_cols, ["fecha", "date"], fallback_index=0)
    start_default = _find_column(lance_cols, ["hr_fincal", "Hora_2"], fallback_index=0)
    end_default = _find_column(lance_cols, ["hr_inicob", "Hora_3"], fallback_index=min(1, len(lance_cols) - 1))

    st.subheader("Intervalo de evaluación TFM")
    st.caption("Por metodología SIRBAA, el intervalo recomendado es final del calado → inicio del cobrado: `hr_fincal` → `hr_inicob` (o `Hora_2` → `Hora_3`).")
    i1, i2, i3 = st.columns(3)
    with i1:
        lance_date_col = st.selectbox(
            "Columna de fecha",
            lance_cols,
            index=lance_cols.index(date_default) if date_default in lance_cols else 0,
        )
    with i2:
        lance_start_col = st.selectbox(
            "Inicio del intervalo a evaluar",
            lance_cols,
            index=lance_cols.index(start_default) if start_default in lance_cols else 0,
            help="Recomendado: `hr_fincal` o `Hora_2` = final del calado, cuando la red llega al fondo.",
        )
    with i3:
        lance_end_col = st.selectbox(
            "Fin del intervalo a evaluar",
            lance_cols,
            index=lance_cols.index(end_default) if end_default in lance_cols else min(1, len(lance_cols) - 1),
            help="Recomendado: `hr_inicob` o `Hora_3` = inicio del cobrado, cuando la red empieza a levantarse del fondo.",
        )

if sensor_file:
    sensor_path = _save_upload(sensor_file)
    sensor_sheet_name = 0
    if sensor_path.suffix.lower() in {".xlsx", ".xls"}:
        sensor_sheet_name = _select_excel_sheet(sensor_path, "sensores", f"sensor_sheet_{sensor_file.name}")
    sensor = _load_sensor_file(sensor_path, sheet_name=sensor_sheet_name)
    sensor, removed_noise_sensor_columns = _drop_sensor_noise_columns(sensor)
    sensor, removed_empty_sensor_columns = drop_empty_columns(sensor)

    st.subheader("Sensores")
    st.caption(f"Vista previa: primeras 20 filas de {len(sensor)} filas cargadas. El análisis usa el archivo completo.")
    st.dataframe(sensor.head(20), use_container_width=True, hide_index=True)

    if removed_noise_sensor_columns:
        st.info(f"Se ocultaron columnas técnicas del sensor: {', '.join(removed_noise_sensor_columns)}")

    if removed_empty_sensor_columns:
        st.info(f"Se ocultaron columnas vacías del sensor: {', '.join(removed_empty_sensor_columns)}")

    sensor_cols = _normalize_for_select(sensor.columns.tolist())
    if not sensor_cols:
        st.error("El archivo de sensores no trae columnas válidas.")
        st.stop()

    left, right = st.columns(2)
    with left:
        time_col = st.selectbox("Columna de tiempo", sensor_cols, index=0 if sensor_cols else None)
    with right:
        temp_candidates = [c for c in sensor_cols if any(k in c.lower() for k in ["temp", "temper", "tfm"])]
        temp_default = temp_candidates[0] if temp_candidates else (sensor_cols[1] if len(sensor_cols) > 1 else (sensor_cols[0] if sensor_cols else None))
        temp_index = sensor_cols.index(temp_default) if temp_default in sensor_cols else 0
        temp_col = st.selectbox("Columna de temperatura", sensor_cols, index=temp_index)

    with st.expander("Ajustes ML de detección"):
        presets = _list_presets()
        if presets:
            preset_options = {path.stem: path for path in presets}
            p1, p2 = st.columns([3, 1])
            with p1:
                selected_preset_key = st.selectbox(
                    "Preset guardado",
                    list(preset_options.keys()),
                    help="Carga parámetros ML previamente guardados para repetir un análisis.",
                )
            with p2:
                if st.button("Aplicar preset", use_container_width=True):
                    preset = _load_preset(preset_options[selected_preset_key])
                    _apply_preset_to_session(preset)
                    st.success(f"Preset aplicado: {preset.get('preset_name', selected_preset_key)}")
                    st.rerun()
        else:
            st.caption("Aún no hay presets guardados. Ajusta parámetros y guarda uno abajo.")

        if st.session_state.loaded_preset_name:
            st.caption(f"Preset activo: {st.session_state.loaded_preset_name}")

        ml_n_clusters = st.slider(
            "Número de clusters",
            2,
            5,
            key="ml_n_clusters",
            help="Cuántos grupos intenta separar el modelo. 3 suele funcionar mejor: fondo, transición y superficie.",
        )
        ml_rolling_window = st.slider(
            "Ventana de suavizado",
            3,
            21,
            step=2,
            key="ml_rolling_window",
            help="Suaviza la temperatura antes de agruparla. Más alto = menos ruido, pero también menos detalle.",
        )
        ml_smoothing_window = st.slider(
            "Suavizado de etiquetas",
            1,
            9,
            step=2,
            key="ml_smoothing_window",
            help="Suaviza la clasificación punto a punto para evitar saltos cortos dentro del mismo lance.",
        )
        ml_merge_gap = st.slider(
            "Unir tramos cercanos (min)",
            0,
            60,
            key="ml_merge_gap_minutes",
            help="Si dos tramos bajos están separados por menos de este tiempo, se unen como un solo lance.",
        )
        ml_context_window = st.slider(
            "Ventana de entorno para contraste (min)",
            15,
            180,
            step=15,
            key="ml_context_window_minutes",
            help="Minutos antes y después de cada segmento usados para comparar el lance contra su entorno térmico.",
        )
        ml_min_points = st.slider(
            "Mínimo de puntos por lance",
            3,
            60,
            key="ml_min_segment_points",
            help="Descarta candidatos demasiado cortos para evitar falsos lances.",
        )

        st.divider()
        st.caption("Guardar configuración actual como preset reproducible")
        preset_name = st.text_input("Nombre del preset", placeholder="ej. merluza_sensor_edf_v1")
        preset_description = st.text_area("Notas del preset", placeholder="Qué archivo/contexto calibró este preset y por qué funcionó.")
        if st.button("Guardar preset actual"):
            if not preset_name.strip():
                st.warning("Escribe un nombre para guardar el preset.")
            else:
                saved_path = _save_preset(
                    name=preset_name,
                    description=preset_description,
                    sensor_file_name=sensor_file.name if sensor_file else None,
                    lances_file_name=lances_file.name if lances_file else None,
                    time_col=time_col,
                    temp_col=temp_col,
                )
                st.session_state.loaded_preset_name = preset_name.strip()
                st.success(f"Preset guardado: {saved_path.name}")

    ml_signature = (
        sensor_file.name,
        tuple(sensor.columns.tolist()),
        len(sensor),
        time_col,
        temp_col,
        ml_n_clusters,
        ml_rolling_window,
        ml_smoothing_window,
        ml_merge_gap,
        ml_context_window,
        ml_min_points,
    )

    if st.session_state.ml_signature != ml_signature:
        sensor_prepared = prepare_sensor_readings(sensor, time_col, temp_col)
        st.session_state.ml_analysis = detect_lance_segments_ml(
            sensor_prepared,
            time_col="reading_ts",
            temp_col="temp_c",
            n_clusters=ml_n_clusters,
            rolling_window=ml_rolling_window,
            smoothing_window=ml_smoothing_window,
            merge_gap_minutes=ml_merge_gap,
            context_window_minutes=ml_context_window,
            min_segment_points=ml_min_points,
        )
        st.session_state.ml_signature = ml_signature
        st.session_state.ml_result_version += 1
        if not st.session_state.ml_analysis.segments.empty:
            st.session_state.ml_selected_segment_id = st.session_state.ml_analysis.segments.iloc[0]["segment_id"]
        else:
            st.session_state.ml_selected_segment_id = None
        st.caption("Detección ML actualizada automáticamente con los parámetros actuales.")

if st.session_state.ml_analysis:
    ml_result = st.session_state.ml_analysis
    ml_points = ml_result.points
    ml_segments_raw = ml_result.segments
    ml_segments = _apply_manual_segment_validation(ml_segments_raw)

    st.subheader("Lances detectados desde termómetro")
    if ml_segments.empty:
        st.warning("No se detectaron segmentos con suficiente señal.")
    else:
        if st.session_state.ml_selected_segment_id not in set(ml_segments["segment_id"].tolist()):
            st.session_state.ml_selected_segment_id = ml_segments.iloc[0]["segment_id"]

        detected_for_chart = ml_segments.copy()
        detected_for_chart["selected"] = detected_for_chart["segment_id"] == st.session_state.ml_selected_segment_id
        selected_row_idx = int(detected_for_chart.index[detected_for_chart["selected"]][0])

        show_observer = st.checkbox(
            "Superponer lances del observador",
            value=bool(lances_file),
            disabled=not bool(lances_file),
        )
        st.session_state.exclude_rejected_ml_segments = st.checkbox(
            "Excluir segmentos marcados como `no es lance` del cruce y descargas filtradas",
            value=st.session_state.exclude_rejected_ml_segments,
            help="No borra segmentos; solo evita que los falsos lances afecten el reporte comparativo y la descarga filtrada.",
        )

        base_line = (
            alt.Chart(ml_points)
            .mark_line(color="#666", size=1.5)
            .encode(
                x=alt.X("reading_ts:T", axis=TIME_AXIS),
                y=alt.Y("temp_c:Q", title="Temperatura"),
                tooltip=["reading_ts:T", "temp_c:Q"],
            )
        )

        segment_selector = alt.selection_point(
            name="segment_selector",
            fields=["segment_id"],
            on="click",
            clear="dblclick",
        )

        detected_rects = (
            alt.Chart(detected_for_chart)
            .mark_rect()
            .encode(
                x=alt.X("start_ts:T", axis=TIME_AXIS),
                x2="end_ts:T",
                y="min_temp:Q",
                y2="max_temp:Q",
                color=alt.condition("datum.selected", alt.value("#ff4b2f"), alt.value("#d62728")),
                opacity=alt.condition("datum.selected", alt.value(0.48), alt.value(0.14)),
                tooltip=[
                    "segment_label:N",
                    "start_ts:T",
                    "end_ts:T",
                    "n_points:Q",
                    "mean_temp:Q",
                    "delta_temp:Q",
                    "std_temp:Q",
                    "env_contrast_temp:Q",
                    "env_mean_temp:Q",
                    "duration_hhmm:N",
                ],
            )
            .add_params(segment_selector)
        )

        chart_layers = [base_line, detected_rects]

        if show_observer and "lances" in locals():
            observer_ts = build_lance_timestamps(
                lances,
                date_col=lance_date_col,
                start_col=lance_start_col,
                end_col=lance_end_col,
            )
            chart_min_temp = float(ml_points["temp_c"].min()) if not ml_points.empty else 0.0
            chart_max_temp = float(ml_points["temp_c"].max()) if not ml_points.empty else 1.0
            observer_rows = []
            for _, obs in observer_ts.iterrows():
                start_ts = obs.get("lance_inicio_ts")
                end_ts = obs.get("lance_fin_ts")
                if pd.isna(start_ts) or pd.isna(end_ts):
                    continue
                if end_ts < start_ts:
                    end_ts = end_ts + pd.Timedelta(days=1)

                obs_window = sensor_readings_within_lance(obs, ml_points)
                has_sensor_points = not obs_window.empty
                observer_rows.append(
                    {
                        "clave_viaje": obs.get("clave_viaje"),
                        "clave_lance": obs.get("clave_lance"),
                        "start_ts": start_ts,
                        "end_ts": end_ts,
                        "min_temp": chart_min_temp,
                        "max_temp": chart_max_temp,
                        "n_sensor_points": int(len(obs_window)),
                    }
                )

            if observer_rows:
                observer_df = pd.DataFrame(observer_rows)
                st.caption(f"Lances observados dibujados: {len(observer_df)} de {len(observer_ts)} con fechas/horas válidas.")
                observer_rects = (
                    alt.Chart(observer_df)
                    .mark_rect(fill="#1f77b4", fillOpacity=0.08, stroke="#1f77b4", strokeWidth=1.5)
                    .encode(
                        x=alt.X("start_ts:T", axis=TIME_AXIS),
                        x2="end_ts:T",
                        y="min_temp:Q",
                        y2="max_temp:Q",
                        tooltip=["clave_viaje:N", "clave_lance:N", "start_ts:T", "end_ts:T", "n_sensor_points:Q"],
                    )
                )
                chart_layers.append(observer_rects)
            else:
                st.warning("No se pudieron dibujar lances observados: revisa fecha, hora inicial y hora final.")

        chart = alt.layer(*chart_layers).properties(height=300)
        chart_placeholder = st.empty()
        st.caption("Rojo = segmentos detectados por ML. Azul = lances del observador (si se activan). Puedes hacer zoom/pan en la gráfica con scroll/arrastre.")

        preferred_segment_cols = [
            "segment_label",
            "segment_id",
            "manual_validation",
            "include_in_report",
            "false_lance_risk",
            "false_lance_flags",
            "validation_hint",
            "start_ts",
            "end_ts",
            "duration_hhmm",
            "duration_min",
            "n_points",
            "mean_temp",
            "median_temp",
            "min_temp",
            "max_temp",
            "delta_temp",
            "std_temp",
            "iqr_temp",
            "env_contrast_temp",
            "env_mean_temp",
            "env_before_mean_temp",
            "env_after_mean_temp",
            "env_n_points",
            "q1_temp",
            "q3_temp",
            "mean_temp_smooth",
        ]
        segment_cols = [c for c in preferred_segment_cols if c in ml_segments.columns] + [
            c for c in ml_segments.columns if c not in preferred_segment_cols
        ]
        ml_segments_display = ml_segments[segment_cols]

        segments_view = st.dataframe(
            ml_segments_display,
            use_container_width=True,
            hide_index=True,
            column_config=_column_config_for(ml_segments_display.columns),
            key=f"ml_segments_table_{st.session_state.ml_result_version}",
            on_select="rerun",
            selection_mode="single-row",
            selection_default={"selection": {"rows": [selected_row_idx], "columns": [], "cells": []}},
        )
        if segments_view and segments_view.selection.rows:
            st.session_state.ml_selected_segment_id = ml_segments.iloc[segments_view.selection.rows[0]]["segment_id"]

        selected_segment_id = st.session_state.ml_selected_segment_id
        validation_current = _get_segment_validation(selected_segment_id)
        validation_choice = st.radio(
            "Validación manual del segmento ML seleccionado",
            VALIDATION_OPTIONS,
            index=VALIDATION_OPTIONS.index(validation_current),
            horizontal=True,
            help="Marca si el segmento detectado por ML corresponde a un lance real. Esta marca se usará para filtrar el cruce y servirá como base para entrenamiento posterior.",
            key=f"manual_validation_radio_{st.session_state.ml_result_version}_{selected_segment_id}",
        )
        if validation_choice != validation_current:
            _set_segment_validation(selected_segment_id, validation_choice)
            st.rerun()

        detected_for_chart = ml_segments.copy()
        detected_for_chart["selected"] = detected_for_chart["segment_id"] == st.session_state.ml_selected_segment_id
        detected_rects = (
            alt.Chart(detected_for_chart)
            .mark_rect()
            .encode(
                x=alt.X("start_ts:T", axis=TIME_AXIS),
                x2="end_ts:T",
                y="min_temp:Q",
                y2="max_temp:Q",
                color=alt.condition("datum.selected", alt.value("#ff4b2f"), alt.value("#d62728")),
                opacity=alt.condition("datum.selected", alt.value(0.48), alt.value(0.14)),
                tooltip=[
                    "segment_label:N",
                    "start_ts:T",
                    "end_ts:T",
                    "n_points:Q",
                    "mean_temp:Q",
                    "delta_temp:Q",
                    "std_temp:Q",
                    "env_contrast_temp:Q",
                    "env_mean_temp:Q",
                    "duration_hhmm:N",
                ],
            )
            .add_params(segment_selector)
        )
        chart = alt.layer(base_line, detected_rects, *chart_layers[2:]).properties(height=300).interactive(bind_y=False)
        chart_event = chart_placeholder.altair_chart(
            chart,
            use_container_width=True,
            key=f"ml_segments_chart_{st.session_state.ml_result_version}",
            on_select="rerun",
            selection_mode=["segment_selector"],
        )
        if chart_event and "segment_selector" in chart_event and chart_event.segment_selector.length > 0:
            st.session_state.ml_selected_segment_id = chart_event.segment_selector.items[0]["segment_id"]

        a1, a2 = st.columns(2)
        a1.metric("Segmentos detectados", len(ml_segments))
        a2.metric("Puntos usados", len(ml_points))

        selected_rows = ml_segments[ml_segments["segment_id"] == st.session_state.ml_selected_segment_id]
        seg_idx = int(selected_rows.index[0]) if not selected_rows.empty else 0
        segment_id = ml_segments.loc[seg_idx, "segment_id"]
        segment_points = ml_points[ml_points["segment_id"] == segment_id].copy()

        c1, c2, c3 = st.columns(3)
        c1.metric("Lecturas en el segmento", len(segment_points))
        c2.metric("Promedio temp", f"{segment_points['temp_c'].mean():.3f}")
        c3.metric("Rango temp", f"{segment_points['temp_c'].min():.3f} → {segment_points['temp_c'].max():.3f}")

        s1, s2, s3 = st.columns(3)
        s1.metric("Delta temp", f"{segment_points['temp_c'].max() - segment_points['temp_c'].min():.3f}")
        s2.metric("Desv. estándar", f"{segment_points['temp_c'].std(ddof=0):.3f}")
        s3.metric("Mediana temp", f"{segment_points['temp_c'].median():.3f}")

        selected_segment = ml_segments[ml_segments["segment_id"] == segment_id].iloc[0]
        e1, e2, e3 = st.columns(3)
        e1.metric("Contraste vs entorno", f"{selected_segment['env_contrast_temp']:.3f}" if pd.notna(selected_segment.get("env_contrast_temp")) else "—")
        e2.metric("Promedio entorno", f"{selected_segment['env_mean_temp']:.3f}" if pd.notna(selected_segment.get("env_mean_temp")) else "—")
        e3.metric("Lecturas entorno", int(selected_segment.get("env_n_points", 0)))

        segment_points_display = segment_points[["reading_ts", "temp_c", "temp_smooth", "ml_cluster", "is_lance_ml", "segment_id"]]
        st.dataframe(
            segment_points_display,
            use_container_width=True,
            column_config=_column_config_for(segment_points_display.columns),
        )

        st.download_button(
            "Descargar segmentos ML CSV",
            data=ml_segments.to_csv(index=False).encode("utf-8"),
            file_name="lances_detectados_ml.csv",
            mime="text/csv",
        )
        filtered_ml_segments = _filter_ml_segments_for_report(ml_segments)
        if filtered_ml_segments is not None and len(filtered_ml_segments) != len(ml_segments):
            st.download_button(
                "Descargar segmentos ML filtrados CSV",
                data=filtered_ml_segments.to_csv(index=False).encode("utf-8"),
                file_name="lances_detectados_ml_filtrados.csv",
                mime="text/csv",
            )

if lances_file and sensor_file:
    st.subheader("Comparación observador ↔ ML y TFM observado")
    st.caption(
        "Esta sección usa los lances del observador, calcula su TFM con el sensor y, si hay detección ML, los cruza contra los segmentos rojos de la gráfica."
    )
    lances_ts = build_lance_timestamps(
        lances,
        date_col=lance_date_col,
        start_col=lance_start_col,
        end_col=lance_end_col,
    )
    sensor_prepared = prepare_sensor_readings(sensor, time_col, temp_col)
    result = match_sensor_to_lances(lances_ts, sensor_prepared)
    ml_segments_for_compare = _filter_ml_segments_for_report(st.session_state.ml_analysis.segments) if st.session_state.ml_analysis else None
    result = _add_ml_overlap_to_observed_result(result, ml_segments_for_compare)
    st.session_state.analysis = {
        "lances_ts": lances_ts,
        "sensor_prepared": sensor_prepared,
        "result": result,
    }

if st.session_state.analysis:
    lances_ts = st.session_state.analysis["lances_ts"]
    sensor_prepared = st.session_state.analysis["sensor_prepared"]
    result = st.session_state.analysis["result"]
    lance_report = _build_lance_report(lances_ts, result)

    _show_methodology_note()

    st.subheader("Resultado comparativo")
    st.caption("Integra el archivo original de lances, el cálculo TFM por sensor y el cruce con segmentos detectados por ML.")
    if not lance_report.empty and st.session_state.observed_selected_lance_idx >= len(lance_report):
        st.session_state.observed_selected_lance_idx = 0
    comparison_view = st.dataframe(
        lance_report,
        use_container_width=True,
        column_config=_column_config_for(lance_report.columns),
        key="observed_lance_report_table",
        on_select="rerun",
        selection_mode="single-row",
        selection_default={
            "selection": {
                "rows": [st.session_state.observed_selected_lance_idx] if not lance_report.empty else [],
                "columns": [],
                "cells": [],
            }
        },
    )
    if comparison_view and comparison_view.selection.rows:
        st.session_state.observed_selected_lance_idx = comparison_view.selection.rows[0]

    ok_count = int((result["tfm_match_status"] == "ok").sum()) if not result.empty else 0
    total = len(result)
    ml_linked_count = int(result["ml_segment_id"].notna().sum()) if "ml_segment_id" in result.columns and not result.empty else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("Lances procesados", total)
    m2.metric("Matches OK", ok_count)
    m3.metric("Con segmento ML solapado", ml_linked_count)

    st.subheader("Auditoría de lecturas dentro del lance observado")
    if not result.empty:
        selected_idx = int(st.session_state.observed_selected_lance_idx)
        selected_label = f"{result.iloc[selected_idx].get('clave_viaje', '')} / {result.iloc[selected_idx].get('clave_lance', '')}".strip(" /")
        st.caption(f"Lance seleccionado desde la tabla comparativa: {selected_label}")
        selected_lance = lances_ts.iloc[selected_idx]
        window = sensor_readings_within_lance(selected_lance, sensor_prepared)
        window_display, removed_window_columns = drop_empty_columns(window, preserve_columns={"reading_ts", "temp_c"})

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Lecturas en ventana", len(window))
        c2.metric("Promedio TFM", f"{window['temp_c'].mean():.3f}" if len(window) else "—")
        c3.metric("Rango", f"{window['temp_c'].min():.3f} → {window['temp_c'].max():.3f}" if len(window) else "—")
        c4.metric("Delta temp", f"{window['temp_c'].max() - window['temp_c'].min():.3f}" if len(window) else "—")

        selected_result = result.iloc[selected_idx]
        if "ml_segment_label" in result.columns and pd.notna(selected_result.get("ml_segment_label")):
            st.info(
                f"Este lance observado se solapa con {selected_result.get('ml_segment_label')} "
                f"durante {selected_result.get('ml_overlap_min'):.1f} min. "
                f"Diferencia TFM observado - promedio ML: {selected_result.get('tfm_vs_ml_mean_delta'):.3f}."
            )
        elif "ml_segment_label" in result.columns:
            st.warning("Este lance observado no se solapa con ningún segmento ML detectado.")

        if removed_window_columns:
            st.caption(f"Columnas vacías ocultadas en esta auditoría: {', '.join(removed_window_columns)}")

        st.dataframe(window_display, use_container_width=True, column_config=_column_config_for(window_display.columns))

    csv_bytes = lance_report.to_csv(index=False).encode("utf-8")
    report_filename_input = st.text_input(
        "Nombre del archivo de reporte",
        value="reporte_lances_tfm_ml.csv",
        help="Puedes escribirlo con o sin .csv. La app limpiará caracteres problemáticos para crear un nombre de archivo seguro.",
    )
    st.download_button(
        "Descargar reporte de lances CSV",
        data=csv_bytes,
        file_name=_clean_csv_filename(report_filename_input, "reporte_lances_tfm_ml.csv"),
        mime="text/csv",
        use_container_width=True,
    )

st.divider()
st.caption("RedesyRaices/Sirbaa - 2026")
