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
_DOI     = "10.5281/zenodo.20262707"
_DOI_URL = f"https://doi.org/{_DOI}"

_APA_CITATION = (
    "Barea, G., & Ganem, C. (2025). *Solar Decomp: GHI to DNI+DHI solar irradiance "
    f"decomposition* [Software]. INAHE-CONICET. Zenodo. {_DOI_URL}"
)

_BIBTEX_CITATION = f"""@software{{barea_ganem_2025_solar_decomp,
  author    = {{Barea, Gustavo and Ganem, Carolina}},
  title     = {{Solar Decomp: GHI to DNI+DHI solar irradiance decomposition}},
  year      = {{2025}},
  publisher = {{Zenodo}},
  doi       = {{{_DOI}}},
  url       = {{{_DOI_URL}}}
}}"""

_VALIDATION_MD = """
**Sitio de referencia:** Córdoba, Argentina (lat −31.4°, lon −64.2°, alt 474 m, UTC−3)
**Datos de referencia:** archivo TMY Córdoba — GHI, DNI y DHI medidos / modelados independientemente
**Período:** año completo (8 760 h) · **N = 3 739 horas diurnas válidas** con DNI referencia > 0

---

### Estadísticas globales — DNI

| Modelo | RMSE (W/m²) | MBE (W/m²) | R² | nRMSE (%) | Total anual (kWh/m²) |
|--------|:-----------:|:----------:|:--:|:---------:|:--------------------:|
| **Referencia** | — | — | — | — | **1 908** |
| DIRINT | 146 | +93 ⚠ | 0.878 | 28.6 | 2 258 (+18 %) |
| Erbs | 87 | −39 | 0.932 | 17.0 | 1 762 (−8 %) |
| **Reindl-2** | **81** | −50 | **0.964** | **15.9** | 1 723 (−10 %) |

### Estadísticas globales — DHI

| Modelo | RMSE (W/m²) | MBE (W/m²) | R² | Total anual (kWh/m²) |
|--------|:-----------:|:----------:|:--:|:--------------------:|
| **Referencia** | — | — | — | **676** |
| DIRINT | 58 | −40 | 0.877 | 523 (−23 %) |
| **Erbs** | **39** | +9 | **0.926** | 706 (+4 %) |
| Reindl-2 | 41 | +24 | 0.922 | 761 (+13 %) |

> **nRMSE** = RMSE / media observada × 100. **MBE** positivo = sobreestimado; negativo = subestimado.

---

### Error relativo mensual — DNI (%)

| Mes | DNI ref (W/m²) | DIRINT | Erbs | Reindl-2 |
|-----|:--------------:|:------:|:----:|:--------:|
| Enero | 494 | +21 % | −5 % | −9 % |
| Febrero | 473 | +20 % | −3 % | −7 % |
| Marzo | 456 | +14 % | −6 % | −9 % |
| Abril | 503 | +21 % | −10 % | −11 % |
| Mayo | 480 | +25 % | −9 % | −8 % |
| Junio | 558 | +25 % | −13 % | −11 % |
| Julio | 494 | +20 % | −11 % | −9 % |
| Agosto | 633 | +17 % | −12 % | −13 % |
| Septiembre | 552 | +13 % | −10 % | −12 % |
| Octubre | 452 | +18 % | −8 % | −11 % |
| Noviembre | 463 | +14 % | −3 % | −9 % |
| Diciembre | 583 | +16 % | −4 % | −9 % |

---

### Interpretación por modelo

**DIRINT** (Perez et al., 1992)
Sobreestima DNI en +14 % a +25 % todos los meses (MBE anual +93 W/m², nRMSE 28.6 %).
Causa: el modelo fue calibrado con climas templados de EE.UU. y Europa que presentan mayor variabilidad de nubosidad (ΔKt' alto). En climas de cielo claro persistente como el centro-oeste de Argentina, ΔKt' es sistemáticamente bajo, forzando a DIRINT hacia los bins de "baja variabilidad" que asignan valores Kn elevados. Resultado: sobreestimación estructural del componente directo. **No se recomienda como modelo primario para climas semiáridos y áridos del interior argentino.**

**Erbs** (Erbs et al., 1982)
Error relativo en DNI: −3 % a −13 % según el mes. Error en DHI prácticamente neutro a lo largo del año (MBE anual +9 W/m²). Es el modelo **más preciso para DHI** (RMSE 39 W/m², R² = 0.926). Adecuado para aplicaciones donde la irradiancia difusa es determinante: simulación de iluminación natural, diseño de envolventes, sistemas de concentración solar.

**Reindl-2** (Reindl et al., 1990)
Mejor correlación para DNI (R² = 0.964) y el menor nRMSE (15.9 %). Incluye el ángulo de elevación solar sin(α) como variable predictora, lo que mejora el desempeño para ángulos cenitales grandes (amanecer / atardecer) y latitudes altas. Tendencia a sobreestimar DHI (+7 % a +15 %). **Recomendado como modelo primario** para el clima continental semiárido de Argentina (Córdoba, Cuyo, NOA).

---

### Conclusiones

1. **La geometría solar** (Spencer, 1971; Cooper, 1969) reproduce el cos(Z) del archivo de referencia con RMSE = 0.005 (R² = 0.9999) al utilizar los parámetros correctos del sitio.
2. **Erbs y Reindl-2** se encuentran dentro de los rangos publicados en la literatura especializada: RMSE_DNI = 80–90 W/m², R²_DNI > 0.93 (Besharat et al., 2013; Ineichen, 2008; Engerer & Mills, 2015).
3. **DIRINT sobreestima sistemáticamente** en climas de cielo persistentemente claro, consistente con reportes previos de sesgo positivo en el hemisferio sur (Vindel & Polo, 2014).
4. **Recomendación operativa:** usar **Reindl-2 como modelo primario** para sitios del interior argentino y **Erbs como verificación cruzada**. DIRINT puede utilizarse en climas con alta variabilidad de nubosidad (Buenos Aires, litoral, Patagonia costera).

---

### Referencias

- Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. *ASHRAE Transactions*, 98(1), 354–369.
- Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation. *Solar Energy*, 28(4), 293–302. https://doi.org/10.1016/0038-092X(82)90302-4
- Reindl, D.T., Beckman, W.A., & Duffie, J.A. (1990). Diffuse fraction correlations. *Solar Energy*, 45(1), 1–7. https://doi.org/10.1016/0038-092X(90)90060-P
- Spencer, J.W. (1971). Fourier series representation of the position of the sun. *Search*, 2(5), 172.
- Cooper, P.I. (1969). The absorption of radiation in solar stills. *Solar Energy*, 12(3), 333–346.
- Kasten, F., & Young, A.T. (1989). Revised optical air mass tables and approximation formula. *Applied Optics*, 28(22), 4735–4738.
- Besharat, F., Dehghan, A.A., & Faghih, A.R. (2013). Empirical models for estimating global solar radiation: A review and case study. *Renewable and Sustainable Energy Reviews*, 21, 798–821. https://doi.org/10.1016/j.rser.2012.12.043
- Ineichen, P. (2008). Comparison and validation of three global-to-beam irradiance models against ground measurements. *Solar Energy*, 82(6), 501–512. https://doi.org/10.1016/j.solener.2007.12.006
- Engerer, N.A., & Mills, F.P. (2015). Validating nine clear sky radiation models in Australia. *Solar Energy*, 120, 9–24. https://doi.org/10.1016/j.solener.2015.06.044
- Vindel, J.M., & Polo, J. (2014). Intermittency and variability of solar irradiance and improvements in its modeling. *Solar Energy*, 107, 60–73. https://doi.org/10.1016/j.solener.2014.05.028
- Leckner, B. (1978). The spectral distribution of solar radiation at the Earth's surface. *Solar Energy*, 20(2), 143–150.
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

    if st.button("Resetear todo", use_container_width=True):
        for k in ["loaded", "df_hourly", "df_result", "report", "site_info"]:
            st.session_state[k] = None
        st.rerun()

    # ── 2. Información del sitio ──────────────────────────────────────────────
    st.subheader("2 · Sitio")
    lat = st.number_input("Latitud [°N]",        value=-34.6,  min_value=-90.0,  max_value=90.0,  step=0.01, format="%.4f")
    lon = st.number_input("Longitud [°E]",        value=-58.4,  min_value=-180.0, max_value=180.0, step=0.01, format="%.4f")
    alt = st.number_input("Altitud [m s.n.m.]",   value=25.0,   min_value=0.0,    max_value=5000.0, step=10.0, format="%.0f",
                          help="Usada para estimar presión atmosférica cuando no hay datos medidos.")
    tz  = st.number_input("Zona horaria [UTC+]",  value=-3.0,   min_value=-12.0,  max_value=14.0,  step=0.5,  format="%.1f")

    # ── 3. Modelos ────────────────────────────────────────────────────────────
    st.subheader("3 · Modelos")
    st.info(
        "El programa calcula los **3 modelos en paralelo**. "
        "Los resultados de cada uno se exportan en columnas separadas.",
        icon="ℹ️",
    )
    st.markdown(
        "- **Reindl-2** (Reindl et al., 1990): incorpora elevación solar sin(α). "
        "Recomendado para climas áridos/semiáridos del interior argentino "
        "(mejor R² = 0.964, nRMSE = 15.9 %).\n"
        "- **Erbs** (Erbs et al., 1982): polinomio Kd(Kt). "
        "Más preciso para DHI (RMSE = 39 W/m²). Robusto sin datos de temperatura.\n"
        "- **DIRINT** (Perez et al., 1992): tabla 3D [W × ΔKt' × Kt']. "
        "Mejor desempeño en climas variables con alta nubosidad "
        "(Buenos Aires, litoral, Patagonia costera). "
        "Tiende a sobreestimar DNI en cielos persistentemente claros."
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

    preserve_existing = st.checkbox(
        "No recalcular filas con DNI/DHI existentes",
        value=True,
        help=(
            "Si el archivo ya contiene columnas DNI y/o DHI con datos, "
            "se conservan esos valores y solo se calculan los faltantes."
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
            df_dec = run_decomposition(df_hourly, primary=primary_model, min_cosz=min_cosz)
        except Exception as e:
            st.error(f"Error en descomposicion: {e}")
            st.error(traceback.format_exc())
            st.stop()

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
            "**Cuando elegir cada modelo:**\n\n"
            "- **DIRINT**: mejor opcion para datos medidos con variabilidad nube/sol. "
            "Usa tabla 3D que incorpora vapor de agua y variabilidad horaria de Kt'.\n"
            "- **Erbs**: baseline simple y robusto. No requiere vapor de agua. "
            "Recomendado cuando los datos son escasos o el clima es muy nublado (Kt < 0.4).\n"
            "- **Reindl-2**: alternativa empirica que incorpora elevacion solar sin(alfa). "
            "Util como segundo punto de comparacion con Erbs."
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

with st.expander("Validacion cientifica del programa"):
    st.markdown(_VALIDATION_MD)

with st.expander("Como citar esta herramienta"):
    st.markdown("**Formato APA**")
    st.markdown(_APA_CITATION)
    st.markdown("**BibTeX**")
    st.code(_BIBTEX_CITATION, language="bibtex")
    st.caption(f"DOI: [{_DOI}]({_DOI_URL})")

with st.expander("Aviso de responsabilidad"):
    st.info(_DISCLAIMER)
