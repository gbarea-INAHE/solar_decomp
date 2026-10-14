"""
preprocessor.py — Agregación horaria y cálculo de geometría solar.

Etapa 0→1 del pipeline:
  · Valida cobertura mínima por hora (COVERAGE_MIN).
  · Agrega GHI a resolución horaria (media aritmética de muestras válidas).
  · Asigna timestamp_center = inicio_hora + 30 min (centro del intervalo).
  · Propaga columnas opcionales (T, P) por media; si hay punto de rocío (o humedad + T) agrega dew_point_C.
  · Llama a solar_geometry.compute_geometry_df para cos_Z, G0n, G0h, AM, zenith.
  · Calcula Kt = GHI_h / G0h (con guard G0h ≤ 0 → NaN).

Entrada  : LoadedData (de io_handler)
Salida   : pd.DataFrame horario con columnas estandarizadas.
"""
from __future__ import annotations

import math
from typing import Optional  # noqa: F401  (usado en firma de aggregate_to_hourly)

import numpy as np
import pandas as pd

from config import COVERAGE_MIN, HOUR_OFFSET_MIN
from io_handler import LoadedData
from solar_geometry import compute_geometry_df, dew_point_from_rh, lon_to_360W, pressure_from_altitude_kpa


def _warn_once(ld: LoadedData, msg: str) -> None:
    """Agrega el aviso a ld.warnings sin duplicarlo si el preprocesamiento se repite."""
    if msg not in ld.warnings:
        ld.warnings.append(msg)


def pressure_to_kpa(values: pd.Series) -> tuple[pd.Series, str, float]:
    """
    Convierte una columna de presión atmosférica de superficie a kPa, infiriendo la unidad por la MAGNITUD de su mediana:
      mediana > 2000        → Pa    (rango plausible 30 000–110 000)  → / 1000
      200 < mediana ≤ 2000  → hPa (= mbar) (300–1100)                 → / 10
      mediana ≤ 200         → kPa   (30–110)                          → sin cambio
    Después de convertir, la mediana debe estar entre 30 y 110 kPa; si no, falla con ValueError (no se adivina).
    Si la columna no tiene ningún valor numérico, se devuelve sin cambios (como antes).
    Devuelve (serie en kPa, unidad detectada, mediana original).
    """
    med = float(values.median())
    if not np.isfinite(med):
        return values, "sin datos", med
    unit, f = ("Pa", 1000.0) if med > 2000 else ("hPa", 10.0) if med > 200 else ("kPa", 1.0)
    if not 30.0 <= med / f <= 110.0:
        raise ValueError(
            f"La columna de presión tiene una mediana de {med:.4g}, que no corresponde a una presión atmosférica de superficie "
            "en kPa (30–110), hPa (300–1100) ni Pa (30 000–110 000). Revise la columna o sus unidades."
        )
    return values / f, unit, med


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
    # "temp_C", "pressure_kPa", "dew_point_C"
]


def aggregate_to_hourly(
    ld: LoadedData,
    lat_deg: float,
    lon_deg: float,
    tz_hr: float,
    altitude_m: float = 0.0,
    temp_default_C: float = 20.0,
    pressure_default_kPa: Optional[float] = None,
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

    # Presión por defecto: desde altitud si no se provee valor explícito
    p_default = pressure_default_kPa if pressure_default_kPa is not None else pressure_from_altitude_kpa(altitude_m)

    if ld.pressure_col:
        df["_pres"] = pd.to_numeric(df[ld.pressure_col], errors="coerce")
        # Unidad (Pa, hPa o kPa) inferida por la magnitud de la mediana; falla si no es una presión plausible
        df["_pres"], _p_unit, _p_med = pressure_to_kpa(df["_pres"])
        _warn_once(ld, f"Presión: la columna '{ld.pressure_col}' se interpretó en {_p_unit} (mediana {_p_med:.4g}) y se usa en kPa.")
        pres_agg = df.groupby("_hour_key")["_pres"].mean().reset_index()
        pres_agg.columns = ["timestamp_start", "pressure_kPa"]
        hourly_base = hourly_base.merge(pres_agg, on="timestamp_start", how="left")
    else:
        hourly_base["pressure_kPa"] = p_default

    # ── 5b. Punto de rocío (opcional; lo usa el DIRINT de Perez para el agua precipitable) ──
    #  Orden: columna de punto de rocío del archivo; si no hay, humedad relativa + temperatura (Magnus).
    #  Cada muestra inválida queda NaN (no se recorta ni se inventa) y se informa en ld.warnings; una hora sin
    #  ninguna muestra válida queda NaN y el DIRINT usa para ella el bin de «agua precipitable desconocida».
    dew_hourly = None
    if ld.dewpoint_col:
        td_raw = pd.to_numeric(df[ld.dewpoint_col], errors="coerce")
        td_ok = td_raw.where((td_raw >= -80.0) & (td_raw <= 40.0))
        n_bad = int(td_raw.notna().sum() - td_ok.notna().sum())
        if n_bad:
            _warn_once(ld, f"Punto de rocío '{ld.dewpoint_col}': {n_bad} valores fuera de −80…40 °C descartados (NaN).")
        df["_td"] = td_ok
        dew_hourly = df.groupby("_hour_key")["_td"].mean()
    elif ld.humidity_col and ld.temp_col:
        rh_raw = pd.to_numeric(df[ld.humidity_col], errors="coerce")
        rh_valid = rh_raw[(rh_raw > 0.0) & (rh_raw <= 100.0)]
        if rh_valid.notna().any() and float(rh_valid.max()) <= 1.0:
            _warn_once(ld, f"Humedad relativa '{ld.humidity_col}': todos los valores están entre 0 y 1; se esperan porcentajes (0–100). "
                           f"NO se usó para el punto de rocío (el DIRINT usa el bin de agua precipitable desconocida). Convierta a % y vuelva a cargar.")
        else:
            temp_row = pd.to_numeric(df[ld.temp_col], errors="coerce")
            td_row = dew_point_from_rh(temp_row.to_numpy(float), rh_raw.to_numpy(float))
            both = temp_row.notna().to_numpy() & rh_raw.notna().to_numpy()
            n_bad = int(both.sum() - np.isfinite(td_row).sum())
            if n_bad:
                _warn_once(ld, f"Humedad relativa '{ld.humidity_col}': {n_bad} muestras con humedad fuera de (0, 100] % o temperatura fuera de "
                               f"−45…60 °C quedaron sin punto de rocío (NaN).")
            df["_td"] = td_row
            dew_hourly = df.groupby("_hour_key")["_td"].mean()
    elif ld.humidity_col:
        _warn_once(ld, f"Humedad relativa '{ld.humidity_col}' detectada pero no hay columna de temperatura: no se puede calcular el punto de rocío "
                       f"(el DIRINT usa el bin de agua precipitable desconocida).")
    if dew_hourly is not None:
        dew_agg = dew_hourly.rename("dew_point_C").reset_index()
        dew_agg.columns = ["timestamp_start", "dew_point_C"]
        hourly_base = hourly_base.merge(dew_agg, on="timestamp_start", how="left")

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
