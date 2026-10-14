"""
reference.py — Consistencia de los modelos con un DNI / DHI de referencia que trae el archivo (EPW u otro).

Qué mide y qué NO mide:
  - Compara la salida horaria de cada modelo con las columnas DNI y/o DHI del archivo cargado. Es una medida de
    CONSISTENCIA con esa referencia, no de exactitud: solo es exactitud si la referencia es una medición.
  - En los archivos IWEC2 el DNI y el DHI no son mediciones: el DNI es una partición (tipo Gompertz) de la GHI del
    propio archivo y el DHI resulta por cierre. En ese caso una diferencia pequeña indica parecido con ese generador.
  - No incluye intervalos de confianza ni pruebas estadísticas.

Dominio por defecto (el del análisis asociado): horas con GHI horaria >= 10 W/m² y cos θz >= 0.20.
Métricas: n, RMSE, MBE (modelo − referencia), nRMSE (% de la media de la referencia) y R² = 1 − SSE/SST.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = (("DIRINT", "dirint"), ("Erbs", "erbs"), ("Reindl-2", "reindl2"))
GHI_MIN_DEFAULT = 10.0
COSZ_MIN_DEFAULT = 0.20


def hourly_reference(ld, timestamps: pd.Series) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    Media horaria de las columnas DNI y DHI del archivo cargado, alineada con `timestamps` (timestamp_start de la
    serie horaria). Devuelve None para la variable que el archivo no trae.
    """
    key = ld.df["_timestamp"].dt.floor("h")

    def _one(col):
        if not col:
            return None
        s = pd.to_numeric(ld.df[col], errors="coerce").groupby(key).mean()
        return s.reindex(pd.to_datetime(timestamps)).to_numpy(dtype=float)

    return _one(ld.dni_col), _one(ld.dhi_col)


def _metrics(obs: np.ndarray, pred: np.ndarray) -> dict:
    ok = np.isfinite(obs) & np.isfinite(pred)
    n = int(ok.sum())
    if n < 2:
        return dict(n=n, RMSE=np.nan, MBE=np.nan, nRMSE_pct=np.nan, R2=np.nan)
    o, p = obs[ok], pred[ok]
    e = p - o
    rmse = float(np.sqrt(np.mean(e ** 2)))
    sst = float(((o - o.mean()) ** 2).sum())
    return dict(
        n=n, RMSE=rmse, MBE=float(e.mean()),
        nRMSE_pct=rmse / float(o.mean()) * 100.0 if o.mean() != 0 else np.nan,
        R2=float(1.0 - (e ** 2).sum() / sst) if sst > 0 else np.nan,
    )


def consistency_table(
    df: pd.DataFrame,
    ref_dni: np.ndarray | None,
    ref_dhi: np.ndarray | None,
    cosz_min: float = COSZ_MIN_DEFAULT,
    ghi_min: float = GHI_MIN_DEFAULT,
) -> pd.DataFrame:
    """
    Tabla (una fila por variable y modelo) de la consistencia de DNI_*/DHI_* de `df` con las referencias dadas,
    en las horas con GHI_h >= ghi_min y cos_Z >= cosz_min. `df` es la salida de run_decomposition.
    Falla con ValueError si faltan columnas o si las longitudes no coinciden.
    """
    for col in ("GHI_h", "cos_Z"):
        if col not in df.columns:
            raise ValueError(f"Falta la columna '{col}' en el resultado.")
    dom = (df["GHI_h"].to_numpy(float) >= ghi_min) & (df["cos_Z"].to_numpy(float) >= cosz_min)
    rows = []
    for var, ref in (("DNI", ref_dni), ("DHI", ref_dhi)):
        if ref is None:
            continue
        ref = np.asarray(ref, dtype=float)
        if len(ref) != len(df):
            raise ValueError(f"La referencia de {var} tiene {len(ref)} valores y el resultado {len(df)} filas.")
        for label, tag in MODELS:
            col = f"{var}_{tag}"
            if col not in df.columns:
                raise ValueError(f"Falta la columna '{col}' en el resultado.")
            pred = np.where(dom, df[col].to_numpy(float), np.nan)
            rows.append({"Variable": var, "Modelo": label, **_metrics(np.where(dom, ref, np.nan), pred)})
    return pd.DataFrame(rows, columns=["Variable", "Modelo", "n", "RMSE", "MBE", "nRMSE_pct", "R2"])
