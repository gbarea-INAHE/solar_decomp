"""
test_dewpoint_humidity.py — Punto de rocío desde humedad relativa (Magnus) y su uso en el DIRINT de Perez 1992.
Verifica la fórmula contra tres referencias independientes (valores de tabla conocidos, pvlib.atmosphere.tdew_from_rh y una inversión numérica
de la fórmula de Buck), la detección de columnas, la agregación horaria y que el DIRINT con punto de rocío coincide con pvlib.
Usa datos sintéticos; no necesita archivos externos.
"""
import io

import numpy as np
import pandas as pd
import pvlib

import decomposition as dec
from decomposition import dirint_series
from io_handler import load_file
from preprocessor import aggregate_to_hourly
from solar_geometry import dew_point_from_rh
from test_dirint_perez1992 import LAT, LON, TZ, make_hourly


def _buck_es(t):
    """Presión de saturación sobre agua [hPa], Buck (1981/1996): 6.1121·exp((18.678 − T/234.5)·T/(257.14 + T)). Independiente de Magnus-OMM."""
    return 6.1121 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def _td_buck(t, rh):
    """Punto de rocío por bisección sobre la fórmula de Buck: es(Td) = rh/100 · es(T)."""
    target = rh / 100.0 * _buck_es(t)
    lo, hi = np.full_like(t, -80.0), np.full_like(t, 60.0)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        up = _buck_es(mid) > target
        hi, lo = np.where(up, mid, hi), np.where(up, lo, mid)
    return 0.5 * (lo + hi)


def test_known_values_and_properties():
    # valores de tablas psicrométricas (redondeados a 0.1 °C)
    for t, rh, exp in ((20.0, 50.0, 9.3), (25.0, 50.0, 13.9), (30.0, 60.0, 21.4)):
        got = float(dew_point_from_rh(t, rh))
        assert abs(got - exp) < 0.15, f"Td({t} °C, {rh} %) = {got:.2f}, esperado ≈ {exp}"
    tt = np.linspace(-40, 55, 20)
    assert np.allclose(dew_point_from_rh(tt, np.full_like(tt, 100.0)), tt, atol=1e-9), "con 100 % Td debe ser igual a T"
    for t in (-20.0, 0.0, 15.0, 35.0):
        td = dew_point_from_rh(np.full(50, t), np.linspace(2, 100, 50))
        assert np.all(np.diff(td) > 0) and np.all(td <= t + 1e-9), "Td debe crecer con la humedad y ser ≤ T"
    print("[OK] Magnus: valores de tabla, Td = T con 100 %, monótona y ≤ T")


def test_matches_pvlib_and_buck():
    rng = np.random.default_rng(11)
    t = rng.uniform(-30, 45, 4000)
    rh = rng.uniform(5, 100, 4000)
    ours = dew_point_from_rh(t, rh)
    if hasattr(pvlib.atmosphere, "tdew_from_rh"):
        ref = pvlib.atmosphere.tdew_from_rh(t, rh)
        assert np.allclose(ours, ref, atol=1e-9), "distinto de pvlib.atmosphere.tdew_from_rh"
        print(f"[OK] igual a pvlib.atmosphere.tdew_from_rh (máx |dif| = {np.max(np.abs(ours - ref)):.1e} °C)")
    else:
        print("[AVISO] esta versión de pvlib no tiene tdew_from_rh; se omite esa comparación")
    buck = _td_buck(t, rh)
    d = np.abs(ours - buck)
    assert d.max() < 0.25, f"Magnus vs Buck difieren hasta {d.max():.2f} °C"
    print(f"[OK] Magnus-OMM vs inversión numérica de Buck: máx |dif| = {d.max():.2f} °C, mediana {np.median(d):.3f} °C (−30…45 °C, 5…100 %)")


def test_invalid_inputs_are_nan():
    t = np.array([20.0, 20.0, 20.0, 20.0, np.nan, 20.0, -50.0, 65.0])
    rh = np.array([0.0, -5.0, 100.5, np.nan, 50.0, 100.0, 50.0, 50.0])
    out = dew_point_from_rh(t, rh)
    assert np.isnan(out[:5]).all() and np.isnan(out[6:]).all(), "humedad ∉ (0,100], temperatura fuera de −45…60 o NaN deben dar NaN (sin recortar)"
    assert out[5] == 20.0
    print("[OK] entradas inválidas → NaN (no se recorta ni se inventa)")


def _csv(df: pd.DataFrame) -> io.StringIO:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf


