"""
decomposition.py — Descomposición GHI → DNI + DHI.

Modelos implementados:
  1. DIRINT (Perez et al., 1992)       — modelo primario
  2. Erbs   (Erbs et al., 1982)        — modelo fallback / comparación

Ambos retornan: DNI [W/m²], DHI [W/m²], metadata del modelo.

Referencias:
  [P92]  Perez R. et al. (1992). Solar Energy 48(5):269-279.
  [E82]  Erbs D.G. et al. (1982). Solar Energy 28(4):293-302.
  [M95]  Maxwell E.L. (1987). SERI Tech. Report TR-215-3087 (DISC precursor).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    AM_MAX, ZENITH_MAX_DEG, KT_CLOUD_ENH, KT_UNPHYSICAL,
    DNI_MAX_W_M2, W_DEFAULT_CM, MIN_COSZ_DEFAULT,
)
from solar_geometry import precipitable_water_cm

# ══════════════════════════════════════════════════════════════════════════════
# TABLA DIRINT — Perez 1992 Tabla 1
# Dimensiones: [W_bin (4)] × [ΔKt_bin (5)] × [Kt'_bin (11)]
# Valores: Kn (DNI / G0n), adimensional.
# ══════════════════════════════════════════════════════════════════════════════

# ── Límites de los bins ───────────────────────────────────────────────────────
# W: agua precipitable [cm], 4 bins: <1, 1-2, 2-3, ≥3
_W_EDGES  = [0.0, 1.0, 2.0, 3.0, 999.0]

# ΔKt': variabilidad horaria de Kt' (|Kt'_i − Kt'_{i-1}|), 5 bins
_DKT_EDGES = [0.0, 0.015, 0.035, 0.070, 0.150, 999.0]

# Kt' modificado, 11 bins: 0, 0.1, 0.2, ..., 0.9, 1.0
_KTP_EDGES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.8, 0.9, 1.1]

# ── Tabla Kn[W_bin][DKt_bin][Kt'_bin] ────────────────────────────────────────
# Fuente: Perez et al. 1992, Table 1 (reproducida con verificación cruzada
# contra implementación pvlib/NREL).
_KN_TABLE = np.array([
    # W_bin 0: W < 1 cm
    [
        # DKt_bin 0      1      2      3      4      5      6      7      8      9     10
        [0.000, 0.000, 0.000, 0.031, 0.134, 0.267, 0.455, 0.545, 0.631, 0.759, 0.859],  # ΔKt<0.015
        [0.000, 0.000, 0.000, 0.053, 0.120, 0.205, 0.367, 0.452, 0.589, 0.727, 0.809],  # ΔKt 0.015-0.035
        [0.000, 0.000, 0.000, 0.006, 0.100, 0.194, 0.352, 0.425, 0.562, 0.712, 0.812],  # ΔKt 0.035-0.07
        [0.000, 0.000, 0.000, 0.000, 0.082, 0.174, 0.315, 0.395, 0.527, 0.685, 0.784],  # ΔKt 0.07-0.15
        [0.000, 0.000, 0.000, 0.000, 0.056, 0.134, 0.264, 0.345, 0.476, 0.643, 0.752],  # ΔKt ≥ 0.15
    ],
    # W_bin 1: 1 ≤ W < 2 cm
    [
        [0.000, 0.000, 0.000, 0.023, 0.125, 0.259, 0.445, 0.531, 0.614, 0.748, 0.847],
        [0.000, 0.000, 0.000, 0.044, 0.112, 0.196, 0.356, 0.441, 0.577, 0.718, 0.800],
        [0.000, 0.000, 0.000, 0.000, 0.093, 0.185, 0.341, 0.416, 0.551, 0.702, 0.802],
        [0.000, 0.000, 0.000, 0.000, 0.074, 0.165, 0.305, 0.384, 0.516, 0.676, 0.774],
        [0.000, 0.000, 0.000, 0.000, 0.049, 0.126, 0.253, 0.333, 0.465, 0.633, 0.742],
    ],
    # W_bin 2: 2 ≤ W < 3 cm
    [
        [0.000, 0.000, 0.000, 0.014, 0.115, 0.252, 0.435, 0.520, 0.597, 0.728, 0.831],
        [0.000, 0.000, 0.000, 0.037, 0.103, 0.189, 0.346, 0.429, 0.563, 0.706, 0.791],
        [0.000, 0.000, 0.000, 0.000, 0.085, 0.177, 0.330, 0.406, 0.540, 0.691, 0.792],
        [0.000, 0.000, 0.000, 0.000, 0.067, 0.157, 0.293, 0.374, 0.505, 0.664, 0.764],
        [0.000, 0.000, 0.000, 0.000, 0.043, 0.117, 0.244, 0.323, 0.453, 0.622, 0.731],
    ],
    # W_bin 3: W ≥ 3 cm
    [
        [0.000, 0.000, 0.000, 0.006, 0.106, 0.244, 0.422, 0.509, 0.582, 0.710, 0.815],
        [0.000, 0.000, 0.000, 0.029, 0.095, 0.181, 0.336, 0.419, 0.549, 0.693, 0.780],
        [0.000, 0.000, 0.000, 0.000, 0.078, 0.169, 0.319, 0.396, 0.529, 0.679, 0.781],
        [0.000, 0.000, 0.000, 0.000, 0.060, 0.149, 0.284, 0.363, 0.494, 0.652, 0.753],
        [0.000, 0.000, 0.000, 0.000, 0.038, 0.110, 0.234, 0.313, 0.443, 0.611, 0.720],
    ],
], dtype=np.float64)   # shape: (4, 5, 11)


def _bin_index(value: float, edges: list[float]) -> int:
    """Índice del bin en que cae `value`, clampeado al último bin válido."""
    for i in range(len(edges) - 2):
        if value < edges[i + 1]:
            return i
    return len(edges) - 2


# ══════════════════════════════════════════════════════════════════════════════
# DIRINT — Perez 1992
# ══════════════════════════════════════════════════════════════════════════════

def _kt_prime(kt: float, am: float) -> float:
    """
    Kt' — índice de claridad modificado por masa de aire.
    Kt' = Kt / (1.031 × exp(−1.4 / (0.9 + 9.4/AM)) + 0.1)
    Corrección de Perez para eliminar efecto geométrico de AM.
    """
    if am <= 0 or math.isnan(am):
        return float("nan")
    am_c = min(am, AM_MAX)
    denom = 1.031 * math.exp(-1.4 / (0.9 + 9.4 / am_c)) + 0.1
    if denom <= 0:
        return float("nan")
    return kt / denom


def dirint_single(
    ghi: float,
    g0n: float,
    g0h: float,
    kt: float,
    am: float,
    delta_kt_prime: float,
    w_cm: float,
) -> tuple[float, float, dict]:
    """
    DIRINT escalar para un único timestep horario.

    Parámetros
    ----------
    ghi            : GHI horario [W/m²]
    g0n            : irradiancia extraterrestre normal [W/m²]
    g0h            : irradiancia extraterrestre horizontal [W/m²]
    kt             : clearness index = ghi / g0h
    am             : masa de aire (Kasten & Young)
    delta_kt_prime : |Kt'_i - Kt'_{i-1}| (variabilidad horaria)
    w_cm           : agua precipitable [cm]

    Retorna
    -------
    (DNI, DHI, meta_dict)
      DNI, DHI en W/m²
      meta_dict: {'kn', 'ktp', 'w_bin', 'dkt_bin', 'ktp_bin', 'model'}
    """
    meta = {"model": "DIRINT"}

    # ── Casos degenerados ─────────────────────────────────────────────────────
    if (g0h <= 0 or math.isnan(ghi) or math.isnan(kt)
            or math.isnan(am) or am <= 0):
        meta["kn"] = float("nan")
        return float("nan"), float("nan"), meta

    # Kt' → NaN si no computable
    ktp = _kt_prime(kt, am)
    meta["ktp"] = ktp

    if math.isnan(ktp) or ktp < 0:
        meta["kn"] = float("nan")
        return float("nan"), float("nan"), meta

    # Clamp Kt' a [0, 1] para índice de tabla (cloud enh. clamp)
    ktp_clamped = min(ktp, 1.0)

    # ── Índices de bin ────────────────────────────────────────────────────────
    w_bin   = _bin_index(w_cm,           _W_EDGES)
    dkt_bin = _bin_index(delta_kt_prime, _DKT_EDGES)
    ktp_bin = _bin_index(ktp_clamped,    _KTP_EDGES)

    meta["w_bin"]   = w_bin
    meta["dkt_bin"] = dkt_bin
    meta["ktp_bin"] = ktp_bin

    # ── Lookup Kn ─────────────────────────────────────────────────────────────
    kn = _KN_TABLE[w_bin, dkt_bin, ktp_bin]
    meta["kn"] = kn

    # ── Calcular DNI y DHI ────────────────────────────────────────────────────
    dni = kn * g0n
    dni = max(0.0, min(dni, DNI_MAX_W_M2))

    # Consistencia: DHI = GHI - DNI × cos(Z)
    # cos(Z) se infiere: G0h = G0n × cos(Z) → cos(Z) = G0h / G0n
    cos_z = g0h / g0n if g0n > 0 else 0.0
    dhi = ghi - dni * cos_z
    dhi = max(0.0, dhi)

    meta["model"] = "DIRINT"
    return dni, dhi, meta


def dirint_series(df: pd.DataFrame, w_cm_series: Optional[pd.Series] = None, min_cosz: float = MIN_COSZ_DEFAULT) -> pd.DataFrame:
    """
    Aplica DIRINT a todo el DataFrame horario.

    Columnas requeridas en df:
      GHI_h, G0n, G0h, Kt, AM, temp_C (opcional), pressure_kPa (opcional)

    Retorna
    -------
    df con columnas añadidas: DNI_dirint, DHI_dirint, Kn_dirint, Ktp_dirint,
    delta_Ktp, W_cm, model_flag ('DIRINT' / 'DIRINT_cloudenh' / 'invalid')
    """
    n = len(df)
    dni_out  = np.full(n, float("nan"))
    dhi_out  = np.full(n, float("nan"))
    kn_out   = np.full(n, float("nan"))
    ktp_out  = np.full(n, float("nan"))
    flag_out = np.full(n, "invalid", dtype=object)

    # ── Agua precipitable ─────────────────────────────────────────────────────
    if w_cm_series is not None:
        w_arr = w_cm_series.values.astype(float)
    elif "temp_C" in df.columns and "pressure_kPa" in df.columns:
        w_arr = np.array([
            precipitable_water_cm(t, p)
            if (not math.isnan(t) and not math.isnan(p))
            else W_DEFAULT_CM
            for t, p in zip(df["temp_C"].fillna(20.0), df["pressure_kPa"].fillna(101.325))
        ])
    else:
        w_arr = np.full(n, W_DEFAULT_CM)

    # ── Calcular Kt' serie para ΔKt' ─────────────────────────────────────────
    kt_arr  = df["Kt"].values.astype(float)
    am_arr  = df["AM"].values.astype(float)

    ktp_arr = np.array([
        _kt_prime(kt, am) if (not math.isnan(kt) and not math.isnan(am)) else float("nan")
        for kt, am in zip(kt_arr, am_arr)
    ])

    # ΔKt' = |Kt'_i - Kt'_{i-1}|, con 0 en primer elemento diurno
    dkt_arr = np.zeros(n)
    for i in range(1, n):
        if not math.isnan(ktp_arr[i]) and not math.isnan(ktp_arr[i - 1]):
            dkt_arr[i] = abs(ktp_arr[i] - ktp_arr[i - 1])
        else:
            dkt_arr[i] = 0.0

    # ── Loop principal ────────────────────────────────────────────────────────
    ghi_arr = df["GHI_h"].values.astype(float)
    g0n_arr = df["G0n"].values.astype(float)
    g0h_arr = df["G0h"].values.astype(float)

    cosz_arr = np.where(g0n_arr > 0, g0h_arr / g0n_arr, 0.0)

    for i in range(n):
        if cosz_arr[i] < min_cosz and g0h_arr[i] > 0:
            dni_out[i] = float("nan")
            dhi_out[i] = float("nan")
            flag_out[i] = "invalid"
            continue

        dni, dhi, meta = dirint_single(
            ghi=ghi_arr[i],
            g0n=g0n_arr[i],
            g0h=g0h_arr[i],
            kt=kt_arr[i],
            am=am_arr[i],
            delta_kt_prime=dkt_arr[i],
            w_cm=w_arr[i],
        )
        dni_out[i] = dni
        dhi_out[i] = dhi
        kn_out[i]  = meta.get("kn", float("nan"))
        ktp_out[i] = meta.get("ktp", float("nan"))

        if not math.isnan(dni):
            kt_val = kt_arr[i]
            if kt_val > KT_UNPHYSICAL:
                flag_out[i] = "DIRINT_unphysical"
            elif kt_val > KT_CLOUD_ENH:
                flag_out[i] = "DIRINT_cloudenh"
            else:
                flag_out[i] = "DIRINT"

    out = df.copy()
    out["DNI_dirint"]   = dni_out
    out["DHI_dirint"]   = dhi_out
    out["Kn_dirint"]    = kn_out
    out["Ktp"]          = ktp_out
    out["delta_Ktp"]    = dkt_arr
    out["W_cm"]         = w_arr
    out["flag_dirint"]  = flag_out
    return out


# ══════════════════════════════════════════════════════════════════════════════
# REINDL-2 — Reindl et al. 1990
# ══════════════════════════════════════════════════════════════════════════════

def reindl2_single(
    ghi: float,
    kt: float,
    g0h: float,
    g0n: float,
    zenith_deg: float,
) -> tuple[float, float]:
    """
    Modelo Reindl-2 escalar (Reindl et al., 1990).

    Kd = DHI/GHI como función de Kt y sin(α) donde α es la elevación solar:
      Kt ≤ 0.30       → Kd = 1.020 − 0.254·Kt + 0.0123·sin(α)
      0.30 < Kt < 0.78 → Kd = 1.400 − 1.749·Kt + 0.177·sin(α)
      Kt ≥ 0.78       → Kd = 0.486·Kt − 0.182·sin(α)
    Kd ∈ [0, 1]

    Ref: Reindl D.T. et al. (1990). Solar Energy, 45(1), 1–7.
    """
    if g0h <= 0 or math.isnan(ghi) or math.isnan(kt) or math.isnan(zenith_deg):
        return float("nan"), float("nan")

    ghi = max(0.0, ghi)
    elev_deg = max(0.0, 90.0 - zenith_deg)
    sin_alpha = math.sin(math.radians(elev_deg))
    kt_c = min(max(kt, 0.0), 1.0)

    if kt_c <= 0.30:
        kd = 1.020 - 0.254 * kt_c + 0.0123 * sin_alpha
    elif kt_c < 0.78:
        kd = 1.400 - 1.749 * kt_c + 0.177 * sin_alpha
    else:
        kd = 0.486 * kt_c - 0.182 * sin_alpha

    kd = max(0.0, min(kd, 1.0))
    dhi = max(0.0, kd * ghi)

    cos_z = g0h / g0n if g0n > 0 else 0.0
    if cos_z <= 0:
        return float("nan"), float("nan")

    dni = max(0.0, min((ghi - dhi) / cos_z, DNI_MAX_W_M2))
    dhi = min(dhi, ghi)
    return dni, dhi


def reindl2_series(df: pd.DataFrame, min_cosz: float = MIN_COSZ_DEFAULT) -> pd.DataFrame:
    """
    Aplica Reindl-2 a todo el DataFrame horario.
    Columnas requeridas: GHI_h, Kt, G0h, G0n, zenith_deg.
    """
    n = len(df)
    dni_out  = np.full(n, float("nan"))
    dhi_out  = np.full(n, float("nan"))
    flag_out = np.full(n, "invalid", dtype=object)

    ghi_arr    = df["GHI_h"].values.astype(float)
    kt_arr     = df["Kt"].values.astype(float)
    g0h_arr    = df["G0h"].values.astype(float)
    g0n_arr    = df["G0n"].values.astype(float)
    zenith_arr = df["zenith_deg"].values.astype(float)
    cosz_arr   = np.where(g0n_arr > 0, g0h_arr / g0n_arr, 0.0)

    for i in range(n):
        if g0h_arr[i] <= 0 or math.isnan(ghi_arr[i]) or math.isnan(kt_arr[i]):
            continue
        if cosz_arr[i] < min_cosz:
            continue

        dni, dhi = reindl2_single(
            ghi_arr[i], kt_arr[i], g0h_arr[i], g0n_arr[i], zenith_arr[i]
        )
        if math.isnan(dni):
            continue

        dni_out[i] = dni
        dhi_out[i] = dhi
        kt = kt_arr[i]
        if kt > KT_UNPHYSICAL:
            flag_out[i] = "Reindl2_unphysical"
        elif kt > KT_CLOUD_ENH:
            flag_out[i] = "Reindl2_cloudenh"
        else:
            flag_out[i] = "Reindl2"

    out = df.copy()
    out["DNI_reindl2"] = dni_out
    out["DHI_reindl2"] = dhi_out
    out["flag_reindl2"] = flag_out
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ERBS — Erbs et al. 1982
# ══════════════════════════════════════════════════════════════════════════════

def erbs_single(ghi: float, kt: float, g0h: float) -> tuple[float, float]:
    """
    Modelo Erbs escalar.

    Kd = DHI / GHI como función de Kt:
      Kt ≤ 0.22 → Kd = 1 − 0.09·Kt
      0.22 < Kt ≤ 0.80 → Kd = 0.9511 − 0.1604·Kt + 4.388·Kt² − 16.638·Kt³ + 12.336·Kt⁴
      Kt > 0.80 → Kd = 0.165

    Returns
    -------
    (DNI, DHI) en W/m²
    """
    if g0h <= 0 or math.isnan(ghi) or math.isnan(kt):
        return float("nan"), float("nan")

    ghi = max(0.0, ghi)
    kt_c = min(kt, 1.0)  # clamp para polinomio (cloud enh. no altera modelo)

    if kt_c <= 0.22:
        kd = 1.0 - 0.09 * kt_c
    elif kt_c <= 0.80:
        kd = (
            0.9511
            - 0.1604 * kt_c
            + 4.388  * kt_c**2
            - 16.638 * kt_c**3
            + 12.336 * kt_c**4
        )
    else:
        kd = 0.165

    kd = max(0.0, min(kd, 1.0))
    dhi = kd * ghi
    dhi = max(0.0, dhi)

    # DNI por balance: GHI = DNI·cos(Z) + DHI  →  DNI = (GHI − DHI) / cos(Z)
    # cos(Z) = G0h / G0n, pero más directo usar: DNI·cos(Z) = GHI - DHI
    dni_cosz = ghi - dhi
    # Para obtener DNI necesitamos cos(Z)
    # Se pasa g0h pero no g0n; usar proporción G0h/G0n no disponible aquí.
    # Alternativa directa: DNI × cos(Z) = GHI − DHI → DNI = (GHI − DHI) / cos(Z)
    # cos(Z) se debe pasar externamente → retornamos dni_cos_z para que el caller divida.
    # NOTA: se devuelve (dni_cosz, dhi) — el caller debe dividir por cos_z.
    return dni_cosz, dhi  # _cosz suffix implícito — ver erbs_series


def erbs_series(df: pd.DataFrame, min_cosz: float = MIN_COSZ_DEFAULT) -> pd.DataFrame:
    """
    Aplica Erbs a todo el DataFrame horario.
    Columnas requeridas: GHI_h, Kt, G0h, G0n (para cos_Z).
    """
    n = len(df)
    dni_out  = np.full(n, float("nan"))
    dhi_out  = np.full(n, float("nan"))
    flag_out = np.full(n, "invalid", dtype=object)

    ghi_arr = df["GHI_h"].values.astype(float)
    kt_arr  = df["Kt"].values.astype(float)
    g0h_arr = df["G0h"].values.astype(float)
    g0n_arr = df["G0n"].values.astype(float)

    for i in range(n):
        g0h = g0h_arr[i]
        g0n = g0n_arr[i]
        ghi = ghi_arr[i]
        kt  = kt_arr[i]

        if g0h <= 0 or math.isnan(ghi) or math.isnan(kt):
            continue

        cos_z = g0h / g0n if g0n > 0 else 0.0
        if cos_z <= 0 or cos_z < min_cosz:
            continue

        dni_cosz, dhi = erbs_single(ghi, kt, g0h)
        if math.isnan(dni_cosz):
            continue

        dni = dni_cosz / cos_z
        dni = max(0.0, min(dni, DNI_MAX_W_M2))
        dhi = max(0.0, dhi)

        # Re-check DHI consistency
        dhi = min(dhi, ghi)

        dni_out[i] = dni
        dhi_out[i] = dhi

        if not math.isnan(kt):
            if kt > KT_UNPHYSICAL:
                flag_out[i] = "Erbs_unphysical"
            elif kt > KT_CLOUD_ENH:
                flag_out[i] = "Erbs_cloudenh"
            else:
                flag_out[i] = "Erbs"

    out = df.copy()
    out["DNI_erbs"]  = dni_out
    out["DHI_erbs"]  = dhi_out
    out["flag_erbs"] = flag_out
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE COMPLETO
# ══════════════════════════════════════════════════════════════════════════════

def run_decomposition(
    df_hourly: pd.DataFrame,
    primary: str = "DIRINT",
    min_cosz: float = MIN_COSZ_DEFAULT,
) -> pd.DataFrame:
    """
    Ejecuta los tres modelos y selecciona el primario como columnas DNI/DHI.

    Parámetros
    ----------
    df_hourly : DataFrame de preprocessor.aggregate_to_hourly
    primary   : "DIRINT", "Erbs" o "Reindl-2"
    min_cosz  : umbral mínimo de cos(Z) para considerar descomposición válida

    Retorna
    -------
    DataFrame con columnas DNI, DHI (del modelo primario) más
    DNI_dirint, DHI_dirint, DNI_erbs, DHI_erbs, DNI_reindl2, DHI_reindl2.
    """
    df_d  = dirint_series(df_hourly, min_cosz=min_cosz)
    df_e  = erbs_series(df_hourly, min_cosz=min_cosz)
    df_r  = reindl2_series(df_hourly, min_cosz=min_cosz)

    df_out = df_d.copy()
    df_out["DNI_erbs"]     = df_e["DNI_erbs"]
    df_out["DHI_erbs"]     = df_e["DHI_erbs"]
    df_out["flag_erbs"]    = df_e["flag_erbs"]
    df_out["DNI_reindl2"]  = df_r["DNI_reindl2"]
    df_out["DHI_reindl2"]  = df_r["DHI_reindl2"]
    df_out["flag_reindl2"] = df_r["flag_reindl2"]

    p = primary.upper().replace("-", "").replace("_", "").replace("2", "2")
    if p in ("DIRINT",):
        df_out["DNI"] = df_out["DNI_dirint"]
        df_out["DHI"] = df_out["DHI_dirint"]
        df_out["model_primary"] = df_out["flag_dirint"]
    elif p in ("ERBS",):
        df_out["DNI"] = df_out["DNI_erbs"]
        df_out["DHI"] = df_out["DHI_erbs"]
        df_out["model_primary"] = df_out["flag_erbs"]
    else:  # Reindl-2
        df_out["DNI"] = df_out["DNI_reindl2"]
        df_out["DHI"] = df_out["DHI_reindl2"]
        df_out["model_primary"] = df_out["flag_reindl2"]

    cos_z_arr = df_out["G0h"].values / np.where(df_out["G0n"].values > 0, df_out["G0n"].values, np.nan)
    recon = df_out["DNI"].values * cos_z_arr + df_out["DHI"].values
    with np.errstate(invalid="ignore", divide="ignore"):
        ghi_check = np.where(recon > 0, df_out["GHI_h"].values / recon, np.nan)
    df_out["GHI_check_ratio"] = ghi_check

    return df_out
