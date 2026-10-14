"""
test_reference_consistency.py — Métricas de consistencia con la referencia del archivo (reference.py).

Uso: python test_reference_consistency.py
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd

from reference import consistency_table, hourly_reference


def make_df(n=200, seed=1):
    rng = np.random.default_rng(seed)
    cosz = np.linspace(0.0, 1.0, n)
    ghi = 800 * cosz
    base = rng.uniform(100, 700, n)
    d = pd.DataFrame({"GHI_h": ghi, "cos_Z": cosz})
    for v in ("DNI", "DHI"):
        for tag in ("dirint", "erbs", "reindl2"):
            d[f"{v}_{tag}"] = base
    return d, base


def test_metrics_and_domain():
    d, base = make_df()
    ref = base - 10.0                         # el modelo está 10 W/m² por encima
    t = consistency_table(d, ref, None)
    assert list(t["Variable"].unique()) == ["DNI"] and list(t["Modelo"]) == ["DIRINT", "Erbs", "Reindl-2"]
    dom = (d["GHI_h"] >= 10) & (d["cos_Z"] >= 0.2)
    r = t.iloc[0]
    assert r["n"] == int(dom.sum()), "solo cuentan las horas con GHI >= 10 y cos θz >= 0.20"
    assert np.isclose(r["RMSE"], 10.0) and np.isclose(r["MBE"], 10.0)
    assert np.isclose(r["nRMSE_pct"], 10.0 / ref[dom.to_numpy()].mean() * 100.0)
    o, p = ref[dom.to_numpy()], base[dom.to_numpy()]
    assert np.isclose(r["R2"], 1 - ((p - o) ** 2).sum() / ((o - o.mean()) ** 2).sum())
    perfect = consistency_table(d, base, base)
    assert len(perfect) == 6 and np.allclose(perfect["RMSE"], 0) and np.allclose(perfect["R2"], 1)
    print("[OK] RMSE, MBE (modelo − referencia), nRMSE y R² contra el cálculo directo; dominio GHI >= 10 y cos θz >= 0.20")


def test_missing_and_errors():
    d, base = make_df()
    ref = base.copy()
    ref[::2] = np.nan                         # la mitad de la referencia falta: n se reduce, no se inventa nada
    t = consistency_table(d, ref, None)
    dom = ((d["GHI_h"] >= 10) & (d["cos_Z"] >= 0.2)).to_numpy() & np.isfinite(ref)
    assert t.iloc[0]["n"] == int(dom.sum())
    empty = consistency_table(d, np.full(len(d), np.nan), None)
    assert (empty["n"] == 0).all() and empty["RMSE"].isna().all()
    for bad, frag in ((lambda: consistency_table(d, base[:-1], None), "valores"),
                      (lambda: consistency_table(d.drop(columns=["cos_Z"]), base, None), "cos_Z"),
                      (lambda: consistency_table(d.drop(columns=["DNI_erbs"]), base, None), "DNI_erbs")):
        try:
            bad()
        except ValueError as e:
            assert frag in str(e), str(e)
        else:
            raise AssertionError("debía fallar con " + frag)
    print("[OK] referencia con huecos (n menor, sin inventar), referencia vacía (n = 0) y fallas explícitas")


def test_hourly_reference():
    ts = pd.date_range("2001-01-01 00:00", periods=4 * 6, freq="30min")        # datos de 30 min
    ld = SimpleNamespace(df=pd.DataFrame({"_timestamp": ts, "DNI": np.arange(len(ts), dtype=float)}), dni_col="DNI", dhi_col=None)
    hours = pd.Series(pd.date_range("2001-01-01 00:00", periods=6, freq="h"))
    dni, dhi = hourly_reference(ld, hours)
    assert dhi is None and np.allclose(dni, [0.5, 2.5, 4.5, 6.5, 8.5, 10.5]), dni
    print("[OK] referencia horaria = media de las muestras de cada hora; None si el archivo no trae esa columna")


if __name__ == "__main__":
    test_metrics_and_domain()
    test_missing_and_errors()
    test_hourly_reference()
    print("[OK] Todas las pruebas de la consistencia con la referencia pasaron.")
