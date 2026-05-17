"""
validator.py — Validación de rangos físicos y flags de calidad.

Opera sobre el DataFrame post-descomposición.
Produce columnas de flag booleanas + score de calidad por fila.

Flags generados (columnas bool):
  flag_kt_cloud_enh    : Kt > 1.00 (cloud enhancement — válido pero inusual)
  flag_kt_unphysical   : Kt > 1.05 (probablemente error de sensor)
  flag_dni_high        : DNI > DNI_WARN_W_M2 (advertencia, no error)
  flag_dni_unphysical  : DNI > DNI_MAX_W_M2  (excede límite físico)
  flag_dni_negative    : DNI < 0
  flag_dhi_exceeds_ghi : DHI > GHI (violación energética)
  flag_dhi_negative    : DHI < 0
  flag_night_nonzero   : G0h == 0 pero GHI > 1 W/m² (ruido nocturno)
  flag_low_coverage    : cobertura de la hora < COVERAGE_MIN
  flag_invalid_hour    : GHI_h es NaN (hora descartada por preprocesador)

Columnas numéricas añadidas:
  quality_score : 100 − Σ penalidades  (0–100, mayor=mejor)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    KT_CLOUD_ENH, KT_UNPHYSICAL,
    DNI_MAX_W_M2, DNI_WARN_W_M2,
    COVERAGE_MIN, PENALTY,
)

# Umbral mínimo de GHI nocturno (offset de sensor)
_NIGHT_GHI_THRESH = 1.0   # W/m²


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade columnas de flag y quality_score al DataFrame de descomposición.

    Parámetros
    ----------
    df : DataFrame resultante de decomposition.run_decomposition

    Retorna
    -------
    DataFrame con columnas de flag y quality_score (inplace-safe: copia nueva).
    """
    out = df.copy()

    kt   = out["Kt"].values.astype(float)
    ghi  = out["GHI_h"].values.astype(float)
    dni  = out["DNI"].values.astype(float)
    dhi  = out["DHI"].values.astype(float)
    g0h  = out["G0h"].values.astype(float)
    cov  = out["coverage"].values.astype(float)

    # ── Flags booleanos ───────────────────────────────────────────────────────
    out["flag_kt_cloud_enh"]    = (kt > KT_CLOUD_ENH)  & ~np.isnan(kt)
    out["flag_kt_unphysical"]   = (kt > KT_UNPHYSICAL) & ~np.isnan(kt)
    out["flag_dni_high"]        = (dni > DNI_WARN_W_M2)  & ~np.isnan(dni)
    out["flag_dni_unphysical"]  = (dni > DNI_MAX_W_M2)   & ~np.isnan(dni)
    out["flag_dni_negative"]    = (dni < 0.0)             & ~np.isnan(dni)
    out["flag_dhi_exceeds_ghi"] = (dhi > ghi + 1.0)      & ~np.isnan(dhi) & ~np.isnan(ghi)
    out["flag_dhi_negative"]    = (dhi < 0.0)             & ~np.isnan(dhi)
    out["flag_night_nonzero"]   = (g0h <= 0) & (ghi > _NIGHT_GHI_THRESH) & ~np.isnan(ghi)
    out["flag_low_coverage"]    = (cov < COVERAGE_MIN)
    out["flag_invalid_hour"]    = np.isnan(ghi)

    # ── Quality score ─────────────────────────────────────────────────────────
    # Inicia en 100; se restan penalidades por flag activo
    score = np.full(len(out), 100.0)

    flag_penalty_map = {
        "flag_kt_cloud_enh":    PENALTY["kt_cloud_enh"],
        "flag_kt_unphysical":   PENALTY["kt_unphysical"],
        "flag_dni_high":        PENALTY["dni_high"],
        "flag_dni_unphysical":  PENALTY["dni_unphysical"],
        "flag_dni_negative":    PENALTY["dni_negative"],
        "flag_dhi_exceeds_ghi": PENALTY["dhi_exceeds_ghi"],
        "flag_dhi_negative":    PENALTY["dhi_negative"],
        "flag_night_nonzero":   PENALTY["night_nonzero"],
        "flag_low_coverage":    PENALTY["low_coverage"],
    }

    for flag_col, penalty in flag_penalty_map.items():
        score = np.where(out[flag_col].values.astype(bool), score - penalty, score)

    # Horas inválidas → score = NaN
    score = np.where(out["flag_invalid_hour"].values.astype(bool), float("nan"), score)

    # Clamp a [0, 100]
    score = np.clip(score, 0.0, 100.0)
    out["quality_score"] = score

    return out


def flag_summary(df_validated: pd.DataFrame) -> dict:
    """
    Resumen de flags: conteo de horas con cada flag activo.

    Retorna dict {flag_name: (count, pct_of_daytime)}.
    """
    # Solo columnas booleanas (excluye flag_dirint, flag_erbs que son strings del modelo)
    flag_cols = [
        c for c in df_validated.columns
        if c.startswith("flag_")
        and pd.api.types.is_bool_dtype(df_validated[c])
    ]

    n_daytime = int((df_validated["G0h"] > 0).sum())
    n_total   = len(df_validated)

    summary = {}
    for col in flag_cols:
        count = int(df_validated[col].sum())
        base  = n_daytime if col != "flag_invalid_hour" else n_total
        pct   = 100.0 * count / base if base > 0 else 0.0
        summary[col] = {"count": count, "pct": round(pct, 2)}

    return summary


def quality_distribution(df_validated: pd.DataFrame) -> dict:
    """
    Distribución del quality_score en bins de 10 puntos.
    Solo horas con score válido (no NaN).
    """
    scores = df_validated["quality_score"].dropna()
    bins = list(range(0, 101, 10))
    counts, edges = np.histogram(scores, bins=bins)
    return {
        f"{edges[i]:.0f}-{edges[i+1]:.0f}": int(counts[i])
        for i in range(len(counts))
    }
