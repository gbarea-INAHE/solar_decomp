"""
solar_geometry.py — Geometría solar.

Replica exacta del algoritmo Yallop implementado en Solar.as (Elements 1.0.6).
Todas las funciones son puras (sin estado), vectorizadas sobre arrays numpy.

Referencias:
  [Y]  Yallop, B.D. (1992). RGO NAO Technical Note No. 69.
  [DB] Duffie & Beckman (2006). Solar Engineering of Thermal Processes, 3rd Ed.
  [KY] Kasten & Young (1989). Applied Optics, 28(22):4735-4738.
"""
from __future__ import annotations
import math
import numpy as np
from datetime import datetime, timedelta
from typing import Union

from config import GSC_W_M2, AM_MAX, ZENITH_MAX_DEG

# ── Tipos ─────────────────────────────────────────────────────────────────────
Numeric = Union[float, np.ndarray]


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITMO YALLOP — réplica de Solar.as (_t, _G_deg, _C, _L_deg, etc.)
# ══════════════════════════════════════════════════════════════════════════════

def _integer_part(x: float) -> float:
    """Parte entera (floor para positivos). Idéntico a AdvMath.integerPart()."""
    return math.floor(x)


def _t_yallop(dt: datetime, tz_hr: float) -> float:
    """
    Parámetro temporal reducido de Yallop [Julian centuries desde J1976.0].
    Réplica exacta de Solar._t(dt, TZ_hrs).
    """
    y = dt.year if dt.month > 2 else dt.year - 1
    m = dt.month - 3 if dt.month > 2 else dt.month + 9
    UT = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 - tz_hr
    t = (
        UT / 24.0
        + dt.day
        + _integer_part(30.6 * m + 0.5)
        + _integer_part(365.25 * (y - 1976.0))
        - 8707.5
    ) / 36525.0
    return t


def _scale_to_360(x: float) -> float:
    """Reduce ángulo al rango [0, 360). Réplica de AdvMath.scaleToN(x, 360)."""
    return x % 360.0


def _G_deg(t: float) -> float:
    """Anomalía media del sol [°]. Réplica de Solar._G_deg(t)."""
    return _scale_to_360(357.528 + 35999.05 * t)


def _C(G_deg: float) -> float:
    """Ecuación del centro. Réplica de Solar._C(G_deg)."""
    G = math.radians(G_deg)
    return 1.915 * math.sin(G) + 0.020 * math.sin(2.0 * G)


def _L_deg(t: float, C: float) -> float:
    """Longitud eclíptica media [°]. Réplica de Solar._L_deg(t, C)."""
    return _scale_to_360(280.460 + 36000.770 * t + C)


def _alpha_deg(L_deg: float) -> float:
    """Ascensión recta del sol [°]. Réplica de Solar._alpha_deg(L_deg)."""
    L = math.radians(L_deg)
    return L_deg - 2.466 * math.sin(2.0 * L) + 0.053 * math.sin(4.0 * L)


def _obliquity_deg(t: float) -> float:
    """Oblicuidad de la eclíptica [°]."""
    return 23.4393 - 0.01300 * t


def _greenwich_hour_angle_deg(t: float, alpha_deg: float) -> float:
    """
    Ángulo horario de Greenwich [°].
    Réplica interna de Solar._greenwichHourAngle_deg.
    """
    G = _G_deg(t)
    C = _C(G)
    L = _L_deg(t, C)
    # GHA = GMST − alpha (simplificado vía Yallop)
    GHA = _scale_to_360(100.005 + 36000.770 * t + C)
    return GHA


def declination_deg(dt: datetime, tz_hr: float) -> float:
    """
    Declinación solar δ [°].
    Réplica exacta de Solar.declination_deg — algoritmo Yallop.
    """
    t = _t_yallop(dt, tz_hr)
    G = _G_deg(t)
    C = _C(G)
    L = _L_deg(t, C)
    alpha = _alpha_deg(L)
    eps = _obliquity_deg(t)
    decl = math.degrees(
        math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(alpha)))
    )
    return decl


def solar_hour_angle_deg(dt: datetime, tz_hr: float, lon_360W_deg: float) -> float:
    """
    Ángulo horario solar ω [°]. Positivo por la tarde.
    Réplica de Solar.solarHourAngle_deg(dt, TZ_hrs, long_360W_deg).
    """
    t = _t_yallop(dt, tz_hr)
    G = _G_deg(t)
    C = _C(G)
    GHA = _scale_to_360(100.005 + 36000.770 * t + C)
    # Local Hour Angle = GHA − longitud_oeste (convención W+)
    sha = _scale_to_360(GHA - lon_360W_deg)
    # Convertir a rango [-180, 180]: positivo = tarde, negativo = mañana
    if sha > 180.0:
        sha -= 360.0
    return sha


def lon_to_360W(lon_deg: float) -> float:
    """
    Convierte longitud E+/W- a convención West-positive 0..360.
    Réplica exacta de Solar.longToLong360W().
    """
    if lon_deg < 0.0:
        return -lon_deg
    elif lon_deg == 0.0:
        return 0.0
    else:
        return 360.0 - lon_deg


