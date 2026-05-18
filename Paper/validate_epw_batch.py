"""
validate_epw_batch.py — Validación científica de DIRINT / Erbs / Reindl-2
contra datos TMY de archivos EPW para todas las ciudades argentinas.

Uso:
    python validate_epw_batch.py

Salida:
    resultados_validacion/validacion_ciudades.xlsx   (métricas por ciudad)
    resultados_validacion/validacion_mensual.xlsx    (métricas mensuales)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Asegurar que el directorio raíz esté en el path ──────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from epw_parser import parse_epw
from solar_geometry import compute_geometry_df
from decomposition import run_decomposition

EPW_DIR    = ROOT / "EPWs"
OUT_DIR    = ROOT / "resultados_validacion"
OUT_DIR.mkdir(exist_ok=True)

MIN_GHI    = 10.0   # W/m²: ignorar horas de noche/casi-noche
MIN_COSZ   = 0.0174 # ~1°


# ── Métricas ──────────────────────────────────────────────────────────────────

def metrics(obs: np.ndarray, pred: np.ndarray) -> dict:
    mask = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[mask], pred[mask]
    n = len(obs)
    if n < 10:
        return dict(n=n, RMSE=np.nan, MBE=np.nan, R2=np.nan, nRMSE=np.nan)
    err  = pred - obs
    rmse = float(np.sqrt(np.mean(err**2)))
    mbe  = float(np.mean(err))
    ss_res = np.sum(err**2)
    ss_tot = np.sum((obs - obs.mean())**2)
    r2   = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    nrmse = rmse / obs.mean() * 100 if obs.mean() > 0 else np.nan
    return dict(n=n, RMSE=round(rmse, 1), MBE=round(mbe, 1),
                R2=round(r2, 4), nRMSE=round(nrmse, 1))


# ── Procesamiento de un EPW ───────────────────────────────────────────────────

def process_epw(epw_path: Path) -> tuple[dict, pd.DataFrame | None]:
    meta, df_raw = parse_epw(epw_path)

    # Filtrar horas de día con GHI válido
    df_day = df_raw[df_raw["GHI"] >= MIN_GHI].copy().reset_index(drop=True)
    if len(df_day) < 100:
        return meta, None

    # Construir DataFrame para run_decomposition
    df_hour = pd.DataFrame({
        "timestamp_start":  df_day["timestamp"],
        "timestamp_center": df_day["timestamp"] + pd.Timedelta(minutes=30),
        "GHI_h":            df_day["GHI"],
        "coverage":         1.0,
        "temp_C":           df_day["temp_C"],
        "pressure_kPa":     df_day["pressure_kPa"],
    })

    # Geometría solar
    geo = compute_geometry_df(df_hour, meta["lat"], meta["lon"], meta["tz"])
    df_hour["cos_Z"]      = geo["cos_Z"]
    df_hour["G0n"]        = geo["G0n"]
    df_hour["G0h"]        = geo["G0h"]
    df_hour["zenith_deg"] = geo["zenith_deg"]
    df_hour["AM"]         = geo["AM"]
    g0h = geo["G0h"]
    df_hour["Kt"] = np.where(g0h > 0, df_day["GHI"].values / g0h, np.nan)

    # Descomposición
    try:
        df_dec = run_decomposition(df_hour, primary="DIRINT", min_cosz=MIN_COSZ)
    except Exception as e:
        print(f"  ERROR en {meta['city']}: {e}")
        return meta, None

    # Adjuntar referencia EPW
    df_dec["DNI_ref"] = df_day["DNI_ref"].values
    df_dec["DHI_ref"] = df_day["DHI_ref"].values
    df_dec["month"]   = df_day["timestamp"].dt.month.values

    return meta, df_dec


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    epw_files = sorted(EPW_DIR.glob("*.EPW")) + sorted(EPW_DIR.glob("*.epw"))
    print(f"EPW encontrados: {len(epw_files)}")

    city_rows  = []
    monthly_rows = []

    for epw_path in epw_files:
        print(f"  Procesando: {epw_path.name} ...", end=" ", flush=True)
        meta, df = process_epw(epw_path)
        if df is None:
            print("SKIP (sin datos)")
            continue

        city = meta["city"]
        models = {
            "DIRINT":   ("DNI_dirint", "DHI_dirint"),
            "Erbs":     ("DNI_erbs",   "DHI_erbs"),
            "Reindl2":  ("DNI_reindl2","DHI_reindl2"),
        }

        for model, (dni_col, dhi_col) in models.items():
            if dni_col not in df.columns:
                continue
            m_dni = metrics(df["DNI_ref"].values, df[dni_col].values)
            m_dhi = metrics(df["DHI_ref"].values, df[dhi_col].values)
            city_rows.append({
                "Ciudad": city, "Lat": meta["lat"], "Lon": meta["lon"],
                "Elev_m": meta["elevation"], "TZ": meta["tz"],
                "Modelo": model, "N_horas": m_dni["n"],
                "DNI_RMSE": m_dni["RMSE"], "DNI_MBE": m_dni["MBE"],
                "DNI_R2":   m_dni["R2"],   "DNI_nRMSE": m_dni["nRMSE"],
                "DHI_RMSE": m_dhi["RMSE"], "DHI_MBE": m_dhi["MBE"],
                "DHI_R2":   m_dhi["R2"],   "DHI_nRMSE": m_dhi["nRMSE"],
            })

            # Métricas mensuales
            for month, grp in df.groupby("month"):
                m_d = metrics(grp["DNI_ref"].values, grp[dni_col].values)
                m_h = metrics(grp["DHI_ref"].values, grp[dhi_col].values)
                monthly_rows.append({
                    "Ciudad": city, "Modelo": model, "Mes": int(month),
                    "DNI_RMSE": m_d["RMSE"], "DNI_MBE": m_d["MBE"], "DNI_R2": m_d["R2"],
                    "DHI_RMSE": m_h["RMSE"], "DHI_MBE": m_h["MBE"], "DHI_R2": m_h["R2"],
                })

        print("OK")

    df_cities  = pd.DataFrame(city_rows)
    df_monthly = pd.DataFrame(monthly_rows)

    out_path = OUT_DIR / "validacion_ciudades.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_cities.to_excel(writer,  sheet_name="Por_Ciudad",  index=False)
        df_monthly.to_excel(writer, sheet_name="Por_Mes",     index=False)

        # Resumen: mejor modelo por ciudad según DNI_R2
        if not df_cities.empty:
            best = (
                df_cities.sort_values("DNI_R2", ascending=False)
                .groupby("Ciudad").first()
                .reset_index()[["Ciudad","Lat","Lon","Elev_m","Modelo",
                                "DNI_RMSE","DNI_MBE","DNI_R2","DNI_nRMSE",
                                "DHI_RMSE","DHI_MBE","DHI_R2"]]
                .rename(columns={"Modelo": "Mejor_modelo_DNI"})
            )
            best.to_excel(writer, sheet_name="Mejor_modelo", index=False)

    print(f"\nResultados guardados en: {out_path}")
    print(f"Ciudades procesadas: {df_cities['Ciudad'].nunique() if not df_cities.empty else 0}")


if __name__ == "__main__":
    main()
