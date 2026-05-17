"""
preprocessor.py — Agregación horaria y cálculo de geometría solar.

Etapa 0→1 del pipeline:
  · Valida cobertura mínima por hora (COVERAGE_MIN).
  · Agrega GHI a resolución horaria (media aritmética de muestras válidas).
  · Asigna timestamp_center = inicio_hora + 30 min (centro del intervalo).
  · Propaga columnas opcionales (T, P) por media.
  · Llama a solar_geometry.compute_geometry_df para cos_Z, G0n, G0h, AM, zenith.
  · Calcula Kt = GHI_h / G0h (con guard G0h ≤ 0 → NaN).

Entrada  : LoadedData (de io_handler)
Salida   : pd.DataFrame horario con columnas estandarizadas.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from config import COVERAGE_MIN, HOUR_OFFSET_MIN
from io_handler import LoadedData
from solar_geometry import compute_geometry_df, lon_to_360W


# ── Columnas de salida garantizadas ──────────────────────────────────────────
OUTPUT_COLS = [
    "timestamp_start",   # inicio del intervalo horario (UTC o local, sin offset)
    "timestamp_center",  # timestamp_start + 30 min  (usado por geometría solar)
    "GHI_h",             # GHI promedio horario [W/m²]
    "coverage",          # fracción de muestras válidas en el intervalo
    "cos_Z",             # cos(ángulo cenital) — integral analítica
    "G0n",               # irradiancia extraterrestre normal [W/m²]
    "G0h",               # irradiancia extraterrestre horizontal [W/m²]
    "zenith_deg",        # ángulo cenital [°]
    "AM",                # masa de aire (Kasten & Young)
    "Kt",                # clearness index = GHI_h / G0h
    # opcionales (presentes si los datos los tienen):
    # "temp_C", "pressure_kPa"
]


def aggregate_to_hourly(
    ld: LoadedData,
    lat_deg: float,
    lon_deg: float,
    tz_hr: float,
    temp_default_C: float = 20.0,
    pressure_default_kPa: float = 101.325,
) -> pd.DataFrame:
    """
    Agrega el DataFrame de alta resolución a resolución horaria.

    Parámetros
    ----------
    ld                   : LoadedData de io_handler.load_file
    lat_deg              : latitud [°N, negativo=Sur]
    lon_deg              : longitud [°E, negativo=Oeste]
    tz_hr                : UTC offset en horas (e.g. -3 para ART)
    temp_default_C       : temperatura por defecto si columna no disponible
    pressure_default_kPa : presión por defecto si columna no disponible

    Retorna
    -------
    pd.DataFrame con columnas de OUTPUT_COLS (más opcionales si hay datos).
    Filas nocturnas (G0h == 0) se conservan pero Kt = NaN.
    Horas con coverage < COVERAGE_MIN → GHI_h = NaN (hora inválida).
    """
    df = ld.df.copy()

    # ── 1. Usar timestamps ya parseados ──────────────────────────────────────
    ts = df["_timestamp"]

    # ── 2. Calcular muestras esperadas por hora ───────────────────────────────
    samples_per_hour = 3600 // ld.resolution_sec  # 60, 4 o 1

    # ── 3. Construir clave de hora (floor a hora) ─────────────────────────────
    df["_hour_key"] = ts.dt.floor("h")

    # ── 4. Agregar GHI ────────────────────────────────────────────────────────
    ghi_series = pd.to_numeric(df[ld.ghi_col], errors="coerce")
    df["_ghi"] = ghi_series

    # Agregación robusta compatible con todas las versiones de pandas
    _grp = df.groupby("_hour_key")["_ghi"]
    _n_valid  = _grp.apply(lambda s: int(s.notna().sum()))
    _coverage = _n_valid / samples_per_hour
    _ghi_mean = _grp.mean()
    _ghi_mean = _ghi_mean.where(_coverage >= COVERAGE_MIN, other=float("nan"))

    hourly_base = pd.DataFrame({
        "timestamp_start": _n_valid.index,
        "GHI_h":           _ghi_mean.values,
        "coverage":        _coverage.values,
    }).reset_index(drop=True)

    # ── 5. Agregar temperatura y presión (opcionales) ─────────────────────────
    if ld.temp_col:
        df["_temp"] = pd.to_numeric(df[ld.temp_col], errors="coerce")
        temp_agg = df.groupby("_hour_key")["_temp"].mean().reset_index()
        temp_agg.columns = ["timestamp_start", "temp_C"]
        hourly_base = hourly_base.merge(temp_agg, on="timestamp_start", how="left")
    else:
        hourly_base["temp_C"] = temp_default_C

    if ld.pressure_col:
        df["_pres"] = pd.to_numeric(df[ld.pressure_col], errors="coerce")
        # Detectar unidades: si mediana > 200 → Pa, convertir; si > 10 → hPa, convertir
        median_p = df["_pres"].median()
        if median_p > 200:
            df["_pres"] = df["_pres"] / 1000.0   # Pa → kPa
        elif median_p > 10:
            df["_pres"] = df["_pres"] / 10.0     # hPa → kPa
        pres_agg = df.groupby("_hour_key")["_pres"].mean().reset_index()
        pres_agg.columns = ["timestamp_start", "pressure_kPa"]
        hourly_base = hourly_base.merge(pres_agg, on="timestamp_start", how="left")
    else:
        hourly_base["pressure_kPa"] = pressure_default_kPa

    # ── 6. timestamp_center = timestamp_start + 30 min ───────────────────────
    hourly_base["timestamp_center"] = (
        hourly_base["timestamp_start"]
        + pd.Timedelta(minutes=HOUR_OFFSET_MIN)
    )

    # ── 7. Geometría solar ────────────────────────────────────────────────────
    lon_360W = lon_to_360W(lon_deg)
    geom = compute_geometry_df(
        df=hourly_base,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        tz_hr=tz_hr,
    )

    hourly_base["cos_Z"]      = geom["cos_Z"]
    hourly_base["G0n"]        = geom["G0n"]
    hourly_base["G0h"]        = geom["G0h"]
    hourly_base["zenith_deg"] = geom["zenith_deg"]
    hourly_base["AM"]         = geom["AM"]

    # ── 8. Índice de claridad Kt ──────────────────────────────────────────────
    #  Kt = GHI_h / G0h ; nocturno (G0h=0) → NaN
    g0h = hourly_base["G0h"].values
    ghi = hourly_base["GHI_h"].values

    with np.errstate(invalid="ignore", divide="ignore"):
        kt = np.where(g0h > 0, ghi / g0h, np.nan)
    hourly_base["Kt"] = kt

    # ── 9. Orden de columnas ──────────────────────────────────────────────────
    base_out = [
        "timestamp_start", "timestamp_center",
        "GHI_h", "coverage",
        "cos_Z", "G0n", "G0h", "zenith_deg", "AM", "Kt",
        "temp_C", "pressure_kPa",
    ]
    # Añadir cualquier columna extra que haya quedado
    extra = [c for c in hourly_base.columns if c not in base_out]
    hourly_base = hourly_base[base_out + extra]

    return hourly_base.reset_index(drop=True)


# ── Estadísticas rápidas de preprocesamiento ──────────────────────────────────

def preprocessing_summary(df_hourly: pd.DataFrame) -> dict:
    """
    Resumen del DataFrame horario para mostrar en UI antes de descomposición.
    """
    n_total    = len(df_hourly)
    n_daytime  = int((df_hourly["G0h"] > 0).sum())
    n_valid    = int(df_hourly["GHI_h"].notna().sum())
    n_invalid  = n_total - n_valid
    n_kt_enh   = int(((df_hourly["Kt"] > 1.0) & df_hourly["Kt"].notna()).sum())
    n_kt_unphy = int(((df_hourly["Kt"] > 1.05) & df_hourly["Kt"].notna()).sum())

    kt_day = df_hourly.loc[df_hourly["G0h"] > 0, "Kt"].dropna()

    return {
        "n_total_hours":      n_total,
        "n_daytime_hours":    n_daytime,
        "n_valid_hours":      n_valid,
        "n_invalid_hours":    n_invalid,
        "coverage_mean":      float(df_hourly["coverage"].mean()),
        "ghi_max":            float(df_hourly["GHI_h"].max()),
        "ghi_mean_daytime":   float(df_hourly.loc[df_hourly["G0h"] > 0, "GHI_h"].mean()),
        "kt_mean":            float(kt_day.mean()) if not kt_day.empty else float("nan"),
        "kt_max":             float(kt_day.max())  if not kt_day.empty else float("nan"),
        "n_kt_cloud_enh":     n_kt_enh,
        "n_kt_unphysical":    n_kt_unphy,
    }
