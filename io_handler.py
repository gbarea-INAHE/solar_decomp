"""
io_handler.py — Carga, detección de columnas y análisis de resolución temporal.

Soporta:
  - CSV / Excel (.xlsx, .xls)
  - Detección automática de columna GHI (alias comunes)
  - Detección automática de timestamp (múltiples formatos)
  - Detección de resolución temporal: 1-min, 15-min, 60-min
  - Columnas opcionales: DNI, DHI, temperatura, presión
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config import RES_TOLERANCES

# ── Alias de columnas ─────────────────────────────────────────────────────────

# Orden: más específico primero (evita capturas erróneas)
GHI_ALIASES = [
    r"^ghi$", r"^global_horizontal_irradiance$", r"^global.*horiz",
    r"^irradiancia.*global", r"^gh$", r"^g_h$", r"^ghi_w",
    r"^solar.*global", r"^swdown$", r"^ssrd$",          # ERA5 / WRF
]
DNI_ALIASES = [
    r"^dni$", r"^direct_normal_irradiance$", r"^direct.*normal",
    r"^irradiancia.*directa", r"^bn$", r"^dni_w", r"^beam$",
]
DHI_ALIASES = [
    r"^dhi$", r"^diffuse_horizontal_irradiance$", r"^diffuse.*horiz",
    r"^irradiancia.*difusa", r"^dh$", r"^d_h$", r"^dif$",
]
TEMP_ALIASES = [
    r"^temp.*dry|^tdb$|^dry.*bulb|^temperatura|^temp_c|^air.*temp|^t2m$",
]
PRESSURE_ALIASES = [
    r"^pressure|^presion|^press_kpa|^p_kpa|^p_hpa|^sp$|^msl$",
]
TIMESTAMP_ALIASES = [
    r"^timestamp|^datetime|^fecha|^time$|^date$|^dt$|^hora$",
    r"^date.*time|^time.*stamp",
]


def _match_col(col: str, patterns: list[str]) -> bool:
    """True si el nombre de columna (normalizado) coincide con algún patrón."""
    c = col.strip().lower().replace(" ", "_").replace("-", "_")
    return any(re.search(p, c) for p in patterns)


def _find_col(df: pd.DataFrame, patterns: list[str]) -> Optional[str]:
    """Devuelve el nombre original de la primera columna que coincide."""
    for col in df.columns:
        if _match_col(col, patterns):
            return col
    return None


# ── Detección de timestamp ────────────────────────────────────────────────────

_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y%m%d%H%M",
    "%Y%m%d%H%M%S",
]


def _parse_timestamp_col(series: pd.Series) -> pd.Series:
    """
    Intenta parsear una Serie de strings/objects a datetime.
    Prueba formatos conocidos; fallback a pd.to_datetime(infer).
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    sample = series.dropna().iloc[0] if not series.dropna().empty else None
    if sample is None:
        raise ValueError("Columna de timestamp vacía.")

    # Intentar formatos explícitos primero
    for fmt in _TS_FORMATS:
        try:
            parsed = pd.to_datetime(series, format=fmt, errors="raise")
            return parsed
        except Exception:
            continue

    # Fallback inferido
    try:
        return pd.to_datetime(series, infer_datetime_format=True, errors="raise")
    except Exception:
        raise ValueError(
            f"No se pudo parsear la columna de timestamp. "
            f"Muestra: '{sample}'. Formatos soportados: {_TS_FORMATS}"
        )


