"""
test_epw_loader.py — Lectura de archivos EPW (io_handler.read_epw / load_file) con EPW SINTÉTICOS generados aquí.
No se versiona ni se usa ningún archivo EPW real (los IWEC2 tienen licencia ASHRAE).

Uso: python test_epw_loader.py
"""
import io
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from decomposition import run_decomposition
from io_handler import load_file, read_epw
from preprocessor import aggregate_to_hourly

LAT, LON, TZ, ELEV = -34.60, -58.40, -3.0, 25.0
HEADER = [
    f"LOCATION,TESTVILLE,-,ARG,SYNTH,000000,{LAT:.2f},{LON:.2f},{TZ:.1f},{ELEV:.1f}",
    "DESIGN CONDITIONS,0",
    "TYPICAL/EXTREME PERIODS,0",
    "GROUND TEMPERATURES,0",
    "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
    "COMMENTS 1,archivo sintetico de prueba",
    "COMMENTS 2,sin datos reales",
    "DATA PERIODS,1,1,Data,Sunday, 1/ 1,12/31",
]
NDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def make_rows(year_of_month=lambda m: 2001, leap=False):
    """Registros EPW de 35 campos, 1 por hora, en orden de calendario."""
    rows = []
    for m in range(1, 13):
        nd = NDAYS[m - 1] + (1 if (leap and m == 2) else 0)
        for d in range(1, nd + 1):
            for h in range(1, 25):
                sun = max(0.0, np.sin(np.pi * (h - 6.5) / 12.0)) if 7 <= h <= 18 else 0.0
                ghi = 900.0 * sun * (0.6 + 0.4 * ((d % 3) / 2.0))
                dni, dhi = 0.6 * ghi, 0.4 * ghi
                f = ["0"] * 35
                f[0], f[1], f[2], f[3], f[4], f[5] = str(year_of_month(m)), str(m), str(d), str(h), "60", "A7A7A7A7"
                f[6], f[7], f[8], f[9] = f"{15 + 8 * sun:.1f}", "8.0", "60", "101300"
                f[10], f[11], f[13], f[14], f[15] = "0", "1367", f"{ghi:.0f}", f"{dni:.0f}", f"{dhi:.0f}"
                rows.append(",".join(f))
    return rows


def write_epw(lines, name="test.epw", folder=None):
    folder = Path(folder or tempfile.mkdtemp())
    p = folder / name
    p.write_text("\n".join(lines) + "\n", encoding="latin-1")
    return p


def base_lines(**kw):
    return HEADER + make_rows(**kw)


def raises(lines, fragment, name="malo.epw"):
    p = write_epw(lines, name)
    try:
        read_epw(p)
    except ValueError as e:
        assert fragment in str(e), f"mensaje inesperado: {e!r} (se esperaba «{fragment}»)"
        return
    raise AssertionError(f"debía fallar con «{fragment}»")


def test_parse_basic():
    lines = base_lines()
    lines[8 + 10] = lines[8 + 10].replace(",A7A7A7A7,", ",A7A7A7A7,", 1)
    # introducir códigos de dato faltante en la fila 11 (GHI 9999, presión 999999, punto de rocío 99.9, HR 999)
    f = lines[8 + 10].split(",")
    f[13], f[9], f[7], f[8] = "9999", "999999", "99.9", "999"
    lines[8 + 10] = ",".join(f)
    meta, df = read_epw(write_epw(lines))
    assert (meta["lat"], meta["lon"], meta["tz"], meta["elev"]) == (LAT, LON, TZ, ELEV)
    assert meta["city"] == "TESTVILLE" and meta["country"] == "ARG" and meta["n_rows"] == 8760 and meta["years"] == [2001]
    assert len(df) == 8760
    ts = df["timestamp"]
    assert ts.iloc[0] == pd.Timestamp("2001-01-01 00:00"), "la hora 1 debe ser el intervalo que empieza a las 00:00"
    assert ts.iloc[23] == pd.Timestamp("2001-01-01 23:00"), "la hora 24 debe ser 23:00 del mismo día (no 00:00 del siguiente)"
    assert ts.iloc[24] == pd.Timestamp("2001-01-02 00:00")
    assert np.isnan(df["GHI"].iloc[10]) and np.isnan(df["pressure_Pa"].iloc[10]) and np.isnan(df["dew_point_C"].iloc[10]) and np.isnan(df["RH"].iloc[10])
    assert df["pressure_Pa"].iloc[0] == 101300.0 and df["dew_point_C"].iloc[0] == 8.0 and df["RH"].iloc[0] == 60.0
    print("[OK] read_epw: encabezado, hora final -> inicio del intervalo, códigos de dato faltante -> NaN, presión en Pa")