def avg_cos_zenith(
    dt_center: datetime,
    tz_hr: float,
    lat_deg: float,
    lon_360W_deg: float,
    interval_hr: float = 1.0,
) -> float:
    """
    INTEGRAL ANALÍTICA de cos(Z) sobre el intervalo centrado en dt_center.

    Fórmula [réplica de Solar.avg_cosz / Solar.avgCosZHourCentered]:
      avg = c3 × [c1×(sin(ω₂)−sin(ω₁)) + c2×(ω₂−ω₁)]
      donde:
        c1 = cos(φ)·cos(δ)
        c2 = sin(φ)·sin(δ)
        c3 = 1 / (ω₂−ω₁)   [ω en radianes]
        ω₁ = ω_center − Δω/2
        ω₂ = ω_center + Δω/2

    Retorna max(0, avg_cosZ) — nocturno → 0.
    """
    decl = declination_deg(dt_center, tz_hr)
    sha_center = solar_hour_angle_deg(dt_center, tz_hr, lon_360W_deg)

    delta_omega_deg = interval_hr * 15.0          # 15°/hora
    omega1_rad = math.radians(sha_center - delta_omega_deg / 2.0)
    omega2_rad = math.radians(sha_center + delta_omega_deg / 2.0)

    lat_rad  = math.radians(lat_deg)
    decl_rad = math.radians(decl)

    c1 = math.cos(lat_rad) * math.cos(decl_rad)
    c2 = math.sin(lat_rad) * math.sin(decl_rad)
    c3 = 1.0 / (omega2_rad - omega1_rad)

    avg_cz = c3 * (
        c1 * (math.sin(omega2_rad) - math.sin(omega1_rad))
        + c2 * (omega2_rad - omega1_rad)
    )
    return max(0.0, avg_cz)


def G0n_W_m2(doy: int) -> float:
    """
    Irradiancia extraterrestre normal [W/m²].
    G0n = Gsc × (1 + 0.033 × cos(2π·DOY/365))
    Ref [DB] p.10 — idéntico a Solar.irradianceExtNormal_W__m2().
    """
    return GSC_W_M2 * (1.0 + 0.033 * math.cos(2.0 * math.pi * doy / 365.0))


def G0h_W_m2(doy: int, avg_cosZ: float) -> float:
    """Irradiancia extraterrestre horizontal [W/m²] = G0n × cos(Z)."""
    return G0n_W_m2(doy) * avg_cosZ


def air_mass_kasten(zenith_deg: float) -> float:
    """
    Masa de aire óptica relativa (Kasten & Young, 1989) [adimensional].
    AM = 1 / (cos(Z) + 0.50572 × (96.07995 − Z)^−1.6364)
    Retorna NaN si Z ≥ 90° (noche).
    Clampea en AM_MAX para estabilidad numérica.
    """
    if zenith_deg >= 90.0:
        return float("nan")
    Z = zenith_deg
    AM = 1.0 / (
        math.cos(math.radians(Z))
        + 0.50572 * (96.07995 - Z) ** (-1.6364)
    )
    return min(AM, AM_MAX)


def precipitable_water_cm(temp_C: float, pressure_kPa: float) -> float:
    """
    Estimación de agua precipitable W [cm] a partir de temperatura y presión.
    Fórmula de Leckner (1978) simplificada:
      W = 0.493 × RH × exp(26.23 − 5416/T_K) / T_K
    Aproximación: asume HR=70% como valor típico si no se provee humedad.
    """
    T_K = temp_C + 273.15
    RH = 0.70  # aproximación conservadora
    # Presión parcial de vapor saturado (Magnus)
    es_hPa = 6.1078 * math.exp(17.269 * temp_C / (temp_C + 237.3))
    ea_hPa = RH * es_hPa
    W = 0.493 * ea_hPa / T_K
    return max(0.1, W)


# ══════════════════════════════════════════════════════════════════════════════
# VECTORIZACIÓN — opera sobre DataFrame pandas
# ══════════════════════════════════════════════════════════════════════════════

def compute_geometry_df(
    df,                       # DataFrame con col 'timestamp_center'
    lat_deg: float,
    lon_deg: float,
    tz_hr: float,
) -> dict:
    """
    Calcula geometría solar para cada fila del DataFrame horario.
    Retorna dict de arrays numpy: cos_Z, G0n, G0h, zenith_deg, AM.
    """
    import pandas as pd

    lon_360W = lon_to_360W(lon_deg)
    n = len(df)

    cos_Z_arr    = np.zeros(n)
    G0n_arr      = np.zeros(n)
    G0h_arr      = np.zeros(n)
    zenith_arr   = np.zeros(n)
    AM_arr       = np.full(n, float("nan"))

    for i, row in enumerate(df.itertuples()):
        dt = row.timestamp_center
        if hasattr(dt, "to_pydatetime"):
            dt = dt.to_pydatetime()

        doy = dt.timetuple().tm_yday

        cz   = avg_cos_zenith(dt, tz_hr, lat_deg, lon_360W, interval_hr=1.0)
        g0n  = G0n_W_m2(doy)
        g0h  = g0n * cz
        zen  = math.degrees(math.acos(min(cz, 1.0))) if cz > 0 else 90.0
        am   = air_mass_kasten(zen)

        cos_Z_arr[i]  = cz
        G0n_arr[i]    = g0n
        G0h_arr[i]    = g0h
        zenith_arr[i] = zen
        AM_arr[i]     = am

    return {
        "cos_Z":      cos_Z_arr,
        "G0n":        G0n_arr,
        "G0h":        G0h_arr,
        "zenith_deg": zenith_arr,
        "AM":         AM_arr,
    }
