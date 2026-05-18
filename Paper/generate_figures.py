"""
generate_figures.py — Figuras para el paper científico (v2).

Figuras generadas en Paper/figuras/:
  Fig1  Mapa Argentina: mejor modelo DNI (forma=modelo, color=R²)
  Fig2  Scatter DNI obs vs pred — 3 modelos
  Fig3  Scatter DHI obs vs pred — 3 modelos
  Fig4  Heatmap R² DNI ciudad × modelo
  Fig5  nRMSE DNI barras por ciudad
  Fig6  MBE DNI boxplot por modelo
  Fig7  Taylor Diagram DNI
  Fig8  Heatmap MBE mensual (mejor modelo, ciudad × mes)
  Fig9  R² vs Kt medio por ciudad (desempeño vs aridez)
  Fig10 Boxplot nRMSE DNI por zona Köppen
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT  = Path(__file__).resolve().parent
OUT   = ROOT / "figuras"
OUT.mkdir(exist_ok=True)
DATA_XLS = ROOT / "resultados_validacion" / "validacion_ciudades.xlsx"
EPW_DIR  = ROOT.parent / "EPWs"
sys.path.insert(0, str(ROOT.parent))
from epw_parser import parse_epw
from solar_geometry import compute_geometry_df
from decomposition import run_decomposition

# ── Paleta ────────────────────────────────────────────────────────────────────
COLORS  = {"DIRINT": "#e15759", "Erbs": "#4e79a7", "Reindl2": "#59a14f"}
MARKERS = {"DIRINT": "^",       "Erbs": "s",        "Reindl2": "o"}
MLABEL  = {"DIRINT": "DIRINT",  "Erbs": "Erbs",     "Reindl2": "Reindl-2"}
PLT_KW  = {"dpi": 150, "bbox_inches": "tight"}
MIN_GHI = 10.0;  MIN_COSZ = 0.0174

# ── Zonas climáticas ──────────────────────────────────────────────────────────
# Clasificación Köppen-Geiger y IRAM 11603 (zona térmica argentina)
CLIMATE = {
    # ciudad (tal como aparece en EPW meta)          Köppen   IRAM
    "AEROPARQUE-BS-AS":         ("Cfa",  "III"),
    "ANDALGALÁ":                ("BWk",  "IV"),
    "BARILOCHE-AERO":           ("Cfb",  "V"),
    "CATAMARCA-AERO":           ("BWk",  "III"),
    "COMODORO-RIVADAVIA":       ("BSk",  "V"),
    "CONCORDIA-AERO":           ("Cfa",  "II"),
    "CORDOBA-AERO":             ("BSk",  "III"),
    "CORRIENTES-AERO":          ("Cfa",  "I"),
    "ESQUEL-AERO":              ("BSk",  "V"),
    "FORMOSA-AERO":             ("Aw",   "I"),
    "GENERAL PICO AIRP.":       ("BSk",  "III"),
    "GUALEGUAYCHU-AERO":        ("Cfa",  "II"),
    "IGUAZU-AERO":              ("Cfa",  "I"),
    "JUJUY-AERO":               ("BSh",  "II"),
    "JUNIN-AERO":               ("BSk",  "III"),
    "LA-RIOJA-AERO":            ("BWh",  "III"),
    "MALARGUE-AERO":            ("BWk",  "IV"),
    "MENDOZA-AERO":             ("BWk",  "III"),
    "NEUQUEN-AERO":             ("BSk",  "IV"),
    "PARANA-AERO":              ("Cfa",  "II"),
    "PASO-DE-LOS-LIBRES":       ("Cfa",  "I"),
    "POSADAS-AERO":             ("Cfa",  "I"),
    "PRESIDENCIA-ROQUE-S":      ("Cfa",  "II"),
    "RECONQUISTA-AERO":         ("Cfa",  "II"),
    "RESISTENCIA-AERO":         ("Cfa",  "I"),
    "RIO-GALLEGOS-AERO":        ("BSk",  "VI"),
    "ROSARIO-AERO":             ("Cfa",  "III"),
    "SALTA-AERO":               ("BSh",  "II"),
    "SAN-JUAN-AERO":            ("BWk",  "III"),
    "SAN-LUIS-AERO":            ("BSk",  "III"),
    "SAN-RAFAEL-AERO":          ("BWk",  "IV"),
    "SANTA-ROSA-AERO":          ("BSk",  "IV"),
    "SANTIAGO-DEL-ESTERO":      ("BSk",  "II"),
    "SAUCE-VIEJO-AERO":         ("Cfa",  "III"),
    "TARTAGAL-AERO":            ("Aw",   "I"),
    "TRELEW-AERO":              ("BWk",  "V"),
    "TUCUMAN-AERO":             ("Cfa",  "II"),
    "USHUAIA-AERO":             ("ET",   "VI"),
    "VIEDMA-AERO":              ("BSk",  "IV"),
    "VILLA-DOLORES-AERO":       ("BSk",  "III"),
    "VILLA-REYNOLDS-AERO":      ("BSk",  "III"),
}

KOPPEN_COLORS = {
    "Aw": "#e74c3c",   # tropical savanna
    "BSh": "#e67e22",  # hot steppe
    "BSk": "#f39c12",  # cold steppe
    "BWh": "#c0392b",  # hot desert
    "BWk": "#d35400",  # cold desert
    "Cfa": "#27ae60",  # humid subtropical
    "Cfb": "#1abc9c",  # oceanic
    "ET":  "#2980b9",  # tundra
}

IRAM_COLORS = {"I": "#e74c3c", "II": "#e67e22", "III": "#f1c40f",
               "IV": "#27ae60", "V": "#2980b9", "VI": "#8e44ad"}


def _city_key(city: str) -> str:
    return city.upper().strip()


def _get_climate(city: str) -> tuple[str, str]:
    key = _city_key(city)
    # búsqueda exacta o por prefijo
    if key in CLIMATE:
        return CLIMATE[key]
    for k, v in CLIMATE.items():
        if key.startswith(k[:8]):
            return v
    return ("?", "?")


def metrics(obs, pred):
    mask = np.isfinite(obs) & np.isfinite(pred)
    o, p = obs[mask], pred[mask]
    if len(o) < 10:
        return dict(n=len(o), RMSE=np.nan, MBE=np.nan, R2=np.nan, nRMSE=np.nan,
                    std_obs=np.nan, std_pred=np.nan, R=np.nan)
    err  = p - o
    rmse = float(np.sqrt(np.mean(err**2)))
    mbe  = float(np.mean(err))
    ss   = np.sum((o - o.mean())**2)
    r2   = float(1 - np.sum(err**2)/ss) if ss > 0 else np.nan
    nrmse = rmse / o.mean() * 100 if o.mean() > 0 else np.nan
    R    = float(np.corrcoef(o, p)[0, 1])
    return dict(n=len(o), RMSE=round(rmse,1), MBE=round(mbe,1),
                R2=round(r2,4), nRMSE=round(nrmse,1),
                std_obs=float(o.std()), std_pred=float(p.std()), R=R)


def load_all_epw_data() -> pd.DataFrame:
    all_rows = []
    seen = set()
    for epw_path in sorted(EPW_DIR.glob("*.EPW")) + sorted(EPW_DIR.glob("*.epw")):
        meta, df_raw = parse_epw(epw_path)
        city = meta["city"]
        if city in seen:
            continue
        seen.add(city)
        df_day = df_raw[df_raw["GHI"] >= MIN_GHI].copy().reset_index(drop=True)
        if len(df_day) < 100:
            continue
        df_h = pd.DataFrame({
            "timestamp_start":  df_day["timestamp"],
            "timestamp_center": df_day["timestamp"] + pd.Timedelta(minutes=30),
            "GHI_h":    df_day["GHI"],  "coverage": 1.0,
            "temp_C":   df_day["temp_C"], "pressure_kPa": df_day["pressure_kPa"],
        })
        geo = compute_geometry_df(df_h, meta["lat"], meta["lon"], meta["tz"])
        for k, v in geo.items():
            df_h[k] = v
        g0h = geo["G0h"]
        df_h["Kt"] = np.where(g0h > 0, df_day["GHI"].values / g0h, np.nan)
        try:
            df_dec = run_decomposition(df_h, primary="DIRINT", min_cosz=MIN_COSZ)
        except Exception:
            continue
        df_dec["DNI_ref"] = df_day["DNI_ref"].values
        df_dec["DHI_ref"] = df_day["DHI_ref"].values
        df_dec["city"] = city;  df_dec["lat"] = meta["lat"];  df_dec["lon"] = meta["lon"]
        df_dec["Kt_val"] = df_h["Kt"].values
        koppen, iram = _get_climate(city)
        df_dec["koppen"] = koppen;  df_dec["iram"] = iram
        all_rows.append(df_dec)
    return pd.concat(all_rows, ignore_index=True)


# ══ Fig 1 — Mapa (forma=modelo, color=R²) ════════════════════════════════════
def fig1_mapa(df_best):
    fig, ax = plt.subplots(figsize=(6, 9))
    ax.set_facecolor("#e8f4f8"); fig.patch.set_facecolor("white")
    ax.set_xlim(-74, -52); ax.set_ylim(-56, -21)
    ax.set_xlabel("Longitud (°)", fontsize=9); ax.set_ylabel("Latitud (°)", fontsize=9)
    ax.set_title("Mejor modelo de descomposición DNI\npor ciudad — Argentina",
                 fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3, linewidth=0.5)

    norm = Normalize(vmin=0.85, vmax=0.97)
    cmap = cm.RdYlGn

    for model in ["Reindl2", "Erbs", "DIRINT"]:
        sub = df_best[df_best["Mejor_modelo_DNI"] == model]
        if sub.empty:
            continue
        colors = [cmap(norm(v)) for v in sub["DNI_R2"]]
        ax.scatter(sub["Lon"], sub["Lat"], c=colors, marker=MARKERS[model],
                   s=80, zorder=5, edgecolors="k", linewidths=0.5,
                   label=f"{MLABEL[model]} (n={len(sub)})")
        for _, row in sub.iterrows():
            ax.annotate(row["Ciudad"].split("-")[0].title(),
                        (row["Lon"], row["Lat"]),
                        fontsize=5.5, xytext=(3, 3), textcoords="offset points", color="#333")

    sm = ScalarMappable(cmap=cmap, norm=norm); sm.set_array([])
    fig.colorbar(sm, ax=ax, shrink=0.4, pad=0.02).set_label("R² DNI", fontsize=8)
    ax.legend(fontsize=8, loc="lower left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUT / "Fig1_mapa_mejor_modelo.png", **PLT_KW); plt.close(fig)
    print("  Fig1 OK")


# ══ Fig 2 & 3 — Scatter hexbin ════════════════════════════════════════════════
def fig_scatter(df_all, var, ref_col, fname, title):
    models = [("DIRINT",  f"DNI_dirint"  if var=="DNI" else "DHI_dirint"),
              ("Erbs",    f"DNI_erbs"    if var=="DNI" else "DHI_erbs"),
              ("Reindl2", f"DNI_reindl2" if var=="DNI" else "DHI_reindl2")]
    lim = (0, 1050) if var == "DNI" else (0, 550)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True, sharex=True)
    for ax, (model, pred_col) in zip(axes, models):
        obs  = df_all[ref_col].values
        pred = df_all[pred_col].values if pred_col in df_all.columns else np.full(len(obs), np.nan)
        mask = np.isfinite(obs) & np.isfinite(pred) & (obs > 0)
        o, p = obs[mask], pred[mask]
        hb = ax.hexbin(o, p, gridsize=60, cmap="Blues", mincnt=1, extent=(*lim, *lim))
        ax.plot(lim, lim, "k--", lw=0.8, alpha=0.6)
        m = metrics(o, p)
        ax.set_title(f"{MLABEL[model]}\nR²={m['R2']:.3f}  RMSE={m['RMSE']:.0f} W/m²  MBE={m['MBE']:+.0f}",
                     fontsize=9)
        ax.set_xlabel(f"{var} referencia EPW (W/m²)", fontsize=8)
        if ax is axes[0]:
            ax.set_ylabel(f"{var} calculado (W/m²)", fontsize=8)
        ax.set_xlim(lim); ax.set_ylim(lim); ax.tick_params(labelsize=7)
        plt.colorbar(hb, ax=ax).set_label("N horas", fontsize=7)

    fig.suptitle(title, fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(OUT / fname, **PLT_KW); plt.close(fig)
    print(f"  {fname} OK")


# ══ Fig 4 — Heatmap R² DNI ════════════════════════════════════════════════════
def fig4_heatmap(df_cities):
    pivot = df_cities.pivot_table(index="Ciudad", columns="Modelo", values="DNI_R2", aggfunc="mean")
    pivot = pivot.sort_values("Reindl2", ascending=True)
    pivot = pivot[[m for m in ["DIRINT","Erbs","Reindl2"] if m in pivot.columns]]
    fig, ax = plt.subplots(figsize=(7, 11))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0.75, vmax=0.97)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([MLABEL.get(c,c) for c in pivot.columns], fontsize=10)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([c.replace("-AERO","").replace("-"," ").title() for c in pivot.index], fontsize=7)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i,j]
            if np.isfinite(val):
                ax.text(j, i, f"{val:.3f}", ha="center", va="center",
                        fontsize=6, color="black" if val > 0.82 else "white")
    plt.colorbar(im, ax=ax, shrink=0.5).set_label("R² DNI", fontsize=9)
    ax.set_title("R² DNI por ciudad y modelo\n(ordenado por Reindl-2)", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig4_heatmap_R2_DNI.png", **PLT_KW); plt.close(fig)
    print("  Fig4 OK")


# ══ Fig 5 — nRMSE barras ══════════════════════════════════════════════════════
def fig5_nrmse(df_cities):
    pivot = df_cities.pivot_table(index="Ciudad", columns="Modelo", values="DNI_nRMSE", aggfunc="mean")
    pivot = pivot.sort_values("Reindl2", ascending=False)
    pivot = pivot[[m for m in ["DIRINT","Erbs","Reindl2"] if m in pivot.columns]]
    n = len(pivot); x = np.arange(n); w = 0.25
    fig, ax = plt.subplots(figsize=(14, 5))
    for i, model in enumerate(pivot.columns):
        ax.bar(x + i*w, pivot[model], w, label=MLABEL[model],
               color=COLORS[model], edgecolor="white", linewidth=0.3)
    ax.set_xticks(x + w)
    ax.set_xticklabels([c.replace("-AERO","").replace("-"," ").title() for c in pivot.index],
                       rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("nRMSE DNI (%)"); ax.legend(fontsize=9); ax.grid(axis="y", alpha=0.3)
    ax.set_title("Error relativo DNI (nRMSE) por ciudad y modelo", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig5_nRMSE_por_ciudad.png", **PLT_KW); plt.close(fig)
    print("  Fig5 OK")


# ══ Fig 6 — MBE boxplot ═══════════════════════════════════════════════════════
def fig6_mbe(df_cities):
    models = ["DIRINT","Erbs","Reindl2"]
    data = [df_cities[df_cities["Modelo"]==m]["DNI_MBE"].dropna().values for m in models]
    fig, ax = plt.subplots(figsize=(6,5))
    bp = ax.boxplot(data, patch_artist=True, widths=0.5, medianprops=dict(color="black", lw=2))
    for patch, model in zip(bp["boxes"], models):
        patch.set_facecolor(COLORS[model]); patch.set_alpha(0.8)
    ax.axhline(0, color="k", lw=0.8, ls="--")
    ax.set_xticks([1,2,3]); ax.set_xticklabels([MLABEL[m] for m in models], fontsize=10)
    ax.set_ylabel("MBE DNI (W/m²)"); ax.grid(axis="y", alpha=0.3)
    ax.set_title("Sesgo (MBE) DNI por modelo\n(distribución sobre 41 ciudades)", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig6_MBE_boxplot.png", **PLT_KW); plt.close(fig)
    print("  Fig6 OK")


# ══ Fig 7 — Taylor Diagram ════════════════════════════════════════════════════
def fig7_taylor(df_all):
    """Taylor diagram DNI: cada punto = 1 ciudad × modelo."""
    fig = plt.figure(figsize=(8, 7))
    ax  = fig.add_subplot(111, projection="polar")
    ax.set_thetamin(0); ax.set_thetamax(90)

    ref_std = df_all["DNI_ref"].std()

    for model, pred_col in [("DIRINT","DNI_dirint"),("Erbs","DNI_erbs"),("Reindl2","DNI_reindl2")]:
        if pred_col not in df_all.columns:
            continue
        cities = df_all["city"].unique()
        thetas, rs = [], []
        for city in cities:
            sub = df_all[df_all["city"] == city]
            obs  = sub["DNI_ref"].values
            pred = sub[pred_col].values
            mask = np.isfinite(obs) & np.isfinite(pred)
            o, p = obs[mask], pred[mask]
            if len(o) < 50:
                continue
            R    = np.corrcoef(o, p)[0,1]
            sd_p = p.std()
            thetas.append(np.arccos(np.clip(R, -1, 1)))
            rs.append(sd_p / ref_std)
        ax.scatter(thetas, rs, c=COLORS[model], marker=MARKERS[model],
                   s=35, alpha=0.8, zorder=4, label=MLABEL[model])

    # Referencia (obs): R=1, std=1
    ax.scatter([0], [1.0], c="black", s=80, zorder=5, marker="*", label="Referencia EPW")

    # Arcos de RMSE normalizado
    for rmse_n in [0.2, 0.4, 0.6]:
        theta_arr = np.linspace(0, np.pi/2, 100)
        r_arr = np.sqrt(1 + rmse_n**2 - 2*rmse_n*np.cos(theta_arr - 0))
        # circulo centrado en (0,1) en coord polares — aprox. como contorno
        angles = np.linspace(0, np.pi/2, 200)
        rs_c   = []
        for a in angles:
            # resolver r^2 - 2r*cos(a) + 1 = rmse_n^2
            disc = 1 - (1 - rmse_n**2)
            if disc < 0: continue
            r_sol = np.cos(a) + np.sqrt(rmse_n**2 - np.sin(a)**2) if rmse_n**2 >= np.sin(a)**2 else None
            if r_sol and r_sol > 0:
                rs_c.append((a, r_sol))
        if rs_c:
            aa, rr = zip(*rs_c)
            ax.plot(aa, rr, "k--", lw=0.5, alpha=0.4)
            ax.text(aa[-1], rr[-1], f"RMSE={rmse_n:.1f}", fontsize=6, color="gray")

    ax.set_rmax(1.6)
    ax.set_rticks([0.5, 1.0, 1.5])
    ax.set_rlabel_position(80)
    ax.set_title("Taylor Diagram — DNI\n(std normalizada por desv. obs.)", fontsize=11, fontweight="bold", pad=20)

    # Etiquetas angulares = correlación
    for R_val in [0.9, 0.95, 0.99, 1.0]:
        angle = np.arccos(R_val)
        ax.text(angle, 1.55, f"R={R_val}", fontsize=7, ha="center", color="#333")

    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "Fig7_Taylor_DNI.png", **PLT_KW); plt.close(fig)
    print("  Fig7 OK")


# ══ Fig 8 — Heatmap MBE mensual ═══════════════════════════════════════════════
def fig8_mbe_mensual(df_monthly, df_best):
    """MBE mensual del mejor modelo por ciudad."""
    best_map = df_best.set_index("Ciudad")["Mejor_modelo_DNI"].to_dict()
    rows = []
    for _, row in df_monthly.iterrows():
        city  = row["Ciudad"]
        model = best_map.get(city)
        if row["Modelo"] == model:
            rows.append({"Ciudad": city, "Mes": row["Mes"], "MBE": row["DNI_MBE"]})
    df_m = pd.DataFrame(rows)
    if df_m.empty:
        return
    pivot = df_m.pivot_table(index="Ciudad", columns="Mes", values="MBE", aggfunc="mean")
    # ordenar por latitud (norte→sur)
    lat_map = df_best.set_index("Ciudad")["Lat"].to_dict()
    pivot["_lat"] = pivot.index.map(lambda c: lat_map.get(c, 0))
    pivot = pivot.sort_values("_lat", ascending=False).drop(columns="_lat")
    pivot.columns = [f"M{c}" if isinstance(c, int) else c for c in pivot.columns]

    fig, ax = plt.subplots(figsize=(12, 11))
    vmax = max(abs(pivot.values[np.isfinite(pivot.values)]).max(), 1)
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdBu_r",
                   vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Ene","Feb","Mar","Abr","May","Jun",
                         "Jul","Ago","Sep","Oct","Nov","Dic"], fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([c.replace("-AERO","").replace("-"," ").title() for c in pivot.index], fontsize=7)
    for i in range(len(pivot.index)):
        for j in range(12):
            val = pivot.values[i, j]
            if np.isfinite(val):
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=5.5,
                        color="black" if abs(val) < vmax*0.6 else "white")
    cb = fig.colorbar(im, ax=ax, shrink=0.5)
    cb.set_label("MBE DNI (W/m²) — mejor modelo por ciudad", fontsize=8)
    ax.set_title("Sesgo mensual DNI — mejor modelo por ciudad\n(orden Norte→Sur)", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig8_MBE_mensual.png", **PLT_KW); plt.close(fig)
    print("  Fig8 OK")


# ══ Fig 9 — R² vs Kt medio ════════════════════════════════════════════════════
def fig9_r2_vs_kt(df_all, df_cities):
    kt_mean = (df_all[df_all["Kt_val"].notna()]
               .groupby("city")["Kt_val"].mean().rename("Kt_mean"))
    df_r = df_cities[df_cities["Modelo"]=="Reindl2"].copy()
    df_r = df_r.join(kt_mean, on="Ciudad")
    df_r.dropna(subset=["Kt_mean","DNI_R2"], inplace=True)
    df_r["koppen"] = df_r["Ciudad"].apply(lambda c: _get_climate(c)[0])

    fig, ax = plt.subplots(figsize=(8, 5))
    for kp, grp in df_r.groupby("koppen"):
        color = KOPPEN_COLORS.get(kp, "gray")
        ax.scatter(grp["Kt_mean"], grp["DNI_R2"], c=color, s=60,
                   label=kp, edgecolors="k", linewidths=0.4, zorder=4)
        for _, row in grp.iterrows():
            ax.annotate(row["Ciudad"].split("-")[0].title(),
                        (row["Kt_mean"], row["DNI_R2"]),
                        fontsize=5.5, xytext=(3,2), textcoords="offset points", color="#444")

    # Línea de tendencia
    x, y = df_r["Kt_mean"].values, df_r["DNI_R2"].values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() > 3:
        z = np.polyfit(x[mask], y[mask], 1)
        xp = np.linspace(x[mask].min(), x[mask].max(), 50)
        ax.plot(xp, np.polyval(z, xp), "k--", lw=1, alpha=0.6, label=f"Tendencia (m={z[0]:+.2f})")

    ax.set_xlabel("Kt medio anual (índice de claridad)", fontsize=9)
    ax.set_ylabel("R² DNI — Reindl-2", fontsize=9)
    ax.set_title("Desempeño del modelo vs. aridez del clima\n(Reindl-2, 41 ciudades)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7, ncol=2); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "Fig9_R2_vs_Kt.png", **PLT_KW); plt.close(fig)
    print("  Fig9 OK")


# ══ Fig 10 — Boxplot nRMSE por zona Köppen ════════════════════════════════════
def fig10_boxplot_koppen(df_cities):
    df_r2 = df_cities[df_cities["Modelo"]=="Reindl2"].copy()
    df_r2["koppen"] = df_r2["Ciudad"].apply(lambda c: _get_climate(c)[0])
    df_erbs = df_cities[df_cities["Modelo"]=="Erbs"].copy()
    df_erbs["koppen"] = df_erbs["Ciudad"].apply(lambda c: _get_climate(c)[0])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    for ax, (df_m, model) in zip(axes, [(df_r2,"Reindl2"),(df_erbs,"Erbs")]):
        zones = sorted(df_m["koppen"].unique())
        data  = [df_m[df_m["koppen"]==z]["DNI_nRMSE"].dropna().values for z in zones]
        colors= [KOPPEN_COLORS.get(z,"gray") for z in zones]
        bp = ax.boxplot(data, patch_artist=True, widths=0.5,
                        medianprops=dict(color="black", lw=1.5))
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c); patch.set_alpha(0.8)
        ax.set_xticks(range(1, len(zones)+1))
        ax.set_xticklabels(zones, fontsize=9)
        ax.set_ylabel("nRMSE DNI (%)"); ax.grid(axis="y", alpha=0.3)
        ax.set_title(f"{MLABEL[model]} — nRMSE DNI por zona Köppen", fontsize=10, fontweight="bold")
        # añadir n por zona
        for i, (z, d) in enumerate(zip(zones, data)):
            ax.text(i+1, ax.get_ylim()[1]*0.95, f"n={len(d)}", ha="center", fontsize=7, color="#333")

    fig.suptitle("Error relativo DNI (nRMSE) por zona climática Köppen-Geiger", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig10_nRMSE_Koppen.png", **PLT_KW); plt.close(fig)
    print("  Fig10 OK")


# ══ MAIN ══════════════════════════════════════════════════════════════════════
def main():
    import warnings; warnings.filterwarnings("ignore")
    print("Cargando resultados Excel...")
    df_cities  = pd.read_excel(DATA_XLS, sheet_name="Por_Ciudad")
    df_monthly = pd.read_excel(DATA_XLS, sheet_name="Por_Mes")
    df_best    = pd.read_excel(DATA_XLS, sheet_name="Mejor_modelo")

    print("Cargando datos EPW (1 min aprox)...")
    df_all = load_all_epw_data()

    print("Generando figuras...")
    fig1_mapa(df_best)
    fig_scatter(df_all, "DNI", "DNI_ref", "Fig2_scatter_DNI.png",
                "Dispersión DNI calculado vs. referencia EPW — 41 ciudades argentinas")
    fig_scatter(df_all, "DHI", "DHI_ref", "Fig3_scatter_DHI.png",
                "Dispersión DHI calculado vs. referencia EPW — 41 ciudades argentinas")
    fig4_heatmap(df_cities)
    fig5_nrmse(df_cities)
    fig6_mbe(df_cities)
    fig7_taylor(df_all)
    fig8_mbe_mensual(df_monthly, df_best)
    fig9_r2_vs_kt(df_all, df_cities)
    fig10_boxplot_koppen(df_cities)

    print(f"\nFiguras guardadas en: {OUT}")


if __name__ == "__main__":
    main()
