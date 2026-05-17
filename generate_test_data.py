"""
generate_test_data.py — Genera CSV de prueba con datos sintéticos realistas.

Produce un año de datos a 15 minutos (35040 filas) para Buenos Aires.
GHI sintético = G0h × clearness_index + ruido, con ciclo estacional.

Uso: python generate_test_data.py
Salida: test_data_15min.csv
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Sitio: Buenos Aires
LAT  = -34.60
LON  = -58.38
TZ   = -3.0
YEAR = 2023

# ── Geometría solar simplificada para generación sintética ────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from solar_geometry import avg_cos_zenith, G0n_W_m2, lon_to_360W

def generate_synthetic_ghi(rng_seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    lon_w = lon_to_360W(LON)

    # Timestamps: 1-ene-2023 00:00 a 31-dic-2023 23:45
    start = datetime(YEAR, 1, 1, 0, 0, 0)
    n_steps = 35040  # 365 × 24 × 4
    timestamps = [start + timedelta(minutes=15 * i) for i in range(n_steps)]

    ghi_vals  = []
    temp_vals = []

    for dt in timestamps:
        doy = dt.timetuple().tm_yday

        # cos(Z) analítico sobre intervalo de 15 min → escalar a 1h equivalente
        cz = avg_cos_zenith(dt, TZ, LAT, lon_w, interval_hr=0.25)

        if cz <= 0.01:
            ghi_vals.append(0.0)
        else:
            g0n = G0n_W_m2(doy)
            g0h = g0n * cz

            # Índice de claridad base con variabilidad estacional
            # Buenos Aires: verano más nublado (Kt~0.45), invierno más claro (Kt~0.60)
            kt_base = 0.52 + 0.08 * math.cos(2 * math.pi * (doy - 15) / 365)

            # Variabilidad aleatoria (simula nubosidad)
            kt_noise = rng.normal(0, 0.12)
            kt = np.clip(kt_base + kt_noise, 0.0, 1.08)

            ghi = g0h * kt
            ghi = max(0.0, ghi)
            ghi_vals.append(round(ghi, 2))

        # Temperatura sintética: ciclo diario + estacional
        hour = dt.hour + dt.minute / 60.0
        t_base = 15.0 + 10.0 * math.cos(2 * math.pi * (doy - 15) / 365)  # estacional
        t_daily = -5.0 * math.cos(2 * math.pi * (hour - 14) / 24)          # diario
        temp = t_base + t_daily + rng.normal(0, 0.5)
        temp_vals.append(round(float(temp), 1))

    df = pd.DataFrame({
        "timestamp":    timestamps,
        "GHI":          ghi_vals,
        "temp_C":       temp_vals,
        "pressure_kPa": 101.3,
    })

    # Introducir 2% de NaN en GHI (datos faltantes realistas)
    nan_mask = rng.random(n_steps) < 0.02
    df.loc[nan_mask, "GHI"] = float("nan")

    return df


if __name__ == "__main__":
    print("Generando datos sintéticos a 15-min para Buenos Aires (2023)...")
    df = generate_synthetic_ghi()
    out = "test_data_15min.csv"
    df.to_csv(out, index=False)
    print(f"Guardado: {out}  ({len(df):,} filas)")
    print(f"GHI max: {df['GHI'].max():.1f} W/m², NaN: {df['GHI'].isna().sum()} filas")
