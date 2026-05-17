"""
config.py — Constantes físicas y umbrales del sistema.
Centraliza todos los parámetros para facilitar ajustes sin tocar lógica.
"""

# ── Constante solar ────────────────────────────────────────────────────────────
GSC_W_M2 = 1367.0       # W/m² — igual que Elements (Solar.SOLAR_CONSTANT_W__m2)

# ── Límites físicos de irradiancia ────────────────────────────────────────────
DNI_MAX_W_M2  = 1100.0  # Límite físico a nivel de superficie
DNI_WARN_W_M2 =  900.0  # Umbral de advertencia (valores inusualmente altos)
DHI_MAX_W_M2  = 1000.0  # DHI no puede superar GHI ni este techo
GHI_MAX_W_M2  = 1600.0  # Con cloud enhancement extremo

# ── Índice de claridad ────────────────────────────────────────────────────────
KT_CLOUD_ENH  = 1.00    # Kt > 1.00 → posible cloud enhancement
KT_UNPHYSICAL = 1.05    # Kt > 1.05 → flag unphysical (error de sensor probable)

# ── Preprocesamiento temporal ─────────────────────────────────────────────────
COVERAGE_MIN    = 0.75  # Fracción mínima de muestras válidas por hora
HOUR_OFFSET_MIN = 30    # Offset al centro del intervalo horario (minutos)

# ── Masa de aire ─────────────────────────────────────────────────────────────
AM_MAX = 10.0            # Límite operativo de DIRINT (Perez 1992)
ZENITH_MAX_DEG = 87.0   # Ángulo cenital máximo para cálculo válido

# ── Agua precipitable ─────────────────────────────────────────────────────────
W_DEFAULT_CM = 1.5      # Valor climatológico por defecto si no se provee T/P

# ── Detección de resolución temporal (segundos) ───────────────────────────────
RES_TOLERANCES = {
    60:   (30,   90),    # 1-min:  mediana ∈ [30, 90] s
    900:  (600, 1200),   # 15-min: mediana ∈ [600, 1200] s
    3600: (3000, 3900),  # 60-min: mediana ∈ [3000, 3900] s
}

# ── Umbral mínimo de cos(Z) para descomposición válida ───────────────────────
MIN_COSZ_DEFAULT = 0.08   # ángulos cenitales > ~85° → resultados inestables

# ── Quality score — penalidades ───────────────────────────────────────────────
PENALTY = {
    "kt_cloud_enh":    10,
    "kt_unphysical":   25,
    "dni_high":        10,
    "dni_unphysical":  30,
    "dni_negative":    20,
    "dhi_exceeds_ghi": 20,
    "dhi_negative":    15,
    "night_nonzero":   15,
    "low_coverage":    20,
}