def test_load_file_and_pipeline():
    p = write_epw(base_lines(), "sintetico.EPW")                 # extensión en mayúsculas
    ld = load_file(p)
    assert ld.is_epw and ld.epw_meta["city"] == "TESTVILLE"
    assert (ld.ghi_col, ld.dni_col, ld.dhi_col, ld.temp_col, ld.pressure_col, ld.humidity_col, ld.dewpoint_col) == (
        "GHI", "DNI", "DHI", "temp_C", "pressure_Pa", "RH", "dew_point_C")
    assert ld.resolution_sec == 3600
    assert any("EPW «TESTVILLE»" in w for w in ld.warnings) and any("Columna DNI detectada" in w for w in ld.warnings)
    df_h = aggregate_to_hourly(ld, lat_deg=ld.epw_meta["lat"], lon_deg=ld.epw_meta["lon"], tz_hr=ld.epw_meta["tz"], altitude_m=ld.epw_meta["elev"])
    assert len(df_h) == 8760
    raw = pd.read_csv(io.StringIO("\n".join(l.split(",")[13] for l in base_lines()[8:])), header=None)[0].to_numpy(float)
    assert np.allclose(df_h["GHI_h"].to_numpy(float), raw, equal_nan=True), "GHI horaria debe ser la del EPW"
    assert np.allclose(df_h["pressure_kPa"], 101.3), "debe usar la presión del archivo (Pa -> kPa)"
    assert (df_h["dew_point_C"] == 8.0).all(), "el punto de rocío del archivo tiene prioridad sobre humedad + temperatura"
    res = run_decomposition(df_h, primary="DIRINT")
    assert res["DNI_dirint"].notna().sum() > 1000 and (res["dirint_W_source"].dropna() == "unknown_bin").all()
    res_td = run_decomposition(df_h, primary="DIRINT", use_dew_point=True)
    assert (res_td["dirint_W_source"].dropna() == "dew_point").any()
    print("[OK] load_file(.EPW) + aggregate_to_hourly + run_decomposition (con y sin punto de rocío)")


class Named(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


def test_buffer():
    data = "\n".join(base_lines()).encode("latin-1")
    buf = Named(data, "subido.epw")
    ld = load_file(buf)
    assert ld.is_epw and len(ld.df) == 8760 and buf.tell() == 0, "el buffer debe quedar al inicio"
    ld2 = load_file(write_epw(base_lines()))
    assert (ld.df["GHI"].fillna(-1) == ld2.df["GHI"].fillna(-1)).all()
    print("[OK] load_file con buffer (como el UploadedFile de Streamlit) = ruta")


def test_tmy_and_leap():
    ld = load_file(write_epw(base_lines(year_of_month=lambda m: 1990 + m), "tmy.epw"))
    assert len(ld.epw_meta["years"]) == 12 and any("años distintos" in w for w in ld.warnings)
    df_h = aggregate_to_hourly(ld, lat_deg=LAT, lon_deg=LON, tz_hr=TZ)
    assert len(df_h) == 8760
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res = run_decomposition(df_h, primary="DIRINT")
    assert res["DNI_dirint"].notna().sum() > 1000
    ld_leap = load_file(write_epw(base_lines(year_of_month=lambda m: 2000, leap=True), "bisiesto.epw"))
    assert ld_leap.epw_meta["n_rows"] == 8784 and not any("registros (se esperaban" in w for w in ld_leap.warnings)
    print("[OK] TMY con años distintos (aviso, 8,760 h, DIRINT por tramos) y año bisiesto (8,784 registros)")


def test_fail_loudly():
    good = base_lines()
    raises(["a,b,c", "1,2,3"], "no es un EPW válido")
    raises(["NOTLOCATION,x"] + good[1:], "LOCATION válido")
    raises([good[0].replace(f"{LAT:.2f}", "abc")] + good[1:], "no numéricos en LOCATION")
    raises([good[0].replace(f"{LAT:.2f}", "-95.00")] + good[1:], "fuera de rango")
    raises(good[:7] + ["DATA PERIODS,1,2,Data,Sunday, 1/ 1,12/31"] + good[8:], "2 registros por hora")
    raises(good[:7] + ["DATA PERIODS,1"] + good[8:], "sin número de registros por hora")
    raises(good[:8], "no tiene registros de datos")
    short = list(good)
    short[8 + 5] = ",".join(short[8 + 5].split(",")[:20])
    raises(short, "menos de 29 campos")
    bad = list(good)
    f = bad[8 + 7].split(","); f[13] = "xyz"; bad[8 + 7] = ",".join(f)
    raises(bad, "no numéricos")
    bad = list(good)
    f = bad[8 + 7].split(","); f[3] = "25"; bad[8 + 7] = ",".join(f)
    raises(bad, "entre 1 y 24")
    bad = list(good)
    f = bad[8 + 7].split(","); f[1] = "13"; bad[8 + 7] = ",".join(f)
    raises(bad, "fechas inválidas")
    bad = list(good)
    bad[8 + 100], bad[8 + 101] = bad[8 + 101], bad[8 + 100]
    raises(bad, "estrictamente creciente")
    nog = []
    for ln in good[8:]:
        f = ln.split(","); f[13] = "9999"; nog.append(",".join(f))
    raises(HEADER + nog, "ningún valor válido de irradiancia global")
    print("[OK] el lector falla con mensaje explícito ante 12 formas de EPW inválido")


if __name__ == "__main__":
    test_parse_basic()
    test_load_file_and_pipeline()
    test_buffer()
    test_tmy_and_leap()
    test_fail_loudly()
    print("[OK] Todas las pruebas del lector de EPW pasaron.")
