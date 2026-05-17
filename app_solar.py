"""
app_solar.py — Streamlit UI para descomposición GHI → DNI + DHI.

Flujo:
  Sidebar : carga de archivo → configuración de sitio → parámetros → ejecutar
  Panel   : métricas resumen → gráficos → comparación DIRINT vs Erbs → exportar

Ejecutar:
  streamlit run app_solar.py
"""
from __future__ import annotations

import io
import math
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from io_handler import load_file, summarize_loaded
from preprocessor import aggregate_to_hourly, preprocessing_summary
from decomposition import run_decomposition
from validator import validate
from reporter import (
    build_quality_report,
    export_csv, export_excel,
    report_to_json_str,
    generate_template_excel, generate_template_csv,
)

# ─────────────────────────────────────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Solar Decomp — GHI→DNI+DHI",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────────────────────────────────────
for key in ["loaded", "df_hourly", "df_result", "report", "site_info"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ─────────────────────────────────────────────────────────────────────────────
# Helpers de gráficos
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "GHI":  "#f4a261",
    "DNI_dirint": "#2a9d8f",
    "DHI_dirint": "#457b9d",
    "DNI_erbs":   "#e76f51",
    "DHI_erbs":   "#a8dadc",
    "Kt":   "#8338ec",
    "score": "#06d6a0",
}


def _ts_series(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["timestamp_start"])


def fig_irradiance_timeseries(df: pd.DataFrame) -> go.Figure:
    ts = _ts_series(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts, y=df["GHI_h"],     name="GHI",        line=dict(color=COLORS["GHI"],  width=0.9)))
    fig.add_trace(go.Scatter(x=ts, y=df["DNI_dirint"],name="DNI (DIRINT)",line=dict(color=COLORS["DNI_dirint"], width=0.9)))
    fig.add_trace(go.Scatter(x=ts, y=df["DHI_dirint"],name="DHI (DIRINT)",line=dict(color=COLORS["DHI_dirint"], width=0.9)))
    fig.update_layout(
        title="Serie temporal de irradiancia horaria",
        xaxis_title="Fecha",
        yaxis_title="W/m²",
        hovermode="x unified",
        height=380,
        margin=dict(t=50, b=40, l=60, r=20),
        legend=dict(orientation="h", y=1.08),
    )
    return fig


def fig_model_comparison(df: pd.DataFrame) -> go.Figure:
    """Scatter DNI_dirint vs DNI_erbs + identidad."""
    mask = df["DNI_dirint"].notna() & df["DNI_erbs"].notna()
    d = df[mask]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["DNI_erbs"], y=d["DNI_dirint"],
        mode="markers",
        marker=dict(size=3, color=COLORS["DNI_dirint"], opacity=0.5),
        name="DNI: DIRINT vs Erbs",
    ))
    lim = max(float(d["DNI_erbs"].max()), float(d["DNI_dirint"].max()), 100)
    fig.add_trace(go.Scatter(
        x=[0, lim], y=[0, lim],
        mode="lines",
        line=dict(dash="dash", color="grey", width=1),
        name="1:1",
    ))
    fig.update_layout(
        title="DNI: DIRINT vs Erbs",
        xaxis_title="DNI Erbs [W/m²]",
        yaxis_title="DNI DIRINT [W/m²]",
        height=360,
        margin=dict(t=50, b=40, l=60, r=20),
    )
    return fig


def fig_kt_histogram(df: pd.DataFrame) -> go.Figure:
    kt = df.loc[(df["G0h"] > 0) & df["Kt"].notna(), "Kt"]
    fig = go.Figure(go.Histogram(
        x=kt, nbinsx=50,
        marker_color=COLORS["Kt"],
        opacity=0.8,
        name="Kt",
    ))
    fig.add_vline(x=1.0, line_dash="dash", line_color="red",
                  annotation_text="Cloud enh.", annotation_position="top right")
    fig.update_layout(
        title="Distribución del índice de claridad Kt (horas diurnas)",
        xaxis_title="Kt",
        yaxis_title="Frecuencia",
        height=320,
        margin=dict(t=50, b=40, l=60, r=20),
    )
    return fig


