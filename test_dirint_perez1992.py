"""
test_dirint_perez1992.py — Pruebas del DIRINT de Perez et al. (1992) vía pvlib y de la conservación del DIRINT de v1.0.0.
Usa datos sintéticos (Ineichen × nubosidad persistente); no necesita archivos externos.
"""
import math

import numpy as np
import pandas as pd
import pvlib

import decomposition as dec
from decomposition import dirint_series, dirint_series_v1, run_decomposition, _delta_ktp_bilateral

LAT, LON, ELEV, TZ = -31.65, -68.30, 700.0, -3


def make_hourly(days: int = 30, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t_start = pd.date_range("2021-03-01", periods=days * 24, freq="h")           # hora civil local, inicio de intervalo
    center = t_start + pd.Timedelta(minutes=30)
    utc = center - pd.Timedelta(hours=TZ)
    utc = utc.tz_localize("UTC")
    sp = pvlib.solarposition.get_solarposition(utc, LAT, LON, altitude=ELEV)
    zen = sp["zenith"].to_numpy()
    cosz = np.clip(np.cos(np.radians(zen)), 0, None)
    g0n = pvlib.irradiance.get_extra_radiation(utc).to_numpy()
    g0h = g0n * cosz
    cs = pvlib.location.Location(LAT, LON, altitude=ELEV).get_clearsky(utc, model="ineichen")["ghi"].to_numpy()
    blocks = np.repeat(rng.normal(0, 1.1, size=days * 3 + 1), 8)[: len(t_start)]
    kc = np.clip(1 / (1 + np.exp(-(0.9 + blocks))) * 1.03 + rng.normal(0, 0.03, len(t_start)), 0.1, 1.1)
    ghi = np.where(cosz > 0, cs * kc, 0.0)
    am = np.where(cosz > 0, pvlib.atmosphere.get_relative_airmass(np.minimum(zen, 89.9)), np.nan)
    kt = np.where(g0h > 0, ghi / np.where(g0h > 0, g0h, 1), np.nan)
    return pd.DataFrame({"timestamp_start": t_start, "timestamp_center": center, "GHI_h": ghi, "G0n": g0n, "G0h": g0h, "Kt": kt,
                         "AM": am, "zenith_deg": zen, "cos_Z": cosz, "temp_C": 18.0, "pressure_kPa": 93.0})


def test_matches_pvlib():
    df = make_hourly()
    out = dirint_series(df, min_cosz=0.065, max_zenith=87.0)
    t = pd.DatetimeIndex(df["timestamp_center"])
    ref = pvlib.irradiance.dirint(ghi=pd.Series(df["GHI_h"].to_numpy(), index=t), solar_zenith=pd.Series(df["zenith_deg"].to_numpy(), index=t),
                                  times=t, pressure=pd.Series(df["pressure_kPa"].to_numpy() * 1000, index=t), use_delta_kt_prime=True,
                                  min_cos_zenith=0.065, max_zenith=87.0).to_numpy()
    day = (df["G0h"].to_numpy() > 0) & (df["G0h"].to_numpy() / df["G0n"].to_numpy() >= 0.065) & np.isfinite(ref)
    assert day.sum() > 200
    assert np.array_equal(out["DNI_dirint"].to_numpy()[day], np.clip(ref[day], 0, dec.DNI_MAX_W_M2)), "DNI distinto de pvlib"
    assert np.isnan(out.loc[df["G0h"] <= 0, "DNI_dirint"]).all(), "las filas nocturnas deben ser NaN"
    print(f"[OK] DIRINT == pvlib.irradiance.dirint en {int(day.sum())} horas (igualdad exacta)")


def test_closure_and_flags():
    df = make_hourly()
    out = dirint_series(df)
    ok = out["DNI_dirint"].notna()
    recon = out.loc[ok, "DNI_dirint"] * (out.loc[ok, "G0h"] / out.loc[ok, "G0n"]) + out.loc[ok, "DHI_dirint"]
    clipped = (out.loc[ok, "GHI_h"] - out.loc[ok, "DNI_dirint"] * (out.loc[ok, "G0h"] / out.loc[ok, "G0n"])) < 0
    assert np.allclose(recon[~clipped], out.loc[ok, "GHI_h"][~clipped], atol=1e-9), "cierre GHI = DNI·cosZ + DHI no se cumple"
    assert (out.loc[ok, "DHI_dirint"] >= 0).all() and (out.loc[ok, "DNI_dirint"] <= dec.DNI_MAX_W_M2).all()
    assert set(out["flag_dirint"].unique()) <= {"DIRINT", "DIRINT_cloudenh", "DIRINT_unphysical", "invalid"}
    assert (out["dirint_version"] == "perez1992_pvlib").all()
    print("[OK] cierre, límites y flags")


def test_dew_point_and_w_roundtrip():
    df = make_hourly()
    td = np.full(len(df), 8.0)
    a = dirint_series(df, dew_point_C=td)
    w = np.exp(0.07 * td - 0.075)
    b = dirint_series(df, w_cm_series=pd.Series(w))
    assert np.allclose(a["DNI_dirint"], b["DNI_dirint"], equal_nan=True, atol=1e-9), "W <-> punto de rocío no es consistente"
    c = dirint_series(df)                                   # sin dato: bin de agua precipitable desconocida
    assert c["W_cm"].isna().all()
    assert not np.allclose(a["DNI_dirint"], c["DNI_dirint"], equal_nan=True), "el punto de rocío debería influir"
    print("[OK] punto de rocío / W consistentes; sin dato no se inventa W")


def test_delta_ktp_matches_pvlib_private():
    df = make_hourly()
    out = dirint_series(df)
    ktp = out["Ktp"].to_numpy()
    ref = pvlib.irradiance._delta_kt_prime_dirint(pd.Series(ktp), True, None).to_numpy()   # función privada de pvlib: solo para esta prueba
    assert np.allclose(out["delta_Ktp"].to_numpy(), ref, equal_nan=True, atol=1e-12)
    print("[OK] ΔKt' coincide con la de pvlib")


def _pvlib_dni(df):
    t = pd.DatetimeIndex(df["timestamp_center"])
    return pvlib.irradiance.dirint(ghi=pd.Series(df["GHI_h"].to_numpy(), index=t), solar_zenith=pd.Series(df["zenith_deg"].to_numpy(), index=t),
                                   times=t, pressure=pd.Series(df["pressure_kPa"].to_numpy() * 1000, index=t), use_delta_kt_prime=True,
                                   min_cos_zenith=0.065, max_zenith=87.0).to_numpy()


def test_segments_gap_and_tmy():
    import warnings
    df = make_hourly()
    # (a) horas faltantes en pleno día: la serie se parte en tramos y ΔKt' no cruza el hueco (cada tramo = llamada a pvlib por separado)
    gap = df.drop(index=range(300, 306)).reset_index(drop=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out = dirint_series(gap, min_cosz=0.065, max_zenith=87.0)
    assert any("tramos continuos" in str(x.message) for x in w), "debe avisar de los tramos"
    a, b = gap.iloc[:300], gap.iloc[300:]
    ref = np.concatenate([_pvlib_dni(a), _pvlib_dni(b)])
    day = (gap["G0h"].to_numpy() > 0) & (gap["G0h"].to_numpy() / gap["G0n"].to_numpy() >= 0.065) & np.isfinite(ref)
    assert np.array_equal(out["DNI_dirint"].to_numpy()[day], np.clip(ref[day], 0, dec.DNI_MAX_W_M2)), "con hueco: DNI distinto de pvlib por tramo"
    # (b) TMY: bloques de 10 días de «años» distintos pegados en medianoche; los saltos caen en horas nocturnas, así que el resultado diurno
    #     coincide con pasar la serie entera a pvlib por posición (como hace el benchmark)
    parts = []
    for k in range(3):
        blk = df.iloc[k * 240:(k + 1) * 240].copy()
        for c in ("timestamp_start", "timestamp_center"):
            blk[c] = blk[c] + pd.DateOffset(years=k * 2)
        parts.append(blk)
    tmy = pd.concat(parts, ignore_index=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out2 = dirint_series(tmy, min_cosz=0.065, max_zenith=87.0)
    assert any("3 tramos" in str(x.message) for x in w)
    ref2 = _pvlib_dni(tmy)
    day2 = (tmy["G0h"].to_numpy() > 0) & (tmy["G0h"].to_numpy() / tmy["G0n"].to_numpy() >= 0.065) & np.isfinite(ref2)
    assert day2.sum() > 150
    assert np.array_equal(out2["DNI_dirint"].to_numpy()[day2], np.clip(ref2[day2], 0, dec.DNI_MAX_W_M2)), "TMY: DNI diurno distinto de pvlib por posición"
    print(f"[OK] huecos y TMY: tramos continuos (sin error); con hueco = pvlib por tramo; TMY de 3 bloques = pvlib por posición ({int(day2.sum())} h diurnas)")


def test_fails_loudly():
    df = make_hourly()
    try:
        dirint_series(df.drop(columns=["pressure_kPa"]))
    except KeyError:
        pass
    else:
        raise AssertionError("sin presión debe fallar")
    print("[OK] falla explícita sin la columna de presión")


def test_legacy_kept():
    df = make_hourly()
    new = run_decomposition(df, primary="DIRINT")
    old = run_decomposition(df, primary="DIRINT", legacy_dirint=True)
    assert (new["dirint_version"] == "perez1992_pvlib").all() and "dirint_version" not in old.columns
    ref = dirint_series_v1(df)
    assert np.array_equal(old["DNI_dirint"].to_numpy(), ref["DNI_dirint"].to_numpy(), equal_nan=True)
    print("[OK] run_decomposition usa Perez por defecto y la tabla v1.0.0 con legacy_dirint=True")


def main():
    test_matches_pvlib()
    test_closure_and_flags()
    test_dew_point_and_w_roundtrip()
    test_delta_ktp_matches_pvlib_private()
    test_segments_gap_and_tmy()
    test_fails_loudly()
    test_legacy_kept()
    print("[OK] Todas las pruebas del DIRINT de Perez pasaron.")


if __name__ == "__main__":
    main()
