"""
test_pressure_units.py — Unidad de la presión atmosférica (Pa, hPa, kPa) en preprocessor.pressure_to_kpa / aggregate_to_hourly.

Antes de la v1.1.0 una columna en kPa (101.3) se dividía por 10 (→ 10.13 kPa) y una en hPa (1013) por 1000 (→ 1.013 kPa); solo Pa quedaba bien.

Uso: python test_pressure_units.py
"""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from decomposition import run_decomposition
from io_handler import load_file
from preprocessor import aggregate_to_hourly, pressure_to_kpa


def test_conversion():
    for label, val, unit in (("nivel del mar", 101.325, "kPa"), ("nivel del mar", 1013.25, "hPa"), ("nivel del mar", 101325.0, "Pa"),
                             ("3000 m", 70.1, "kPa"), ("3000 m", 701.0, "hPa"), ("3000 m", 70100.0, "Pa"),
                             ("límite bajo", 33.0, "kPa"), ("límite alto", 1100.0, "hPa")):
        kpa, u, med = pressure_to_kpa(pd.Series([val, val, val]))
        assert u == unit, (label, val, u)
        assert np.isclose(kpa.median(), val / {"kPa": 1, "hPa": 10, "Pa": 1000}[unit])
    print("[OK] Pa, hPa y kPa a nivel del mar y a 3000 m se convierten al mismo valor en kPa")


def test_errors_and_nan():
    for bad in (1.013, 5.0, 29.92, 150.0, 250.0, 1500.0, 5000.0, 200000.0):       # bar/atm, inHg, magnitudes que no son presión de superficie
        try:
            pressure_to_kpa(pd.Series([bad] * 5))
        except ValueError as e:
            assert "no corresponde a una presión atmosférica" in str(e)
        else:
            raise AssertionError(f"debía fallar con {bad}")
    s = pd.Series([np.nan, np.nan])
    out, unit, _ = pressure_to_kpa(s)
    assert unit == "sin datos" and out.isna().all()
    print("[OK] magnitudes implausibles (bar, inHg, 150, 250, 1500, 5000, 200000) fallan con mensaje explícito; sin datos se devuelve igual")


def test_pipeline_units():
    base = pd.read_csv("test_data_15min.csv")
    assert abs(base["pressure_kPa"].median() - 101.3) < 1e-9
    results = {}
    tmp = Path(tempfile.mkdtemp()) / "presion.csv"
    for unit, f in (("kPa", 1.0), ("hPa", 10.0), ("Pa", 1000.0)):
        d = base.copy()
        d["pressure"] = base["pressure_kPa"] * f
        d = d.drop(columns=["pressure_kPa"])
        d.to_csv(tmp, index=False)
        ld = load_file(tmp)
        assert ld.pressure_col == "pressure"
        h = aggregate_to_hourly(ld, lat_deg=-34.60, lon_deg=-58.38, tz_hr=-3.0)
        assert np.allclose(h["pressure_kPa"], 101.3), (unit, h["pressure_kPa"].describe().to_dict())
        assert any(f"interpretó en {unit}" in w for w in ld.warnings), ld.warnings
        results[unit] = run_decomposition(h, primary="DIRINT")["DNI_dirint"].to_numpy(float)
    assert np.array_equal(results["kPa"], results["hPa"], equal_nan=True) and np.array_equal(results["kPa"], results["Pa"], equal_nan=True)
    # la presión es la correcta: antes del arreglo la misma columna en kPa daba 10.13 kPa y otro DNI de DIRINT
    from decomposition import dirint_series
    h10 = h.copy()
    h10["pressure_kPa"] = 10.13
    wrong = dirint_series(h10)["DNI_dirint"].to_numpy(float)
    assert np.nanmax(np.abs(wrong - results["kPa"])) > 1.0, "la presión debe afectar al DIRINT"
    print("[OK] la misma presión en kPa, hPa o Pa da exactamente el mismo DNI de DIRINT (pressure_kPa = 101.3), y se informa la unidad")


if __name__ == "__main__":
    test_conversion()
    test_errors_and_nan()
    test_pipeline_units()
    print("[OK] Todas las pruebas de la unidad de presión pasaron.")