def fig_monthly_energy(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["month"] = pd.to_datetime(df2["timestamp_start"]).dt.month
    month_names = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

    grp = df2[df2["G0h"] > 0].groupby("month")
    months = sorted(grp.groups.keys())
    ghi_kwh  = [grp.get_group(m)["GHI_h"].sum() / 1000 for m in months]
    dni_kwh  = [grp.get_group(m)["DNI_dirint"].sum() / 1000 for m in months]
    dhi_kwh  = [grp.get_group(m)["DHI_dirint"].sum() / 1000 for m in months]
    xlabels  = [month_names[m - 1] for m in months]

    fig = go.Figure()
    fig.add_bar(x=xlabels, y=ghi_kwh,  name="GHI",         marker_color=COLORS["GHI"])
    fig.add_bar(x=xlabels, y=dni_kwh,  name="DNI (DIRINT)", marker_color=COLORS["DNI_dirint"])
    fig.add_bar(x=xlabels, y=dhi_kwh,  name="DHI (DIRINT)", marker_color=COLORS["DHI_dirint"])
    fig.update_layout(
        barmode="group",
        title="Energía mensual (horas diurnas)",
        xaxis_title="Mes",
        yaxis_title="kWh/m²",
        height=360,
        margin=dict(t=50, b=40, l=60, r=20),
        legend=dict(orientation="h", y=1.08),
    )
    return fig


def fig_quality_score(df: pd.DataFrame) -> go.Figure:
    ts = _ts_series(df)
    qs = df["quality_score"]
    fig = go.Figure(go.Scatter(
        x=ts, y=qs,
        mode="lines",
        line=dict(color=COLORS["score"], width=0.9),
        fill="tozeroy",
        fillcolor="rgba(6,214,160,0.15)",
        name="Quality Score",
    ))
    fig.update_layout(
        title="Quality Score horario (0–100)",
        xaxis_title="Fecha",
        yaxis_title="Score",
        yaxis=dict(range=[0, 105]),
        height=300,
        margin=dict(t=50, b=40, l=60, r=20),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("☀️ Solar Decomp")
    st.caption("GHI → DNI + DHI | DIRINT + Erbs")
    st.divider()

    # ── 0. Plantilla descargable ──────────────────────────────────────────────
    st.subheader("0 · Plantilla de datos")
    st.caption("Descarga el template con el formato requerido e instrucciones.")
    col_tmpl_a, col_tmpl_b = st.columns(2)
    with col_tmpl_a:
        st.download_button(
            label="Template Excel",
            data=generate_template_excel(),
            file_name="solar_decomp_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="Excel con hoja de instrucciones + plantilla con filas de ejemplo",
        )
    with col_tmpl_b:
        st.download_button(
            label="Template CSV",
            data=generate_template_csv(),
            file_name="solar_decomp_template.csv",
            mime="text/csv",
            use_container_width=True,
            help="CSV con encabezado descriptivo y filas de ejemplo",
        )
    st.divider()

    # ── 1. Carga de archivo ───────────────────────────────────────────────────
    st.subheader("1 · Datos de entrada")
    uploaded = st.file_uploader(
        "CSV o Excel (.xlsx)",
        type=["csv", "xlsx", "xls"],
        help="Columnas mínimas: timestamp + GHI. Soporta 1-min, 15-min y 60-min.",
    )

    if uploaded is not None and st.session_state.loaded is None:
        with st.spinner("Cargando archivo…"):
            try:
                ld = load_file(uploaded)
                st.session_state.loaded = ld
                st.session_state.df_hourly = None
                st.session_state.df_result = None
                st.session_state.report    = None
            except Exception as e:
                st.error(f"Error al cargar: {e}")
                st.session_state.loaded = None

    if st.button("🔄 Resetear todo", use_container_width=True):
        for k in ["loaded", "df_hourly", "df_result", "report", "site_info"]:
            st.session_state[k] = None
        st.rerun()

    # ── 2. Información del sitio ──────────────────────────────────────────────
    st.subheader("2 · Sitio")
    lat  = st.number_input("Latitud [°N]",      value=-34.6,  min_value=-90.0, max_value=90.0,  step=0.01, format="%.4f")
    lon  = st.number_input("Longitud [°E]",      value=-58.4,  min_value=-180.0, max_value=180.0, step=0.01, format="%.4f")
    tz   = st.number_input("Zona horaria [UTC+]", value=-3.0,  min_value=-12.0, max_value=14.0,  step=0.5,  format="%.1f")

    # ── 3. Parámetros del modelo ──────────────────────────────────────────────
    st.subheader("3 · Modelo")
    primary_model = st.selectbox(
        "Modelo primario",
        options=["DIRINT", "Erbs"],
        index=0,
        help="DIRINT (Perez 1992): recomendado para alta resolución y sitios con variabilidad. "
             "Erbs (1982): más robusto con datos escasos, sin agua precipitable.",
    )
    st.caption(
        "**DIRINT**: lookup 3D [W×ΔKt'×Kt'], considera variabilidad y vapor de agua. "
        "**Erbs**: polinomio piecewise Kd(Kt), robusto pero menos preciso en ciclos claros.",
        unsafe_allow_html=False,
    )

    st.divider()

    # ── 4. Ejecutar ───────────────────────────────────────────────────────────
    run_btn = st.button(
        "▶ Ejecutar descomposición",
        type="primary",
        use_container_width=True,
        disabled=(st.session_state.loaded is None),
    )

# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

if run_btn and st.session_state.loaded is not None:
    ld = st.session_state.loaded
    with st.spinner("Preprocesando y calculando geometría solar…"):
        try:
            df_hourly = aggregate_to_hourly(ld, lat_deg=lat, lon_deg=lon, tz_hr=tz)
            st.session_state.df_hourly = df_hourly
        except Exception as e:
            st.error(f"Error en preprocesamiento: {e}")
            st.error(traceback.format_exc())
            st.stop()

    with st.spinner("Ejecutando modelos DIRINT + Erbs…"):
        try:
            df_dec = run_decomposition(df_hourly, primary=primary_model)
        except Exception as e:
            st.error(f"Error en descomposición: {e}")
            st.error(traceback.format_exc())
            st.stop()

    with st.spinner("Validando y generando reporte…"):
        try:
            df_val  = validate(df_dec)
            site_info = {
                "filename":   ld.df.attrs.get("filename", "archivo_cargado"),
                "lat_deg":    lat,
                "lon_deg":    lon,
                "tz_hr":      tz,
                "resolution": ld.resolution_label,
            }
            report  = build_quality_report(df_val, site_info, primary_model)
            st.session_state.df_result  = df_val
            st.session_state.report     = report
            st.session_state.site_info  = site_info
        except Exception as e:
            st.error(f"Error en validación: {e}")
            st.error(traceback.format_exc())
            st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PANEL PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.loaded is None:
    # ── Pantalla de bienvenida ────────────────────────────────────────────────
    st.markdown("## ☀️ Solar Decomp — GHI → DNI + DHI")
    st.info(
        "Carga un archivo CSV o Excel en el panel lateral para comenzar.\n\n"
        "**Columnas mínimas requeridas:**\n"
        "- Timestamp (cualquier nombre reconocible: `timestamp`, `datetime`, `fecha`, etc.)\n"
        "- GHI en W/m² (nombres reconocidos: `ghi`, `global_horizontal_irradiance`, `swdown`, etc.)\n\n"
        "**Opcionales:** DNI, DHI (referencia), temperatura [°C], presión [kPa/hPa]\n\n"
        "**Resoluciones soportadas:** 1-min · 15-min · 60-min",
        icon="ℹ️",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Modelos implementados")
        st.markdown("""
**DIRINT** (Perez et al., 1992)
- Tabla 3D: [W_precipitable × ΔKt' × Kt']
- Usa variabilidad horaria de Kt'
- Modelo primario recomendado

**Erbs** (Erbs et al., 1982)
- Polinomio Kd(Kt) por tramos
- Sin requerimiento de T/P
- Fallback / comparación
        """)
    with col2:
        st.markdown("### Flujo de procesamiento")
        st.markdown("""
1. **Carga** · Detección automática de columnas y resolución
2. **Preproceso** · Agregación horaria + geometría solar (Yallop)
3. **Descomposición** · DIRINT + Erbs en paralelo
4. **Validación** · Flags físicos + quality score (0–100)
5. **Exportación** · CSV / Excel + reporte JSON
        """)

elif st.session_state.df_result is None:
    # ── Archivo cargado, pendiente de ejecutar ────────────────────────────────
    ld = st.session_state.loaded
    summ = summarize_loaded(ld)

    st.markdown("## Archivo cargado — listo para procesar")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filas totales",     f"{summ['n_rows']:,}")
    c2.metric("Resolución",        summ['resolution'])
    c3.metric("GHI máx [W/m²]",    f"{summ['ghi_max']:.1f}")
    c4.metric("Datos faltantes",   f"{summ['ghi_nan_pct']:.1f}%")

    st.markdown(f"**Inicio:** {summ['start']} &nbsp;|&nbsp; **Fin:** {summ['end']}")
    st.markdown(f"**Columna GHI:** `{summ['ghi_col']}`")

    detected_opt = []
    if summ["has_dni"]:      detected_opt.append("DNI (referencia)")
    if summ["has_dhi"]:      detected_opt.append("DHI (referencia)")
    if summ["has_temp"]:     detected_opt.append("Temperatura")
    if summ["has_pressure"]: detected_opt.append("Presión")
    if detected_opt:
        st.success("Columnas opcionales detectadas: " + ", ".join(detected_opt))

    if summ["warnings"]:
        for w in summ["warnings"]:
            st.warning(w)

    st.info("Configura latitud, longitud y zona horaria en el panel lateral, luego presiona **▶ Ejecutar descomposición**.")

else:
    # ── RESULTADOS ────────────────────────────────────────────────────────────
    df   = st.session_state.df_result
    rep  = st.session_state.report
    s    = rep["summary"]

    st.markdown(f"## Resultados — modelo primario: **{rep['metadata']['primary_model']}**")

    # ── Métricas resumen ──────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Horas diurnas válidas",  f"{s['n_daytime_hours']:,}")
    c2.metric("GHI acum. [kWh/m²]",     f"{s['ghi_total_Wh_m2']/1000:.1f}")
    c3.metric("DNI acum. [kWh/m²]",     f"{s['dni_total_Wh_m2']/1000:.1f}")
    c4.metric("DHI acum. [kWh/m²]",     f"{s['dhi_total_Wh_m2']/1000:.1f}")
    c5.metric("Quality score (media)",   f"{s['quality_score_mean']:.1f}")

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Kt medio (diurno)",       f"{s['kt_mean']:.3f}")
    c7.metric("Kt máx",                  f"{s['kt_max']:.3f}")
    c8.metric("Horas inválidas",         f"{s['n_invalid_hours']:,}")
    flags = rep["flags"]
    n_enh = flags.get("flag_kt_cloud_enh", {}).get("count", 0)
    c9.metric("Cloud enhancement",       f"{n_enh} h")

    # ── Advertencias de flags ─────────────────────────────────────────────────
    n_unphy = flags.get("flag_kt_unphysical", {}).get("count", 0)
    if n_unphy > 0:
        st.warning(f"⚠ {n_unphy} horas con Kt > 1.05 (probable error de sensor).")
    if s["quality_score_min"] < 50:
        st.warning("⚠ Algunas horas tienen quality score < 50. Revisar reporte de flags.")

    st.divider()

    # ── Gráficos ──────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["Serie temporal", "Energía mensual", "Comparación DIRINT vs Erbs", "Calidad"])

    with tab1:
        st.plotly_chart(fig_irradiance_timeseries(df), use_container_width=True)
        st.plotly_chart(fig_kt_histogram(df), use_container_width=True)

    with tab2:
        st.plotly_chart(fig_monthly_energy(df), use_container_width=True)

        # Tabla mensual
        monthly = rep.get("monthly_stats", {})
        if monthly:
            month_names = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
            rows = []
            for m, stats in sorted(monthly.items()):
                rows.append({
                    "Mes":            month_names[int(m) - 1],
                    "GHI [kWh/m²]":  stats["GHI_sum_kWh_m2"],
                    "DNI [kWh/m²]":  stats["DNI_sum_kWh_m2"],
                    "DHI [kWh/m²]":  stats["DHI_sum_kWh_m2"],
                    "Kt medio":       stats["Kt_mean"],
                    "Quality (med)":  stats["quality_mean"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab3:
        mc = rep.get("model_comparison", {})
        if mc:
            col_d, col_e = st.columns(2)
            col_d.markdown("**DNI**")
            col_d.metric("DIRINT medio [W/m²]",  f"{mc['DNI']['DIRINT_mean']:.1f}")
            col_d.metric("Erbs medio [W/m²]",    f"{mc['DNI']['Erbs_mean']:.1f}")
            col_d.metric("RMSE [W/m²]",           f"{mc['DNI']['RMSE_W_m2']:.1f}")
            col_d.metric("Diferencia [%]",        f"{mc['DNI']['diff_pct']:.1f}")

            col_e.markdown("**DHI**")
            col_e.metric("DIRINT medio [W/m²]",  f"{mc['DHI']['DIRINT_mean']:.1f}")
            col_e.metric("Erbs medio [W/m²]",    f"{mc['DHI']['Erbs_mean']:.1f}")
            col_e.metric("RMSE [W/m²]",           f"{mc['DHI']['RMSE_W_m2']:.1f}")
            col_e.metric("Diferencia [%]",        f"{mc['DHI']['diff_pct']:.1f}")

        st.plotly_chart(fig_model_comparison(df), use_container_width=True)

        st.markdown(
            "**¿Cuándo elegir cada modelo?**\n\n"
            "- **DIRINT** tiene menor error sistemático en climas con alta variabilidad "
            "nube/sol y cuando hay datos de temperatura/presión para estimar W.\n"
            "- **Erbs** es más robusto cuando los datos son escasos o el clima es muy nublado "
            "(Kt < 0.4 predominante); no requiere vapor de agua.\n"
            "- La diferencia absoluta entre ambos se muestra en la métrica RMSE arriba."
        )

    with tab4:
        st.plotly_chart(fig_quality_score(df), use_container_width=True)

        # Tabla de flags
        flag_rows = []
        for fname, fdata in flags.items():
            flag_rows.append({
                "Flag":    fname,
                "Horas":   fdata["count"],
                "% horas": f"{fdata['pct']:.1f}%",
            })
        st.dataframe(pd.DataFrame(flag_rows), use_container_width=True, hide_index=True)

        # Distribución quality score
        qd = rep.get("quality_distribution", {})
        if qd:
            st.markdown("**Distribución del quality score**")
            qd_df = pd.DataFrame(
                [{"Rango": k, "Horas": v} for k, v in qd.items()]
            )
            st.dataframe(qd_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Exportar ──────────────────────────────────────────────────────────────
    st.subheader("Exportar resultados")
    col_exp1, col_exp2, col_exp3 = st.columns(3)

    with col_exp1:
        csv_bytes = export_csv(df, minimal=False)
        st.download_button(
            "⬇ CSV completo",
            data=csv_bytes,
            file_name="solar_decomp_resultados.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_exp2:
        xlsx_bytes = export_excel(df, rep, minimal=False)
        st.download_button(
            "⬇ Excel (datos + reporte)",
            data=xlsx_bytes,
            file_name="solar_decomp_resultados.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_exp3:
        json_str = report_to_json_str(rep)
        st.download_button(
            "⬇ Reporte JSON",
            data=json_str,
            file_name="solar_decomp_reporte.json",
            mime="application/json",
            use_container_width=True,
        )

    # ── Tabla de datos (expandible) ───────────────────────────────────────────
    with st.expander("Ver tabla de datos (primeras 96 filas)"):
        preview_cols = [
            "timestamp_start", "GHI_h", "DNI_dirint", "DHI_dirint",
            "DNI_erbs", "DHI_erbs", "Kt", "zenith_deg", "quality_score",
        ]
        show_cols = [c for c in preview_cols if c in df.columns]
        st.dataframe(
            df[show_cols].head(96).style.format(
                {c: "{:.2f}" for c in show_cols if c != "timestamp_start"},
                na_rep="—",
            ),
            use_container_width=True,
        )
