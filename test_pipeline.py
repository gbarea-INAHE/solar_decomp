"""
test_pipeline.py — Verificación end-to-end del pipeline de descomposición.
Usa test_data_15min.csv generado por generate_test_data.py.
"""
import sys
import math
import numpy as np
import pandas as pd

from io_handler import load_file, summarize_loaded
from preprocessor import aggregate_to_hourly, preprocessing_summary
from decomposition import run_decomposition
from validator import validate
from reporter import build_quality_report, export_csv

def approx(a, b, tol):
    return abs(a - b) <= tol

def test_io():
    ld = load_file("test_data_15min.csv")
    assert ld.resolution_sec == 900, f"Resolución esperada 900s, got {ld.resolution_sec}"
    assert ld.ghi_col == "GHI", f"GHI col: {ld.ghi_col}"
    assert ld.temp_col is not None, "Columna temp no detectada"
    s = summarize_loaded(ld)
    assert s["n_rows"] == 35040
    print(f"[OK] io_handler -- {s['n_rows']:,} filas, res={s['resolution']}, ghi_col='{s['ghi_col']}'")
    return ld

def test_preprocessor(ld):
    df_h = aggregate_to_hourly(ld, lat_deg=-34.60, lon_deg=-58.38, tz_hr=-3.0)
    assert len(df_h) == 8760, f"Esperaba 8760 horas, got {len(df_h)}"
    assert "GHI_h" in df_h.columns
    assert "Kt" in df_h.columns
    assert "G0h" in df_h.columns

    # Verificar que Kt en horas nocturnas es NaN
    night_kt = df_h.loc[df_h["G0h"] <= 0, "Kt"]
    assert night_kt.isna().all(), f"Kt nocturno debería ser NaN, got {night_kt.dropna().shape[0]} no-NaN"

    # Verificar que G0h > 0 en verano a mediodía (enero, hora 12)
    midday = df_h[
        (pd.to_datetime(df_h["timestamp_start"]).dt.month == 1) &
        (pd.to_datetime(df_h["timestamp_start"]).dt.hour == 12)
    ]
    assert (midday["G0h"] > 0).all(), "G0h debería ser >0 en enero mediodía (BS.AS.)"

    ps = preprocessing_summary(df_h)
    print(f"[OK] preprocessor -- {ps['n_daytime_hours']} h diurnas, Kt_mean={ps['kt_mean']:.3f}, "
          f"cloud_enh={ps['n_kt_cloud_enh']}")
    return df_h

def test_decomposition(df_h):
    df_d = run_decomposition(df_h, primary="DIRINT")
    assert "DNI_dirint" in df_d.columns
    assert "DHI_dirint" in df_d.columns
    assert "DNI_erbs"   in df_d.columns
    assert "DHI_erbs"   in df_d.columns

    day_mask = df_d["G0h"] > 0
    day = df_d[day_mask & df_d["DNI_dirint"].notna()]

    # DNI físicamente razonable
    assert (day["DNI_dirint"] >= 0).all(), "DNI_dirint negativo detectado"
    assert (day["DNI_dirint"] <= 1100).all(), f"DNI_dirint > 1100: {day['DNI_dirint'].max():.1f}"
    assert (day["DHI_dirint"] >= 0).all(), "DHI_dirint negativo detectado"

    # GHI_check_ratio debe estar cercano a 1 para horas limpias
    clean = df_d[day_mask & (df_d["Kt"] < 0.9) & (df_d["Kt"] > 0.1) & df_d["GHI_check_ratio"].notna()]
    ratio_mean = float(clean["GHI_check_ratio"].mean())
    assert approx(ratio_mean, 1.0, 0.05), f"GHI_check_ratio media={ratio_mean:.4f}, esperado ~1.0"

    print(f"[OK] decomposition -- DNI max={day['DNI_dirint'].max():.1f} W/m2, "
          f"DHI max={day['DHI_dirint'].max():.1f} W/m2, "
          f"GHI_check_ratio={ratio_mean:.4f}")
    return df_d

def test_validator(df_d):
    df_v = validate(df_d)
    assert "quality_score" in df_v.columns
    assert "flag_kt_cloud_enh" in df_v.columns

    scores = df_v["quality_score"].dropna()
    assert (scores >= 0).all() and (scores <= 100).all(), "Quality score fuera de [0,100]"

    n_enh   = int(df_v["flag_kt_cloud_enh"].sum())
    n_unphy = int(df_v["flag_kt_unphysical"].sum())
    q_mean  = float(scores.mean())
    print(f"[OK] validator -- quality_mean={q_mean:.1f}, cloud_enh={n_enh}, unphysical={n_unphy}")
    return df_v

def test_reporter(df_v):
    site_info = {"filename": "test", "lat_deg": -34.6, "lon_deg": -58.38, "tz_hr": -3.0, "resolution": "15-min"}
    rep = build_quality_report(df_v, site_info, "DIRINT")

    assert "summary" in rep
    assert rep["summary"]["n_total_hours"] == 8760
    assert rep["summary"]["ghi_total_Wh_m2"] > 0
    assert "monthly_stats" in rep
    assert len(rep["monthly_stats"]) == 12  # 12 meses

    csv_bytes = export_csv(df_v)
    assert len(csv_bytes) > 1000, "CSV vacío"

    print(f"[OK] reporter -- GHI_total={rep['summary']['ghi_total_Wh_m2']/1000:.0f} kWh/m2, "
          f"DNI_total={rep['summary']['dni_total_Wh_m2']/1000:.0f} kWh/m2, "
          f"q_mean={rep['summary']['quality_score_mean']:.1f}")

def main():
    print("=" * 60)
    print("TEST END-TO-END — Solar Decomp Pipeline")
    print("=" * 60)
    ld   = test_io()
    df_h = test_preprocessor(ld)
    df_d = test_decomposition(df_h)
    df_v = test_validator(df_d)
    test_reporter(df_v)
    print("=" * 60)
    print("[OK] Todos los tests pasaron.")

if __name__ == "__main__":
    main()