def _build_timestamp_from_parts(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Si no hay columna timestamp unificada, intenta construirla desde
    columnas separadas: year, month, day, hour (y opcionalmente minute).
    """
    required = ["year", "month", "day", "hour"]
    cols_lower = {c.lower(): c for c in df.columns}
    if not all(r in cols_lower for r in required):
        return None

    try:
        ts = pd.to_datetime({
            "year":   df[cols_lower["year"]],
            "month":  df[cols_lower["month"]],
            "day":    df[cols_lower["day"]],
            "hour":   df[cols_lower["hour"]],
            "minute": df[cols_lower["minute"]] if "minute" in cols_lower else 0,
        })
        return ts
    except Exception:
        return None


# ── Detección de resolución temporal ─────────────────────────────────────────

def detect_resolution_sec(timestamps: pd.Series) -> int:
    """
    Detecta la resolución temporal en segundos a partir de las diferencias.

    Proceso:
      1. Calcula diferencias consecutivas en segundos.
      2. Toma la mediana (robusto frente a gaps).
      3. Clasifica en {60, 900, 3600} con tolerancias de config.RES_TOLERANCES.
      4. Si no encaja en ninguna → error con valor mediano informativo.

    Returns:
        int — 60, 900 o 3600
    """
    if len(timestamps) < 2:
        raise ValueError("Se necesitan al menos 2 registros para detectar resolución.")

    diffs_s = timestamps.sort_values().diff().dropna().dt.total_seconds()
    # Filtrar diferencias ≤ 0 o absurdamente grandes (>2 h)
    valid = diffs_s[(diffs_s > 0) & (diffs_s <= 7200)]
    if valid.empty:
        raise ValueError("No se encontraron diferencias de tiempo válidas.")

    median_s = float(valid.median())

    for res, (lo, hi) in RES_TOLERANCES.items():
        if lo <= median_s <= hi:
            return res

    raise ValueError(
        f"Resolución temporal no reconocida. Mediana de diferencias: {median_s:.0f} s. "
        f"Soportadas: 60 s (1-min), 900 s (15-min), 3600 s (60-min)."
    )


# ── Carga principal ───────────────────────────────────────────────────────────

class LoadedData:
    """Contenedor con el DataFrame cargado y metadata de detección."""

    def __init__(
        self,
        df: pd.DataFrame,
        timestamp_col: str,
        ghi_col: str,
        resolution_sec: int,
        dni_col: Optional[str] = None,
        dhi_col: Optional[str] = None,
        temp_col: Optional[str] = None,
        pressure_col: Optional[str] = None,
        warnings: Optional[list[str]] = None,
    ):
        self.df = df
        self.timestamp_col = timestamp_col
        self.ghi_col = ghi_col
        self.resolution_sec = resolution_sec
        self.dni_col = dni_col
        self.dhi_col = dhi_col
        self.temp_col = temp_col
        self.pressure_col = pressure_col
        self.warnings: list[str] = warnings or []

    @property
    def resolution_label(self) -> str:
        labels = {60: "1-min", 900: "15-min", 3600: "60-min"}
        return labels.get(self.resolution_sec, f"{self.resolution_sec}s")

    def __repr__(self) -> str:
        return (
            f"LoadedData(rows={len(self.df)}, res={self.resolution_label}, "
            f"ghi='{self.ghi_col}', ts='{self.timestamp_col}')"
        )


def load_file(
    path_or_buffer,
    timestamp_col: Optional[str] = None,
    ghi_col: Optional[str] = None,
) -> LoadedData:
    """
    Carga un CSV o Excel y detecta automáticamente columnas y resolución.

    Args:
        path_or_buffer : ruta (str/Path) o buffer de bytes (para Streamlit).
        timestamp_col  : nombre exacto de columna timestamp (override auto-detect).
        ghi_col        : nombre exacto de columna GHI (override auto-detect).

    Returns:
        LoadedData

    Raises:
        ValueError si no se puede detectar GHI o timestamp.
    """
    warnings_list: list[str] = []

    # ── Leer archivo ──────────────────────────────────────────────────────────
    ext = ""
    if isinstance(path_or_buffer, (str, Path)):
        ext = Path(path_or_buffer).suffix.lower()

    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path_or_buffer, engine="openpyxl")
    else:
        # CSV: intentar inferir separador
        df = _read_csv_robust(path_or_buffer)

    if df.empty:
        raise ValueError("El archivo está vacío o no contiene datos.")

    # ── Detectar / validar columna GHI ───────────────────────────────────────
    if ghi_col:
        if ghi_col not in df.columns:
            raise ValueError(f"Columna GHI especificada '{ghi_col}' no encontrada.")
    else:
        ghi_col = _find_col(df, GHI_ALIASES)
        if ghi_col is None:
            cols = list(df.columns)
            raise ValueError(
                f"No se detectó columna GHI. Columnas disponibles: {cols}. "
                f"Use el parámetro ghi_col= para especificarla."
            )

    # ── Detectar / validar columna timestamp ─────────────────────────────────
    if timestamp_col:
        if timestamp_col not in df.columns:
            raise ValueError(f"Columna timestamp '{timestamp_col}' no encontrada.")
        df["_timestamp"] = _parse_timestamp_col(df[timestamp_col])
    else:
        ts_col = _find_col(df, TIMESTAMP_ALIASES)
        if ts_col is not None:
            df["_timestamp"] = _parse_timestamp_col(df[ts_col])
            timestamp_col = ts_col
        else:
            # Intentar construir desde columnas separadas
            ts_built = _build_timestamp_from_parts(df)
            if ts_built is not None:
                df["_timestamp"] = ts_built
                timestamp_col = "_timestamp"
                warnings_list.append(
                    "Timestamp construido desde columnas separadas (year/month/day/hour)."
                )
            else:
                raise ValueError(
                    "No se detectó columna de timestamp. "
                    "Columnas esperadas: 'timestamp', 'datetime', 'fecha', 'date', etc., "
                    "o columnas separadas: year, month, day, hour."
                )

    # ── Detectar columnas opcionales ─────────────────────────────────────────
    dni_col  = _find_col(df, DNI_ALIASES)
    dhi_col  = _find_col(df, DHI_ALIASES)
    temp_col = _find_col(df, TEMP_ALIASES)
    pres_col = _find_col(df, PRESSURE_ALIASES)

    # ── Limpiar GHI: coerce numérico, NaN explícito ───────────────────────────
    df[ghi_col] = pd.to_numeric(df[ghi_col], errors="coerce")
    n_invalid = df[ghi_col].isna().sum()
    if n_invalid > 0:
        warnings_list.append(
            f"{n_invalid} valores no numéricos en '{ghi_col}' → NaN."
        )

    # ── Detectar resolución ───────────────────────────────────────────────────
    resolution_sec = detect_resolution_sec(df["_timestamp"])

    # ── Advertencias ─────────────────────────────────────────────────────────
    if dni_col:
        warnings_list.append(f"Columna DNI detectada: '{dni_col}' (referencia, no usada en descomposición).")
    if dhi_col:
        warnings_list.append(f"Columna DHI detectada: '{dhi_col}' (referencia, no usada en descomposición).")

    return LoadedData(
        df=df,
        timestamp_col=timestamp_col,
        ghi_col=ghi_col,
        resolution_sec=resolution_sec,
        dni_col=dni_col,
        dhi_col=dhi_col,
        temp_col=temp_col,
        pressure_col=pres_col,
        warnings=warnings_list,
    )


def _read_csv_robust(path_or_buffer) -> pd.DataFrame:
    """
    Lee CSV intentando separadores comunes (,  ;  \\t  |).
    Elige el que produce más columnas (heurístico simple).
    """
    separators = [",", ";", "\t", "|"]
    best_df = None
    best_ncols = 0

    for sep in separators:
        try:
            df = pd.read_csv(path_or_buffer, sep=sep, low_memory=False)
            if len(df.columns) > best_ncols:
                best_ncols = len(df.columns)
                best_df = df
            # Reset buffer si es seekable
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
        except Exception:
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
            continue

    if best_df is None or best_ncols < 2:
        raise ValueError("No se pudo leer el CSV. Verifique el formato y separador.")

    return best_df


# ── Utilidades de inspección ──────────────────────────────────────────────────

def summarize_loaded(ld: LoadedData) -> dict:
    """Resumen estadístico básico para mostrar en UI."""
    ghi = ld.df[ld.ghi_col].dropna()
    ts  = ld.df["_timestamp"]

    return {
        "n_rows":          len(ld.df),
        "resolution":      ld.resolution_label,
        "start":           str(ts.min()),
        "end":             str(ts.max()),
        "ghi_col":         ld.ghi_col,
        "ghi_min":         float(ghi.min()),
        "ghi_max":         float(ghi.max()),
        "ghi_mean":        float(ghi.mean()),
        "ghi_nan_pct":     float(ld.df[ld.ghi_col].isna().mean() * 100),
        "has_dni":         ld.dni_col is not None,
        "has_dhi":         ld.dhi_col is not None,
        "has_temp":        ld.temp_col is not None,
        "has_pressure":    ld.pressure_col is not None,
        "warnings":        ld.warnings,
    }
