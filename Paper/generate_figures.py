"""
generate_figures.py — Figuras para el paper científico.

Genera en Paper/figuras/:
  Fig1_mapa_mejor_modelo.png      — Mapa Argentina, mejor modelo DNI por ciudad
  Fig2_scatter_DNI.png            — Scatter obs vs pred DNI (3 modelos)
  Fig3_scatter_DHI.png            — Scatter obs vs pred DHI (3 modelos)
  Fig4_heatmap_R2_DNI.png         — Heatmap R² DNI por ciudad × modelo
  Fig5_nRMSE_por_ciudad.png       — nRMSE DNI barras por ciudad
  Fig6_MBE_por_modelo.png         — MBE DNI por modelo (boxplot)

Requiere: matplotlib, cartopy (mapa) o folium — si cartopy no está disponible
usa matplotlib con scatter simple sobre coordenadas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT   = Path(__file__).resolve().parent
OUT    = ROOT / "figuras"
OUT.mkdir(exist_ok=True)

DATA_XLS = ROOT / "resultados_validacion" / "validacion_ciudades.xlsx"
EPW_DIR  = ROOT.parent / "EPWs"

# Agregar raíz al path para importar módulos del proyecto
sys.path.insert(0, str(ROOT.parent))
from epw_parser import parse_epw
from solar_geometry import compute_geometry_df
from decomposition import run_decomposition

# ── Colores y estilos ─────────────────────────────────────────────────────────
COLORS  = {"DIRINT": "#e15759", "Erbs": "#4e79a7", "Reindl2": "#59a14f"}
MARKERS = {"DIRINT": "^",       "Erbs": "s",        "Reindl2": "o"}
MODEL_LABELS = {"DIRINT": "DIRINT", "Erbs": "Erbs", "Reindl2": "Reindl-2"}
PLT_PARAMS = {"dpi": 150, "bbox_inches": "tight"}

MIN_GHI  = 10.0
MIN_COSZ = 0.0174


def load_all_epw_data() -> pd.DataFrame:
    """Carga todos los EPW y corre descomposición. Retorna DataFrame combinado."""
    all_rows = []
    for epw_path in sorted(EPW_DIR.glob("*.EPW")) + sorted(EPW_DIR.glob("*.epw")):
        meta, df_raw = parse_epw(epw_path)
        df_day = df_raw[df_raw["GHI"] >= MIN_GHI].copy().reset_index(drop=True)
        if len(df_day) < 100:
            continue
        df_hour = pd.DataFrame({
            "timestamp_start":  df_day["timestamp"],
            "timestamp_center": df_day["timestamp"] + pd.Timedelta(minutes=30),
            "GHI_h":    df_day["GHI"],
            "coverage": 1.0,
            "temp_C":   df_day["temp_C"],
            "pressure_kPa": df_day["pressure_kPa"],
        })
        geo = compute_geometry_df(df_hour, meta["lat"], meta["lon"], meta["tz"])
        df_hour["cos_Z"] = geo["cos_Z"]; df_hour["G0n"] = geo["G0n"]
        df_hour["G0h"]   = geo["G0h"];   df_hour["zenith_deg"] = geo["zenith_deg"]
        df_hour["AM"]    = geo["AM"]
        g0h = geo["G0h"]
        df_hour["Kt"] = np.where(g0h > 0, df_day["GHI"].values / g0h, np.nan)
        try:
            df_dec = run_decomposition(df_hour, primary="DIRINT", min_cosz=MIN_COSZ)
        except Exception:
            continue
        df_dec["DNI_ref"] = df_day["DNI_ref"].values
        df_dec["DHI_ref"] = df_day["DHI_ref"].values
        df_dec["city"]    = meta["city"]
        df_dec["lat"]     = meta["lat"]
        df_dec["lon"]     = meta["lon"]
        all_rows.append(df_dec)
    return pd.concat(all_rows, ignore_index=True)


def metrics(obs, pred):
    mask = np.isfinite(obs) & np.isfinite(pred)
    o, p = obs[mask], pred[mask]
    if len(o) < 10:
        return np.nan, np.nan, np.nan
    rmse = float(np.sqrt(np.mean((p - o)**2)))
    mbe  = float(np.mean(p - o))
    ss   = np.sum((o - o.mean())**2)
    r2   = float(1 - np.sum((p-o)**2)/ss) if ss > 0 else np.nan
    return rmse, mbe, r2


# ══════════════════════════════════════════════════════════════════════════════
# FIG 1 — Mapa Argentina: mejor modelo DNI por ciudad
# ══════════════════════════════════════════════════════════════════════════════

def fig1_mapa(df_best: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(6, 9))
    ax.set_facecolor("#e8f4f8")
    fig.patch.set_facecolor("white")

    # Contorno simple de Argentina (bounding box + indicativo)
    ax.set_xlim(-74, -52)
    ax.set_ylim(-56, -21)
    ax.set_xlabel("Longitud (°)", fontsize=9)
    ax.set_ylabel("Latitud (°)", fontsize=9)
    ax.set_title("Mejor modelo de descomposición DNI\npor ciudad — Argentina", fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3, linewidth=0.5)

    model_order = ["Reindl2", "Erbs", "DIRINT"]
    for model in model_order:
        sub = df_best[df_best["Mejor_modelo_DNI"] == model]
        if sub.empty:
            continue
        ax.scatter(
            sub["Lon"], sub["Lat"],
            c=COLORS[model], marker=MARKERS[model],
            s=80, zorder=5, edgecolors="k", linewidths=0.4,
            label=f"{MODEL_LABELS[model]} (n={len(sub)})"
        )
        for _, row in sub.iterrows():
            ax.annotate(
                row["Ciudad"].split("-")[0].title(),
                (row["Lon"], row["Lat"]),
                fontsize=5.5, xytext=(3, 3), textcoords="offset points", color="#333"
            )

    # Colorear puntos por R²
    norm = Normalize(vmin=0.85, vmax=0.97)
    sm   = ScalarMappable(cmap="RdYlGn", norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.4, pad=0.02)
    cbar.set_label("R² DNI", fontsize=8)

    ax.legend(fontsize=8, loc="lower left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(OUT / "Fig1_mapa_mejor_modelo.png", **PLT_PARAMS)
    plt.close(fig)
    print("  Fig1 guardada")


# ══════════════════════════════════════════════════════════════════════════════
# FIG 2 & 3 — Scatter obs vs pred (DNI y DHI)
# ══════════════════════════════════════════════════════════════════════════════

def fig_scatter(df_all: pd.DataFrame, var: str, ref_col: str, fname: str, title: str):
    models = [("DIRINT", "DNI_dirint" if var=="DNI" else "DHI_dirint"),
              ("Erbs",   "DNI_erbs"   if var=="DNI" else "DHI_erbs"),
              ("Reindl2","DNI_reindl2" if var=="DNI" else "DHI_reindl2")]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True, sharex=True)
    lim = (0, 1050) if var == "DNI" else (0, 550)

    for ax, (model, pred_col) in zip(axes, models):
        obs  = df_all[ref_col].values
        pred = df_all[pred_col].values if pred_col in df_all.columns else np.full(len(obs), np.nan)
        mask = np.isfinite(obs) & np.isfinite(pred) & (obs > 0)
        o, p = obs[mask], pred[mask]

        # Densidad aproximada por hexbin
        hb = ax.hexbin(o, p, gridsize=60, cmap="YlOrRd", mincnt=1, extent=(*lim, *lim))
        ax.plot(lim, lim, "k--", lw=0.8, alpha=0.6)

        rmse, mbe, r2 = metrics(o, p)
        ax.set_title(f"{MODEL_LABELS[model]}\nR²={r2:.3f}  RMSE={rmse:.0f} W/m²  MBE={mbe:+.0f}", fontsize=9)
        ax.set_xlabel(f"{var} referencia EPW (W/m²)", fontsize=8)
        if ax == axes[0]:
            ax.set_ylabel(f"{var} calculado (W/m²)", fontsize=8)
        ax.set_xlim(lim); ax.set_ylim(lim)
        ax.tick_params(labelsize=7)
        plt.colorbar(hb, ax=ax).set_label("N horas", fontsize=7)

    fig.suptitle(title, fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(OUT / fname, **PLT_PARAMS)
    plt.close(fig)
    print(f"  {fname} guardada")


# ══════════════════════════════════════════════════════════════════════════════
# FIG 4 — Heatmap R² DNI por ciudad × modelo
# ══════════════════════════════════════════════════════════════════════════════

def fig4_heatmap(df_cities: pd.DataFrame):
    pivot = df_cities.pivot_table(index="Ciudad", columns="Modelo", values="DNI_R2", aggfunc="mean")
    pivot = pivot.sort_values("Reindl2", ascending=True)
    models_order = ["DIRINT", "Erbs", "Reindl2"]
    pivot = pivot[[m for m in models_order if m in pivot.columns]]

    fig, ax = plt.subplots(figsize=(7, 11))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn",
                   vmin=0.75, vmax=0.97)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([MODEL_LABELS.get(c, c) for c in pivot.columns], fontsize=10)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([c.replace("-AERO","").replace("-"," ").title() for c in pivot.index], fontsize=7)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if np.isfinite(val):
                ax.text(j, i, f"{val:.3f}", ha="center", va="center",
                        fontsize=6, color="black" if val > 0.82 else "white")
    plt.colorbar(im, ax=ax, shrink=0.5).set_label("R² DNI", fontsize=9)
    ax.set_title("R² DNI por ciudad y modelo\n(ordenado por Reindl-2)", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "Fig4_heatmap_R2_DNI.png", **PLT_PARAMS)
    plt.close(fig)
    print("  Fig4 guardada")


# ══════════════════════════════════════════════════════════════════════════════
# FIG 5 — nRMSE DNI por ciudad (barras agrupadas)
# ══════════════════════════════════════════════════════════════════════════════

def fig5_nrmse(df_cities: pd.DataFrame):
    pivot = df_cities.pivot_table(index="Ciudad", columns="Modelo", values="DNI_nRMSE", aggfunc="mean")
    pivot = pivot.sort_values("Reindl2", ascending=False)
    models_order = ["DIRINT", "Erbs", "Reindl2"]
    pivot = pivot[[m for m in models_order if m in pivot.columns]]

    n     = len(pivot)
    x     = np.arange(n)
    width = 0.25

    fig, ax = plt.subplots(figsize=(14, 5))
    for i, model in enumerate(pivot.columns):
        ax.bar(x + i*width, pivot[model], width, label=MODEL_LABELS[model],
               color=COLORS[model], edgecolor="white", linewidth=0.3)

    ax.set_xticks(x + width)
    ax.set_xticklabels([c.replace("-AERO","").replace("-"," ").title() for c in pivot.index],
                       rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("nRMSE DNI (%)", fontsize=9)
    ax.set_title("Error relativo DNI (nRMSE) por ciudad y modelo", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "Fig5_nRMSE_por_ciudad.png", **PLT_PARAMS)
    plt.close(fig)
    print("  Fig5 guardada")


# ══════════════════════════════════════════════════════════════════════════════
# FIG 6 — MBE DNI por modelo (boxplot)
# ══════════════════════════════════════════════════════════════════════════════

def fig6_mbe_boxplot(df_cities: pd.DataFrame):
    models_order = ["DIRINT", "Erbs", "Reindl2"]
    data = [df_cities[df_cities["Modelo"] == m]["DNI_MBE"].dropna().values
            for m in models_order]

    fig, ax = plt.subplots(figsize=(6, 5))
    bp = ax.boxplot(data, patch_artist=True, widths=0.5,
                    medianprops=dict(color="black", linewidth=2))
    for patch, model in zip(bp["boxes"], models_order):
        patch.set_facecolor(COLORS[model])
        patch.set_alpha(0.8)

    ax.axhline(0, color="k", lw=0.8, ls="--")
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([MODEL_LABELS[m] for m in models_order], fontsize=10)
    ax.set_ylabel("MBE DNI (W/m²)", fontsize=9)
    ax.set_title("Sesgo (MBE) DNI por modelo\n(distribución sobre 41 ciudades)", fontsize=11, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "Fig6_MBE_boxplot.png", **PLT_PARAMS)
    plt.close(fig)
    print("  Fig6 guardada")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Cargando resultados...")
    df_cities = pd.read_excel(DATA_XLS, sheet_name="Por_Ciudad")
    df_best   = pd.read_excel(DATA_XLS, sheet_name="Mejor_modelo")

    print("Cargando datos EPW para scatter (puede tomar ~1 min)...")
    df_all = load_all_epw_data()

    print("Generando figuras...")
    fig1_mapa(df_best)
    fig_scatter(df_all, "DNI", "DNI_ref", "Fig2_scatter_DNI.png",
                "Dispersión DNI calculado vs. referencia EPW — 41 ciudades argentinas")
    fig_scatter(df_all, "DHI", "DHI_ref", "Fig3_scatter_DHI.png",
                "Dispersión DHI calculado vs. referencia EPW — 41 ciudades argentinas")
    fig4_heatmap(df_cities)
    fig5_nrmse(df_cities)
    fig6_mbe_boxplot(df_cities)

    print(f"\nFiguras guardadas en: {OUT}")


if __name__ == "__main__":
    main()
