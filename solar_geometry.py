"""
solar_geometry.py — Geometría solar.

Implementación basada en Spencer (1971) / Cooper (1969) / Duffie & Beckman.
Reemplaza el algoritmo Yallop anterior que carecía del término de rotación
terrestre en GHA, produciendo cos(Z) incorrecto para datos reales.

Referencias:
  [SP] Spencer, J.W. (1971). Fourier series representation of the position
       of the sun. Search, 2(5), 172.
  [CO] Cooper, P.I. (1969). The absorption of radiation in solar stills.
       Solar Energy, 12(3), 333–346.
  [DB] Duffie & Beckman (2006). Solar Engineering of Thermal Processes, 3rd Ed.
  [KY] Kasten & Young (1989). Applied Optics, 28(22):4735-4738.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Union

from config import GSC_W_M2, AM_MAX, ZENITH_MAX_DEG

# ── Tipos ─────────────────────────────────────────────────────────────────────
Numeric = Union[float, np.ndarray]


def lon_to_360W(lon_deg: float) -> float:
    """Convierte longitud E+/W- a convención West-positive 0..360."""
    if lon_deg < 0.0:
        return -lon_deg
    elif lon_deg == 0.0:
        return 0.0
    else:
        return 360.0 - lon_deg


def G0n_W_m2(doy: int) -> float:
    """
    Irradiancia extraterrestre normal [W/m²].
    G0n = Gsc × (1 + 0.033 × cos(2π·DOY/365))
    Ref [DB] p.10.
    """
    return GSC_W_M2 * (1.0 + 0.033 * math.cos(2.0 * math.pi * doy / 365.0))


def G0h_W_m2(doy: int, avg_cosZ: float) -> float:
    """Irradiancia extraterrestre horizontal [W/m²] = G0n × cos(Z)."""
    return G0n_W_m2(doy) * avg_cosZ


def air_mass_kasten(zenith_deg: float) -> float:
    """
    Masa de aire óptica relativa (Kasten & Young, 1989) [adimensional].
    AM = 1 / (cos(Z) + 0.50572 × (96.07995 − Z)^−1.6364)
    Retorna NaN si Z ≥ 90°. Clampea en AM_MAX para estabilidad numérica.
    """
    if zenith_deg >= 90.0:
        return float("nan")
    Z = zenith_deg
    AM = 1.0 / (
        math.cos(math.radians(Z))
        + 0.50572 * (96.07995 - Z) ** (-1.6364)
    )
    return min(AM, AM_MAX)


def pressure_from_altitude_kpa(altitude_m: float) -> float:
    """
    Presión atmosférica [kPa] estimada desde altitud [m] — atmósfera estándar ISA.
    Ref: US Standard Atmosphere (1976).
    """
    return 101.325 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588


def precipitable_water_cm(temp_C: float, pressure_kPa: float) -> float:
    """
    Estimación de agua precipitable W [cm] a partir de temperatura y presión.
    Aproximación con HR=70% (Leckner, 1978 simplificado).
    """
    T_K = temp_C + 273.15
    RH = 0.70
    es_hPa = 6.1078 * math.exp(17.269 * temp_C / (temp_C + 237.3))
    ea_hPa = RH * es_hPa
    W = 0.493 * ea_hPa / T_K
    return max(0.1, W)


# ══════════════════════════════════════════════════════════════════════════════
# GEOMETRÍA VECTORIZADA — Spencer (1971) / Cooper (1969)
# ══════════════════════════════════════════════════════════════════════════════

def compute_geometry_df(
    df,
    lat_deg: float,
    lon_deg: float,
    tz_hr: float,
) -> dict:
    """
    Calcula geometría solar para cada fila del DataFrame horario.
    Usa Spencer (1971) para ecuación del tiempo y Cooper (1969) para declinación.
    Retorna dict de arrays numpy: cos_Z, G0n, G0h, zenith_deg, AM.
    """
    import pandas as pd

    dt_center = pd.to_datetime(df["timestamp_center"])
    n = len(df)

    doy = dt_center.dt.dayofyear.to_numpy(dtype=float)
    hour_center = (
        dt_center.dt.hour.to_numpy(dtype=float)
        + dt_center.dt.minute.to_numpy(dtype=float) / 60.0
        + dt_center.dt.second.to_numpy(dtype=float) / 3600.0
    )

    # Declinación solar — Cooper (1969) [radianes]
    decl_rad = np.radians(23.45 * np.sin(np.radians(360.0 * (284.0 + doy) / 365.0)))

    # Ecuación del tiempo — Spencer (1971) [minutos]
    B = np.radians(360.0 * (doy - 81.0) / 364.0)
    eot_min = 9.87 * np.sin(2.0 * B) - 7.53 * np.cos(B) - 1.5 * np.sin(B)

    # Corrección de tiempo: diferencia entre meridiano estándar y longitud local
    lstm_deg = 15.0 * tz_hr          # meridiano estándar del huso horario
    tc_min = 4.0 * (lon_deg - lstm_deg) + eot_min

    # Tiempo solar local [horas] y ángulo horario solar [°]
    lst_hr = hour_center + tc_min / 60.0
    hra_deg = 15.0 * (lst_hr - 12.0)

    lat_rad = math.radians(lat_deg)

    # Promedio analítico de cos(Z) sobre intervalo horario ±7.5° (= ±30 min)
    w1_rad = np.radians(hra_deg - 7.5)
    w2_rad = np.radians(hra_deg + 7.5)
    dw = w2_rad - w1_rad             # siempre π/12

    c1 = np.cos(lat_rad) * np.cos(decl_rad)
    c2 = np.sin(lat_rad) * np.sin(decl_rad)
    avg_cosz = (c1 * (np.sin(w2_rad) - np.sin(w1_rad)) + c2 * dw) / dw
    avg_cosz = np.maximum(0.0, avg_cosz)

    # cos(Z) instantáneo en el centro del intervalo (para ángulo cenital)
    hra_c_rad = np.radians(hra_deg)
    cosz_inst = np.clip(
        np.sin(lat_rad) * np.sin(decl_rad)
        + np.cos(lat_rad) * np.cos(decl_rad) * np.cos(hra_c_rad),
        -1.0, 1.0,
    )
    zenith_deg_arr = np.where(cosz_inst > 0.0, np.degrees(np.arccos(cosz_inst)), 90.0)

    # Irradiancia extraterrestre
    e0 = 1.0 + 0.033 * np.cos(np.radians(360.0 * doy / 365.0))
    g0n_arr = GSC_W_M2 * e0
    g0h_arr = g0n_arr * avg_cosz

    # Masa de aire vectorizada
    am_arr = np.full(n, float("nan"))
    for i in range(n):
        if zenith_deg_arr[i] < 90.0:
            am_arr[i] = air_mass_kasten(float(zenith_deg_arr[i]))

    return {
        "cos_Z":      avg_cosz,
        "G0n":        g0n_arr,
        "G0h":        g0h_arr,
        "zenith_deg": zenith_deg_arr,
        "AM":         am_arr,
    }