def test_column_detection():
    n = 6
    base = {"timestamp": pd.date_range("2021-03-01", periods=n, freq="h"), "GHI": np.linspace(0, 500, n)}
    cases = {
        "relative_humidity": ("Relative Humidity %", None), "rh": ("RH [%]", None), "humedad": ("Humedad relativa", None),
        "dew": (None, "Dew Point Temperature C"), "tdew": (None, "Tdew_C"), "roc": (None, "punto_de_rocio"),
    }
    for _, (hum, dew) in cases.items():
        d = pd.DataFrame(base)
        d["Dry Bulb Temperature C"] = 15.0
        if hum:
            d[hum] = 60.0
        if dew:
            d[dew] = 8.0
        ld = load_file(_csv(d))
        assert (ld.humidity_col == hum) and (ld.dewpoint_col == dew), f"detección: {hum=} {dew=} → {ld.humidity_col!r}, {ld.dewpoint_col!r}"
        assert ld.temp_col == "Dry Bulb Temperature C"
    d = pd.DataFrame(base)
    d["Dry Bulb Temperature C"] = 15.0
    ld = load_file(_csv(d))
    assert ld.humidity_col is None and ld.dewpoint_col is None
    print("[OK] detección de columnas de humedad y de punto de rocío (y de ausencia)")


def _minute_csv(days=3, rh_fun=None, add_dew=False, rh_scale=1.0):
    t = pd.date_range("2021-03-01", periods=days * 1440, freq="min")
    hh = t.hour + t.minute / 60.0
    ghi = np.clip(800 * np.sin(np.pi * (hh - 6.5) / 12.0), 0, None)
    temp = 18 + 8 * np.sin(2 * np.pi * (hh - 9) / 24.0)
    rh = np.clip(60 + 25 * np.cos(2 * np.pi * (hh - 4) / 24.0), 20, 99.0) * rh_scale
    d = pd.DataFrame({"timestamp": t, "GHI": ghi, "temp_C": temp, "RH": rh})
    if rh_fun is not None:
        d["RH"] = rh_fun(d["RH"].to_numpy())
    if add_dew:
        d["Tdew"] = 5.0
    return d


def test_hourly_aggregation_of_dew_point():
    d = _minute_csv()
    d.loc[100:130, "RH"] = np.nan                     # muestras sin humedad
    d.loc[2000:2010, "RH"] = 120.0                    # humedad imposible
    ld = load_file(_csv(d))
    h = aggregate_to_hourly(ld, LAT, LON, TZ, altitude_m=700.0)
    assert "dew_point_C" in h.columns
    row = dew_point_from_rh(d["temp_C"].to_numpy(), d["RH"].to_numpy())
    exp = pd.Series(row, index=pd.DatetimeIndex(d["timestamp"])).groupby(pd.DatetimeIndex(d["timestamp"]).floor("h")).mean()
    got = h.set_index("timestamp_start")["dew_point_C"]
    assert np.allclose(got.to_numpy(), exp.reindex(got.index).to_numpy(), equal_nan=True, atol=1e-12), "Td horaria ≠ media de Td por muestra"
    assert any("fuera de (0, 100]" in w for w in ld.warnings), "debe avisar de las muestras con humedad inválida"
    n_before = len(ld.warnings)
    aggregate_to_hourly(ld, LAT, LON, TZ, altitude_m=700.0)
    assert len(ld.warnings) == n_before, "el aviso no debe duplicarse al repetir el preprocesamiento"
    print("[OK] Td horaria = media de Td por muestra; muestras inválidas → NaN con aviso (sin duplicar)")


def test_humidity_as_fraction_is_refused_loudly():
    d = _minute_csv(rh_scale=0.01)                    # humedad en fracción 0–1
    ld = load_file(_csv(d))
    h = aggregate_to_hourly(ld, LAT, LON, TZ, altitude_m=700.0)
    assert "dew_point_C" not in h.columns, "con humedad en fracción NO debe calcularse el punto de rocío"
    assert any("entre 0 y 1" in w for w in ld.warnings), "debe avisar que la humedad parece fracción"
    print("[OK] humedad en fracción (0–1): no se usa y se avisa")


def test_dew_point_column_has_priority_and_humidity_without_temperature():
    d = _minute_csv(add_dew=True)
    h = aggregate_to_hourly(load_file(_csv(d)), LAT, LON, TZ, altitude_m=700.0)
    assert np.allclose(h["dew_point_C"].dropna(), 5.0), "la columna de punto de rocío tiene prioridad sobre la humedad"
    d2 = _minute_csv().drop(columns=["temp_C"])
    ld = load_file(_csv(d2))
    h2 = aggregate_to_hourly(ld, LAT, LON, TZ, altitude_m=700.0)
    assert "dew_point_C" not in h2.columns and any("no hay columna de temperatura" in w for w in ld.warnings)
    print("[OK] el punto de rocío del archivo tiene prioridad; humedad sin temperatura → aviso y sin Td")


