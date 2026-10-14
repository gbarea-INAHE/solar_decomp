"""
app_solar.py — Streamlit UI para descomposición GHI → DNI + DHI.

Flujo:
  Sidebar : carga de archivo → configuración de sitio → parámetros → ejecutar
  Panel   : métricas resumen → gráficos → comparación de modelos → exportar

Ejecutar:
  streamlit run app_solar.py
"""
from __future__ import annotations

import io
import math
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from io_handler import load_file, summarize_loaded
from preprocessor import aggregate_to_hourly, preprocessing_summary
from decomposition import run_decomposition
from reference import consistency_table, hourly_reference
from validator import validate
from reporter import (
    build_quality_report,
    export_csv, export_excel,
    report_to_json_str,
    generate_template_excel, generate_template_csv,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes de autoría y citación
# ─────────────────────────────────────────────────────────────────────────────
_DOI     = "10.5281/zenodo.20262706"
_DOI_URL = f"https://doi.org/{_DOI}"

_APA_CITATION = (
    "Barea, G., & Ganem, C. (2026).*Solar Decomp: GHI to DNI+DHI solar irradiance "
    f"decomposition* [Software]. INAHE-CONICET. Zenodo. {_DOI_URL}"
)

_BIBTEX_CITATION = f"""@software{{barea_ganem_2026_solar_decomp,
  author    = {{Barea, Gustavo and Ganem, Carolina}},
  title     = {{Solar Decomp: GHI to DNI+DHI solar irradiance decomposition}},
  year      = {{2026}},
  publisher = {{Zenodo}},
  doi       = {{{_DOI}}},
  url       = {{{_DOI_URL}}}
}}"""

_VALIDATION_MD = """
### Sobre los datos de referencia y esta versión

**Qué mide una comparación con un archivo de referencia.** Si el archivo de referencia es un TMY (por ejemplo, un archivo IWEC2), su DNI y su DHI no son mediciones: se generan a partir de la GHI del propio archivo (en IWEC2, con una partición de tipo Gompertz). Comparar los modelos contra ese tipo de referencia mide **consistencia con la referencia**, no exactitud. Para evaluar la exactitud hacen falta mediciones independientes de DNI y DHI.

**Versión 1.1.0.** El modelo DIRINT es ahora el de Perez et al. (1992), a través de `pvlib`. La versión 1.0.0 usaba una tabla propia que no coincidía con la de Perez et al. (1992) y sobreestimaba la DNI; esa tabla se conserva en el código solo para reproducir resultados publicados con esa versión. Ver `CHANGELOG.md`.

**Resultados de validación.** La validación con el archivo de Córdoba que figuraba en versiones anteriores se retiró: usaba la tabla anterior del DIRINT y una referencia que no es una medición. El artículo asociado y sus resultados se enlazarán aquí cuando estén publicados.

---

### Referencias

- Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. *ASHRAE Transactions*, 98(1), 354–369.
- Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation. *Solar Energy*, 28(4), 293–302. https://doi.org/10.1016/0038-092X(82)90302-4
- Reindl, D.T., Beckman, W.A., & Duffie, J.A. (1990). Diffuse fraction correlations. *Solar Energy*, 45(1), 1–7. https://doi.org/10.1016/0038-092X(90)90060-P
- Spencer, J.W. (1971). Fourier series representation of the position of the sun. *Search*, 2(5), 172.
- Cooper, P.I. (1969). The absorption of radiation in solar stills. *Solar Energy*, 12(3), 333–346.
- Kasten, F., & Young, A.T. (1989). Revised optical air mass tables and approximation formula. *Applied Optics*, 28(22), 4735–4738.
"""

_DISCLAIMER = (
    "Esta herramienta se encuentra en desarrollo y validación continua. "
    "Los resultados deben interpretarse como apoyo técnico-científico y no reemplazan "
    "la evaluación profesional específica de cada caso. Los autores y las instituciones "
    "asociadas (INAHE-CONICET) no asumen responsabilidad por decisiones técnicas, "
    "económicas o normativas tomadas exclusivamente a partir de los resultados generados. "
    "El usuario es responsable de verificar la calidad de los datos cargados e interpretar "
    "los resultados en su contexto específico."
)

# ─────────────────────────────────────────────────────────────────────────────
# Logo INAHE
# ─────────────────────────────────────────────────────────────────────────────
_ROOT          = Path(__file__).resolve().parent
_LOGO_PATH     = _ROOT / "assets" / "inahe_logo.jpg"
_TEMPLATE_PATH = _ROOT / "assets" / "plantilla_datos_v2.xlsx"

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
# Encabezado principal
# ─────────────────────────────────────────────────────────────────────────────
_logo_col, _title_col = st.columns([1, 5])
with _logo_col:
    if _LOGO_PATH.is_file():
        st.image(str(_LOGO_PATH), width=150)
with _title_col:
    st.title("Solar Decomp — GHI → DNI + DHI")
    st.markdown(
        "**Autores:** Dr. Arq. Gustavo Barea Paci &nbsp;·&nbsp; Dra. Arq. Carolina Ganem &nbsp;|&nbsp; "
        "**Institución:** INAHE · CONICET"
    )
    st.caption(
        "Modelos: DIRINT (Perez et al., 1992) · Erbs (Erbs et al., 1982) · Reindl-2 (Reindl et al., 1990) "
        "| Geometría solar: Spencer (1971) / Cooper (1969) | Resoluciones: 1-min · 15-min · 60-min"
    )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────────────────────────────────────
for key in ["loaded", "df_hourly", "df_result", "report", "site_info", "ref_table"]:
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
    st.caption("GHI → DNI + DHI | DIRINT · Erbs · Reindl-2")
    st.divider()

    # ── 0. Plantilla descargable ──────────────────────────────────────────────
    st.subheader("0 · Plantilla de datos")
    st.caption("Descarga el template con el formato requerido e instrucciones.")
    col_tmpl_a, col_tmpl_b = st.columns(2)
    with col_tmpl_a:
        _tmpl_bytes = (
            _TEMPLATE_PATH.read_bytes()
            if _TEMPLATE_PATH.is_file()
            else generate_template_excel()
        )
        st.download_button(
            label="Template Excel",
            data=_tmpl_bytes,
            file_name="plantilla_datos_v2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="Planilla con columnas: Date/Time, Global Solar Wh/m2, Normal Solar, Diffuse Solar, Temperatura, Presion",
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
        "CSV, Excel (.xlsx) o EPW",
        type=["csv", "xlsx", "xls", "epw"],
        help=(
            "CSV / Excel: columnas mínimas timestamp + GHI; soporta 1-min, 15-min y 60-min. "
            "EPW: 1 registro por hora; se leen GHI, temperatura, presión (Pa), humedad y punto de rocío, "
            "y el DNI / DHI del archivo se usan como referencia."
        ),
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

    if st.button("Resetear todo", use_container_width=True):
        for k in ["loaded", "df_hourly", "df_result", "report", "site_info", "ref_table"]:
            st.session_state[k] = None
        st.rerun()

    # ── 2. Información del sitio ──────────────────────────────────────────────
    st.subheader("2 · Sitio")
    _ep = st.session_state.loaded.epw_meta if st.session_state.loaded is not None else None
    if _ep:
        st.info(
            f"Sitio tomado del encabezado del EPW «{_ep['city']}» ({_ep['country']}). Revise los valores antes de ejecutar.",
            icon="📍",
        )
    lat = st.number_input("Latitud [°N]",        value=(_ep["lat"] if _ep else -34.6),  min_value=-90.0,  max_value=90.0,  step=0.01, format="%.4f")
    lon = st.number_input("Longitud [°E]",        value=(_ep["lon"] if _ep else -58.4),  min_value=-180.0, max_value=180.0, step=0.01, format="%.4f")
    alt = st.number_input("Altitud [m s.n.m.]",   value=(min(max(_ep["elev"], 0.0), 5000.0) if _ep else 25.0),   min_value=0.0,    max_value=5000.0, step=10.0, format="%.0f",
                          help="Usada para estimar presión atmosférica cuando no hay datos medidos.")
    tz  = st.number_input("Zona horaria [UTC+]",  value=(_ep["tz"] if _ep else -3.0),   min_value=-12.0,  max_value=14.0,  step=0.5,  format="%.1f")

    # ── 3. Modelos ────────────────────────────────────────────────────────────
    st.subheader("3 · Modelos")
    st.info(
        "El programa calcula los **3 modelos en paralelo**. "
        "Los resultados de cada uno se exportan en columnas separadas.",
        icon="ℹ️",
    )
    st.markdown(
        "- **Reindl-2** (Reindl et al., 1990): incorpora la elevación solar sin(α).\n"
        "- **Erbs** (Erbs et al., 1982): polinomio de la fracción difusa Kd en función de Kt. "
        "No requiere temperatura ni humedad.\n"
        "- **DIRINT** (Perez et al., 1992, vía pvlib): tabla de coeficientes con Kt', ángulo cenital, "
        "ΔKt' y agua precipitable. Por defecto usa la clase de «agua precipitable desconocida»; "
        "solo usa el punto de rocío si se activa la opción."
    )
    primary_model = "DIRINT"  # se calculan los 3; columnas DNI/DHI usan DIRINT por compatibilidad

    min_cosz = st.slider(
        "Umbral min cos(Z)",
        min_value=0.01, max_value=0.20, value=0.08, step=0.01,
        help=(
            "Horas con cos(Z) menor a este umbral se descartan. "
            "Valor sugerido: 0.08 (cenit ~85°). "
            "Reducir si se pierden muchas horas del amanecer/atardecer."
        ),
    )

    _is_epw = st.session_state.loaded is not None and st.session_state.loaded.is_epw
    preserve_existing = st.checkbox(
        "No recalcular filas con DNI/DHI existentes",
        value=not _is_epw,
        help=(
            "Si el archivo ya contiene columnas DNI y/o DHI con datos, "
            "se conservan esos valores y solo se calculan los faltantes. "
            "En un EPW está desactivado por defecto: su DNI / DHI son la referencia con la que se comparan los modelos."
        ),
    )

    _ld_td = st.session_state.loaded
    _td_possible = _ld_td is not None and bool(_ld_td.dewpoint_col or (_ld_td.humidity_col and _ld_td.temp_col))
    use_dew_point = st.checkbox(
        "Usar humedad / punto de rocío en el DIRINT",
        value=False,
        disabled=not _td_possible,
        help=(
            "Opcional. Por defecto el DIRINT usa el bin de «agua precipitable desconocida» de Perez et al. (1992). "
            "Si el archivo trae humedad relativa (con temperatura) o punto de rocío, puede usarse para estimar el agua precipitable. "
            "En una prueba con 4 estaciones medidas esto no redujo el error de DNI (lo aumentó entre 3 y 5 W/m²). "
            "Se habilita solo si el archivo trae esos datos."
        ),
    )

    st.divider()

    # ── 4. Ejecutar ───────────────────────────────────────────────────────────
    run_btn = st.button(
        "Ejecutar descomposicion",
        type="primary",
        use_container_width=True,
        disabled=(st.session_state.loaded is None),
    )

# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

if run_btn and st.session_state.loaded is not None:
    ld = st.session_state.loaded
    with st.spinner("Preprocesando y calculando geometria solar…"):
        try:
            df_hourly = aggregate_to_hourly(
                ld, lat_deg=lat, lon_deg=lon, tz_hr=tz, altitude_m=alt,
            )
            st.session_state.df_hourly = df_hourly
        except Exception as e:
            st.error(f"Error en preprocesamiento: {e}")
            st.error(traceback.format_exc())
            st.stop()

    with st.spinner("Ejecutando modelos DIRINT + Erbs + Reindl-2…"):
        try:
            df_dec = run_decomposition(df_hourly, primary=primary_model, min_cosz=min_cosz, use_dew_point=use_dew_point)
        except Exception as e:
            st.error(f"Error en descomposicion: {e}")
            st.error(traceback.format_exc())
            st.stop()

    # ── Consistencia con el DNI / DHI del archivo (antes de cualquier sobrescritura) ─────────────
    ref_table = None
    if ld.dni_col or ld.dhi_col:
        try:
            _r_dni, _r_dhi = hourly_reference(ld, df_dec["timestamp_start"])
            ref_table = consistency_table(df_dec, _r_dni, _r_dhi)
        except Exception as e:
            st.warning(f"No se pudo calcular la consistencia con el DNI / DHI del archivo: {e}")
    st.session_state.ref_table = ref_table

    # ── Preserve existing DNI/DHI ─────────────────────────────────────────────
    if preserve_existing and ld.dni_col and ld.dhi_col:
        try:
            _grp_dni = ld.df.groupby(ld.df["_timestamp"].dt.floor("h"))[ld.dni_col].mean()
            _grp_dhi = ld.df.groupby(ld.df["_timestamp"].dt.floor("h"))[ld.dhi_col].mean()
            _orig_dni = pd.to_numeric(_grp_dni, errors="coerce").reindex(df_dec["timestamp_start"]).values
            _orig_dhi = pd.to_numeric(_grp_dhi, errors="coerce").reindex(df_dec["timestamp_start"]).values
            _has_dni  = ~np.isnan(_orig_dni)
            _has_dhi  = ~np.isnan(_orig_dhi)
            if _has_dni.any():
                df_dec.loc[_has_dni, "DNI"]        = _orig_dni[_has_dni]
                df_dec.loc[_has_dni, "DNI_dirint"]  = _orig_dni[_has_dni]
                df_dec.loc[_has_dni, "model_primary"] = "original"
            if _has_dhi.any():
                df_dec.loc[_has_dhi, "DHI"]        = _orig_dhi[_has_dhi]
                df_dec.loc[_has_dhi, "DHI_dirint"]  = _orig_dhi[_has_dhi]
        except Exception:
            pass  # preserve_existing falla silenciosamente — no bloquea el flujo

    with st.spinner("Validando y generando reporte…"):
        try:
            df_val  = validate(df_dec)
            site_info = {
                "filename":   ld.df.attrs.get("filename", "archivo_cargado"),
                "lat_deg":    lat,
                "lon_deg":    lon,
                "alt_m":      alt,
                "tz_hr":      tz,
                "resolution": ld.resolution_label,
                "min_cosz":   min_cosz,
            }
            report  = build_quality_report(df_val, site_info, primary_model)
            st.session_state.df_result  = df_val
            st.session_state.report     = report
            st.session_state.site_info  = site_info
        except Exception as e:
            st.error(f"Error en validacion: {e}")
            st.error(traceback.format_exc())
            st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PANEL PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.loaded is None:
    # ── Pantalla de bienvenida ────────────────────────────────────────────────
    st.markdown("## ☀️ Solar Decomp — GHI → DNI + DHI")
    st.info(
        "Carga un archivo CSV, Excel o EPW en el panel lateral para comenzar.\n\n"
        "**Columnas mínimas requeridas:**\n"
        "- Timestamp (cualquier nombre reconocible: `timestamp`, `datetime`, `fecha`, etc.)\n"
        "- GHI en W/m² (nombres reconocidos: `ghi`, `global_horizontal_irradiance`, `swdown`, etc.)\n\n"
        "**Opcionales:** DNI, DHI (referencia), temperatura [°C], presión [kPa/hPa], humedad relativa [%] o punto de rocío [°C]\n\n"
        "**Resoluciones soportadas:** 1-min · 15-min · 60-min",
        icon="ℹ️",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Modelos implementados")
        st.markdown("""
**DIRINT** (Perez et al., 1992)
- Tabla de coeficientes: Kt', ángulo cenital, ΔKt' y agua precipitable
- Usa variabilidad horaria de Kt'
- Modelo primario por defecto

**Erbs** (Erbs et al., 1982)
- Polinomio Kd(Kt) por tramos
- Sin requerimiento de T/P
- Fallback / comparación

**Reindl-2** (Reindl et al., 1990)
- Incorpora la elevación solar sin(α)
        """)
    with col2:
        st.markdown("### Flujo de procesamiento")
        st.markdown("""
1. **Carga** · Detección automática de columnas y resolución
2. **Preproceso** · Agregación horaria + geometría solar (Spencer / Cooper)
3. **Descomposición** · DIRINT, Erbs y Reindl-2 en paralelo
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
    if summ["has_dewpoint"]: detected_opt.append("Punto de rocío (uso opcional en el DIRINT)")
    elif summ["has_humidity"]: detected_opt.append("Humedad relativa (se convierte a punto de rocío; uso opcional en el DIRINT)")
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
            "**Que usa cada modelo:**\n\n"
            "- **DIRINT**: tabla de coeficientes (Perez et al., 1992) con Kt', angulo cenital, "
            "variabilidad horaria ΔKt' y agua precipitable.\n"
            "- **Erbs**: formula que depende solo de Kt. No requiere agua precipitable.\n"
            "- **Reindl-2**: incorpora la elevacion solar sin(alfa) ademas de Kt."
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

    # ── Consistencia con la referencia del archivo ───────────────────────────
    _rt = st.session_state.ref_table
    if _rt is not None and not _rt.empty:
        st.subheader("Consistencia con el DNI / DHI del archivo")
        st.caption(
            "Cada modelo frente a las columnas DNI y DHI del archivo (media horaria), en las horas con GHI ≥ 10 W/m² y cos θz ≥ 0.20. "
            "Mide la consistencia con esa referencia, no la exactitud: en un archivo IWEC2 el DNI es una partición de la GHI del propio archivo "
            "y el DHI resulta por cierre, es decir, no son mediciones. MBE = modelo − referencia. Sin intervalos de confianza."
        )
        st.dataframe(
            _rt.style.format({"RMSE": "{:.1f}", "MBE": "{:+.1f}", "nRMSE_pct": "{:.1f}", "R2": "{:.3f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )
        st.download_button(
            "⬇ Consistencia con la referencia (CSV)",
            data=_rt.to_csv(index=False).encode("utf-8"),
            file_name="solar_decomp_consistencia_referencia.csv",
            mime="text/csv",
        )
        st.divider()

    # ── Exportar ──────────────────────────────────────────────────────────────
    st.subheader("Exportar resultados")
    with st.expander("Leyenda de columnas y flags de calidad"):
        from reporter import _LEGEND_ROWS
        import pandas as _pd_leg
        st.dataframe(
            _pd_leg.DataFrame(_LEGEND_ROWS, columns=["Columna", "Unidad", "Descripción"]),
            use_container_width=True,
            hide_index=True,
        )
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
            "DNI_erbs", "DHI_erbs", "DNI_reindl2", "DHI_reindl2",
            "Kt", "zenith_deg", "quality_score",
        ]
        show_cols = [c for c in preview_cols if c in df.columns]
        st.dataframe(
            df[show_cols].head(96).style.format(
                {c: "{:.2f}" for c in show_cols if c != "timestamp_start"},
                na_rep="—",
            ),
            use_container_width=True,
        )

# ─────────────────────────────────────────────────────────────────────────────
# Secciones fijas al pie (siempre visibles)
# ─────────────────────────────────────────────────────────────────────────────
st.divider()

with st.expander("Sobre los datos de referencia y la versión 1.1.0"):
    st.markdown(_VALIDATION_MD)

with st.expander("Como citar esta herramienta"):
    st.markdown("**Formato APA**")
    st.markdown(_APA_CITATION)
    st.markdown("**BibTeX**")
    st.code(_BIBTEX_CITATION, language="bibtex")
    st.caption(f"DOI: [{_DOI}]({_DOI_URL})")

with st.expander("Aviso de responsabilidad"):
    st.info(_DISCLAIMER)