def test_dirint_with_dew_point_matches_pvlib_and_falls_back_per_hour():
    df = make_hourly()
    n = len(df)
    td = np.full(n, 7.0) + 4.0 * np.sin(np.arange(n) / 20.0)
    td_nan = td.copy()
    td_nan[200:260] = np.nan
    t = pd.DatetimeIndex(df["timestamp_center"])
    kw = dict(ghi=pd.Series(df["GHI_h"].to_numpy(), index=t), solar_zenith=pd.Series(df["zenith_deg"].to_numpy(), index=t), times=t,
              pressure=pd.Series(df["pressure_kPa"].to_numpy() * 1000, index=t), use_delta_kt_prime=True, min_cos_zenith=0.065, max_zenith=87.0)
    ref_known = pvlib.irradiance.dirint(temp_dew=pd.Series(td, index=t), **kw).to_numpy()
    ref_unknown = pvlib.irradiance.dirint(**kw).to_numpy()
    day = (df["G0h"].to_numpy() > 0) & (df["G0h"].to_numpy() / df["G0n"].to_numpy() >= 0.065)
    a = dirint_series(df.assign(dew_point_C=td), min_cosz=0.065, max_zenith=87.0)
    ok = day & np.isfinite(ref_known)
    assert np.array_equal(a["DNI_dirint"].to_numpy()[ok], np.clip(ref_known[ok], 0, dec.DNI_MAX_W_M2)), "con Td ≠ pvlib con temp_dew"
    assert not np.array_equal(ref_known[ok], ref_unknown[ok]), "el punto de rocío debe cambiar el resultado respecto de «W desconocida»"
    b = dirint_series(df.assign(dew_point_C=td_nan), min_cosz=0.065, max_zenith=87.0)
    sel = np.zeros(n, bool)
    sel[200:260] = True
    ok_nan = sel & day & np.isfinite(ref_unknown)
    assert ok_nan.sum() > 5
    assert np.array_equal(b["DNI_dirint"].to_numpy()[ok_nan], np.clip(ref_unknown[ok_nan], 0, dec.DNI_MAX_W_M2)), "horas con Td NaN deben usar el bin «desconocido»"
    keep = ~sel & day & np.isfinite(ref_known)
    assert np.array_equal(b["DNI_dirint"].to_numpy()[keep], np.clip(ref_known[keep], 0, dec.DNI_MAX_W_M2))
    assert np.isnan(b.loc[sel, "W_cm"]).all() and np.isfinite(b.loc[~sel & day, "W_cm"]).all()
    print(f"[OK] DIRINT con Td = pvlib con temp_dew ({int(ok.sum())} h); horas con Td NaN usan el bin desconocido ({int(ok_nan.sum())} h)")


def test_pipeline_dew_point_is_opt_in_and_legacy_ignores_it():
    d = _minute_csv()
    ld = load_file(_csv(d))
    h = aggregate_to_hourly(ld, LAT, LON, TZ, altitude_m=700.0)
    no_col = dec.run_decomposition(h.drop(columns=["dew_point_C"]))
    default = dec.run_decomposition(h)
    assert "dew_point_C" in default.columns, "la columna dew_point_C se conserva en la salida como dato"
    assert np.array_equal(default["DNI_dirint"].to_numpy(), no_col["DNI_dirint"].to_numpy(), equal_nan=True), "por defecto el DIRINT NO debe usar el punto de rocío"
    assert (default["dirint_W_source"] == "unknown_bin").all()
    opt = dec.run_decomposition(h, use_dew_point=True)
    assert not np.allclose(opt["DNI_dirint"].to_numpy(), no_col["DNI_dirint"].to_numpy(), equal_nan=True), "con use_dew_point=True el punto de rocío debe llegar al DIRINT"
    assert (opt["dirint_W_source"] == "dew_point").any()
    for kwargs, frame in (({"use_dew_point": True}, h.drop(columns=["dew_point_C"])), ({"use_dew_point": True, "legacy_dirint": True}, h)):
        try:
            dec.run_decomposition(frame, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debía fallar con ValueError: {kwargs}")
    old = dec.run_decomposition(h, legacy_dirint=True)
    old_no_td = dec.run_decomposition(h.drop(columns=["dew_point_C"]), legacy_dirint=True)
    assert np.array_equal(old["DNI_dirint"].to_numpy(), old_no_td["DNI_dirint"].to_numpy(), equal_nan=True), "el legacy v1.0.0 no debe cambiar con el punto de rocío"
    print("[OK] punto de rocío en el DIRINT: apagado por defecto, opt-in con use_dew_point=True, falla fuerte sin dato; el legacy no cambia")


if __name__ == "__main__":
    test_known_values_and_properties()
    test_matches_pvlib_and_buck()
    test_invalid_inputs_are_nan()
    test_column_detection()
    test_hourly_aggregation_of_dew_point()
    test_humidity_as_fraction_is_refused_loudly()
    test_dew_point_column_has_priority_and_humidity_without_temperature()
    test_dirint_with_dew_point_matches_pvlib_and_falls_back_per_hour()
    test_pipeline_dew_point_is_opt_in_and_legacy_ignores_it()
    print("[OK] Todas las pruebas de punto de rocío pasaron.")
