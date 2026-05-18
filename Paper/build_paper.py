"""
build_paper.py — Genera paper_draft.docx y tables.xlsx en Paper/
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

ROOT    = Path(__file__).resolve().parent
FIG_DIR = ROOT / "figuras"
DATA    = ROOT / "resultados_validacion" / "validacion_ciudades.xlsx"

# ── helpers ────────────────────────────────────────────────────────────────────
def _set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)

def _bold_row(row):
    for cell in row.cells:
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True

def add_figure(doc, img_path, caption, width=6.0):
    doc.add_picture(str(img_path), width=Inches(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph(caption)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.runs[0].italic = True
    p.runs[0].font.size = Pt(9)
    doc.add_paragraph()

def heading(doc, text, level=1):
    doc.add_heading(text, level=level)

def body(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)
    return p

def eq(doc, text):
    p = doc.add_paragraph(text)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)

# ── Table data ─────────────────────────────────────────────────────────────────
df_cities  = pd.read_excel(DATA, sheet_name="Por_Ciudad")
df_monthly = pd.read_excel(DATA, sheet_name="Por_Mes")
df_best    = pd.read_excel(DATA, sheet_name="Mejor_modelo")

import sys; sys.path.insert(0, str(ROOT))
from generate_figures import _get_climate

# Table S1
EPW_DIR = ROOT.parent / "EPWs"
from epw_parser import parse_epw
seen = set(); s1_rows = []
for p in sorted(EPW_DIR.glob("*.EPW")) + sorted(EPW_DIR.glob("*.epw")):
    meta, df_raw = parse_epw(p)
    city = meta["city"]
    if city in seen: continue
    seen.add(city)
    koppen, iram = _get_climate(city)
    s1_rows.append([meta["wmo"], city.replace("-AERO","").replace("-"," ").title(),
                    abs(meta["lat"]), abs(meta["lon"]), int(meta["elevation"]),
                    int(meta["tz"]), meta["source"], koppen, iram,
                    int((df_raw["GHI"] >= 10).sum())])
df_s1 = pd.DataFrame(s1_rows, columns=["WMO","City","Lat (°S)","Lon (°W)",
                     "Elev (m)","TZ","Source","Köppen","IRAM","N daytime h"])
df_s1 = df_s1.sort_values("Lat (°S)").reset_index(drop=True)

# Table 2 — global stats
t2_data = [
    ["DIRINT",   "0.436 ± 0.173", "186.8", "+97.0", "58.5", "0.787 ± 0.062", "51.7", "−30.0"],
    ["Erbs",     "0.904 ± 0.035",  "77.2", "−18.0", "24.0", "0.978 ± 0.015", "16.3",  "+2.7"],
    ["Reindl-2", "0.923 ± 0.026",  "69.5", "−19.5", "21.5", "0.960 ± 0.027", "21.7", "+12.0"],
]
t2_headers = ["Model","DNI R²","DNI RMSE\n(W/m²)","DNI MBE\n(W/m²)",
              "DNI nRMSE\n(%)","DHI R²","DHI RMSE\n(W/m²)","DHI MBE\n(W/m²)"]

# Table 3 — by Köppen
t3_data = [
    ["Cfa","Humid subtropical","14","0.942 ± 0.010","20.2","−17.9"],
    ["Aw", "Tropical savanna","3", "0.939 ± 0.006","23.7","−12.7"],
    ["BSh","Hot steppe",       "2", "0.923 ± 0.010","26.2","−14.3"],
    ["BSk","Cold steppe",      "14","0.918 ± 0.026","21.5","−19.6"],
    ["BWk","Cold desert",      "5", "0.902 ± 0.023","20.2","−26.8"],
    ["Cfb","Oceanic temperate","1", "0.901",         "23.6","−18.3"],
    ["BWh","Hot desert",       "1", "0.897",         "23.8","−13.7"],
    ["ET", "Tundra/polar",     "1", "0.868",         "31.4","−18.7"],
]
t3_headers = ["Köppen","Description","N","R²","nRMSE (%)","MBE (W/m²)"]

# Table 1 — climate distribution
t1_data = [
    ["Aw","Tropical savanna","3","I"],
    ["BSh","Hot steppe","2","I–II"],
    ["BSk","Cold steppe","14","II–V"],
    ["BWh","Hot desert","1","III"],
    ["BWk","Cold desert","5","III–IV"],
    ["Cfa","Humid subtropical","14","I–III"],
    ["Cfb","Oceanic temperate","1","V"],
    ["ET","Tundra / polar","1","VI"],
]
t1_headers = ["Köppen","Description","N cities","IRAM zones"]


def build_word():
    doc = Document()

    # Margins
    for section in doc.sections:
        section.top_margin    = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin   = Inches(1.2)
        section.right_margin  = Inches(1.2)

    # Default style
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)

    # ── Title ──────────────────────────────────────────────────────────────────
    t = doc.add_heading("Decomposition of Global Horizontal Irradiance into Direct Normal and Diffuse Horizontal Irradiance for Argentine Climates: A Systematic Validation of Three Empirical Models Using TMY Data from 41 Cities", 0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph("Gustavo Barea Paci¹, Carolina Ganem¹")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.runs[0].bold = True

    p = doc.add_paragraph("¹ Instituto de Ambiente, Hábitat y Energía (INAHE-CONICET), Mendoza, Argentina.")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.runs[0].font.size = Pt(9)

    p = doc.add_paragraph("Proposed journal: Solar Energy / Renewable Energy / Energy and Buildings")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.runs[0].italic = True; p.runs[0].font.size = Pt(9)

    doc.add_paragraph("Keywords: solar irradiance decomposition; DIRINT; Erbs model; Reindl-2; DNI; DHI; Argentina; Köppen-Geiger; IRAM 11603; building energy simulation").runs[0].font.size = Pt(9)
    doc.add_paragraph()

    # ── Abstract ───────────────────────────────────────────────────────────────
    heading(doc, "Abstract", 1)
    body(doc, "Decomposition models that estimate direct normal irradiance (DNI) and diffuse horizontal irradiance (DHI) from global horizontal irradiance (GHI) are essential tools for building energy simulation and solar resource assessment in regions where only GHI is routinely measured. This study presents a systematic validation of three widely used decomposition models — DIRINT (Perez et al., 1992), Erbs (Erbs et al., 1982), and Reindl-2 (Reindl et al., 1990) — against Typical Meteorological Year (TMY) reference data from 41 Argentine cities spanning latitudes 22.6°S to 54.8°S and eight Köppen-Geiger climate classes. Results show that the Reindl-2 model achieves the best DNI estimation in 39 of 41 cities (R² = 0.923 ± 0.026; nRMSE = 21.5%; MBE = −19.5 W/m²), while Erbs yields the lowest DHI errors (R² = 0.978 ± 0.015; RMSE = 16.3 W/m²). DIRINT systematically overestimates DNI (MBE = +97.0 W/m²) in persistently clear-sky climates, limiting its applicability across most of Argentina's territory. Model performance correlates negatively with the mean clearness index (Kt), indicating that greater atmospheric variability improves decomposition accuracy. The Solar Decomp tool and all validation scripts are publicly available at https://github.com/gbarea-INAHE/solar_decomp.")

    # ── 1. Introduction ────────────────────────────────────────────────────────
    heading(doc, "1. Introduction", 1)
    body(doc, "Accurate knowledge of the solar radiation components — global horizontal irradiance (GHI), direct normal irradiance (DNI), and diffuse horizontal irradiance (DHI) — is fundamental for building energy simulation, solar collector design, and urban thermal comfort assessment. However, routine meteorological networks in Argentina, as in most of Latin America, measure only GHI. DNI and DHI are rarely available from direct measurements, creating a systematic gap between the data collected by weather stations and the multi-component radiation inputs required by simulation software such as EnergyPlus, DesignBuilder, or TRNSYS.")
    body(doc, "Typical Meteorological Year (TMY) files in EnergyPlus Weather (EPW) format — the standard input for building energy simulation — include DNI and DHI values, but these are generally estimated from GHI using decomposition models or satellite-derived products rather than direct measurements (Wilcox and Marion, 2008; Sengupta et al., 2018). Understanding the accuracy of different decomposition approaches across the diverse climatic regions of Argentina is therefore directly relevant to the quality of energy simulation results.")
    body(doc, "The three models evaluated in this study represent the most widely cited approaches in the literature: DIRINT (Perez et al., 1992), which uses a three-dimensional lookup table indexed by precipitable water, modified clearness index Kt', and hourly Kt' variability; Erbs (Erbs et al., 1982), which estimates the diffuse fraction as a piecewise polynomial of Kt; and Reindl-2 (Reindl et al., 1990), which extends Erbs by incorporating the solar elevation angle sin(α).")
    body(doc, "Previous validation studies have been conducted primarily for North American, European, and East Asian climates (Ineichen, 2008; Gueymard and Ruiz-Arias, 2016). Systematic validation for South American climates, particularly across the full latitudinal and climatic diversity of Argentina — from subtropical NOA (22°S) to sub-Antarctic Ushuaia (54°S) — remains limited. This study addresses that gap.")
    body(doc, "The specific objectives are: (1) to validate DIRINT, Erbs, and Reindl-2 against TMY data for 41 Argentine cities; (2) to identify the optimal model for each Köppen-Geiger climate class and IRAM 11603 thermal zone; (3) to quantify the relationship between model performance and climate aridity; and (4) to provide model selection guidelines for practitioners.")

    # ── 2. Data and Methods ────────────────────────────────────────────────────
    heading(doc, "2. Data and Methods", 1)
    heading(doc, "2.1 Study Sites", 2)
    body(doc, "The validation dataset comprises 41 meteorological stations distributed across Argentina (22.6°S–54.8°S, 53.9°W–73.0°W), covering eight Köppen-Geiger climate classes and all six IRAM 11603 thermal zones (Table 1). Elevation ranges from 6 m (Buenos Aires Aeroparque) to 1,425 m (Malargüe). The full list of stations is provided in Table S1.")

    # Table 1
    body(doc, "Table 1. Distribution of study sites by Köppen-Geiger climate class and IRAM 11603 thermal zone.")
    tbl = doc.add_table(rows=1 + len(t1_data), cols=len(t1_headers))
    tbl.style = "Table Grid"
    for j, h in enumerate(t1_headers):
        c = tbl.rows[0].cells[j]; c.text = h
        _set_cell_bg(c, "4472C4")
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        c.paragraphs[0].runs[0].bold = True
    for i, row_d in enumerate(t1_data):
        for j, val in enumerate(row_d):
            tbl.rows[i+1].cells[j].text = val
    doc.add_paragraph()

    heading(doc, "2.2 Reference Data", 2)
    body(doc, "TMY data in EPW format were obtained from the IWEC2 (International Weather for Energy Calculations, version 2) dataset (Thevenard and Brunger, 2002), compiled from WMO observation records covering the period 1984–2008. EPW files provide hourly values of GHI, DNI, and DHI in Wh/m². It must be noted that EPW reference DNI and DHI values are themselves model-derived in most cases, rather than direct pyrheliometer measurements. This circularity imposes a methodological limitation discussed in Section 4.3.")

    heading(doc, "2.3 Solar Geometry", 2)
    body(doc, "Solar position was computed using Spencer (1971) for the equation of time and Cooper (1969) for solar declination. The average cosine of the zenith angle over each hourly interval was computed analytically by integrating cos(Z) over ±7.5° of hour angle. Air mass was estimated using Kasten and Young (1989); precipitable water from temperature and pressure following Leckner (1978).")
    eq(doc, "δ = 23.45° · sin(360°·(284 + DOY)/365)")
    eq(doc, "EoT = 9.87·sin(2B) − 7.53·cos(B) − 1.5·sin(B)  [min],  B = 360°·(DOY−81)/364")

    heading(doc, "2.4 Decomposition Models", 2)
    body(doc, "DIRINT (Perez et al., 1992) estimates the beam transmittance Kn = DNI/G0n using a 3D lookup table. The modified clearness index is: Kt' = Kt / [1.031·exp(−1.4/(0.9 + 9.4/AM)) + 0.1].")
    body(doc, "Erbs (Erbs et al., 1982) estimates the diffuse fraction Kd = DHI/GHI as a piecewise polynomial: Kd = 1 − 0.09·Kt (Kt ≤ 0.22); Kd = 0.9511 − 0.1604·Kt + 4.388·Kt² − 16.638·Kt³ + 12.336·Kt⁴ (0.22 < Kt ≤ 0.80); Kd = 0.165 (Kt > 0.80).")
    body(doc, "Reindl-2 (Reindl et al., 1990) incorporates solar elevation sin(α): Kd = 1 − 0.232·Kt (Kt ≤ 0.30); Kd = 1.329 − 1.716·Kt + (0.267 − 0.357·sin α) (0.30 < Kt ≤ 0.78); Kd = 0.426·Kt − 0.256·sin α + 0.118 (Kt > 0.78).")

    heading(doc, "2.5 Validation Metrics", 2)
    body(doc, "Performance was assessed using RMSE, MBE (positive = overestimate), R², and nRMSE (%) on all daytime hours (GHI ≥ 10 W/m²) for each city–model combination. Total dataset: 179,686 hourly observations × 3 models = 539,058 model evaluations.")

    # ── 3. Results ─────────────────────────────────────────────────────────────
    heading(doc, "3. Results", 1)
    heading(doc, "3.1 Global Performance", 2)
    body(doc, "Table 2 summarizes the mean validation statistics across all 41 cities. Reindl-2 achieves the best overall DNI accuracy, with R² = 0.923 ± 0.026 and nRMSE = 21.5%. DIRINT exhibits severe systematic overestimation (MBE = +97.0 W/m²). For DHI, Erbs performs marginally better (RMSE = 16.3 vs. 21.7 W/m²).")

    body(doc, "Table 2. Mean validation statistics for DNI and DHI across 41 Argentine cities (mean ± std over cities). Bold: best value per column.")
    tbl2 = doc.add_table(rows=1 + len(t2_data), cols=len(t2_headers))
    tbl2.style = "Table Grid"
    for j, h in enumerate(t2_headers):
        c = tbl2.rows[0].cells[j]; c.text = h
        _set_cell_bg(c, "4472C4")
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        c.paragraphs[0].runs[0].bold = True; c.paragraphs[0].runs[0].font.size = Pt(9)
    best_cols = {1, 2, 4, 5, 6}  # cols where lower/higher is best
    for i, row_d in enumerate(t2_data):
        for j, val in enumerate(row_d):
            c = tbl2.rows[i+1].cells[j]; c.text = val
            c.paragraphs[0].runs[0].font.size = Pt(9)
            if i == 2 and j in best_cols:  # Reindl2 best DNI
                c.paragraphs[0].runs[0].bold = True
            if i == 1 and j in {5, 6}:    # Erbs best DHI
                c.paragraphs[0].runs[0].bold = True
        if i == 0: _set_cell_bg(tbl2.rows[i+1].cells[0], "FCE4D6")
    doc.add_paragraph()

    add_figure(doc, FIG_DIR/"Fig7_Taylor_DNI.png",
               "Figure 7. Taylor Diagram for DNI. Each point represents one city. DIRINT scatters far from the reference (high angle, high σ); Erbs and Reindl-2 cluster near the reference point (R > 0.95).", width=4.5)

    heading(doc, "3.2 City-Level Performance", 2)
    body(doc, "Reindl-2 ranked as the best model for DNI in 39 of 41 cities (95.1%). Best performance: General Pico, La Pampa (R² = 0.964, nRMSE = 17.1%). Weakest: Ushuaia (R² = 0.868, nRMSE = 31.4%) and Río Gallegos (R² = 0.869).")

    add_figure(doc, FIG_DIR/"Fig1_mapa_mejor_modelo.png",
               "Figure 1. Best DNI decomposition model by city. Marker shape indicates model (circle = Reindl-2, square = Erbs); colour indicates R² value. Reindl-2 dominates across 95% of Argentine territory.", width=4.0)

    add_figure(doc, FIG_DIR/"Fig4_heatmap_R2_DNI.png",
               "Figure 4. R² DNI heatmap by city and model (ordered by Reindl-2 performance). Green = high accuracy; red = low accuracy.", width=5.5)

    add_figure(doc, FIG_DIR/"Fig5_nRMSE_por_ciudad.png",
               "Figure 5. DNI nRMSE (%) by city and model. Cities ordered by Reindl-2 error (highest to lowest). DIRINT errors consistently exceed 50% in most cities.", width=6.5)

    heading(doc, "3.3 Performance by Climate Zone", 2)
    body(doc, "Table 3 summarises Reindl-2 DNI performance by Köppen-Geiger class. Humid subtropical (Cfa) and tropical savanna (Aw) climates yield the highest accuracy, while polar climates (ET) show the largest relative errors.")

    body(doc, "Table 3. Mean Reindl-2 DNI performance by Köppen-Geiger class (ordered by R²).")
    tbl3 = doc.add_table(rows=1 + len(t3_data), cols=len(t3_headers))
    tbl3.style = "Table Grid"
    for j, h in enumerate(t3_headers):
        c = tbl3.rows[0].cells[j]; c.text = h
        _set_cell_bg(c, "70AD47")
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        c.paragraphs[0].runs[0].bold = True
    for i, row_d in enumerate(t3_data):
        for j, val in enumerate(row_d):
            tbl3.rows[i+1].cells[j].text = val
    doc.add_paragraph()

    add_figure(doc, FIG_DIR/"Fig10_nRMSE_Koppen.png",
               "Figure 10. nRMSE DNI by Köppen-Geiger zone for Reindl-2 (left) and Erbs (right). BSh (hot steppe) shows the highest variability; BWk (cold desert) and Cfa (humid subtropical) show lowest median errors.", width=6.5)

    heading(doc, "3.4 Scatter Analysis", 2)
    add_figure(doc, FIG_DIR/"Fig2_scatter_DNI.png",
               "Figure 2. Scatter plot (hexbin density) of calculated vs. reference EPW DNI for all 41 cities. DIRINT shows a strong overestimation cloud above the 1:1 line; Erbs and Reindl-2 are tightly distributed along it.", width=6.5)
    add_figure(doc, FIG_DIR/"Fig3_scatter_DHI.png",
               "Figure 3. Scatter plot of calculated vs. reference EPW DHI. Erbs and Reindl-2 show near-perfect alignment; DIRINT underestimates DHI systematically.", width=6.5)

    heading(doc, "3.5 Seasonal Bias Patterns", 2)
    body(doc, "The monthly MBE heatmap (Figure 8) reveals systematic seasonal patterns. Northern Argentina shows near-zero MBE throughout the year. Central Argentina (30°–40°S) presents moderate negative MBE in winter (JJA), reaching −40 to −60 W/m² in June–July for Córdoba, Mendoza, and San Luis. Patagonian sites show large and variable MBE throughout the year.")
    add_figure(doc, FIG_DIR/"Fig8_MBE_mensual.png",
               "Figure 8. Monthly MBE (W/m²) heatmap for the best model per city, ordered North→South. Blue = underestimation; red = overestimation.", width=6.5)

    heading(doc, "3.6 Model Performance vs. Climate Aridity", 2)
    body(doc, "Figure 9 shows R² vs. mean annual clearness index (Kt) across 41 cities. A negative trend (slope = −0.08 per unit Kt) confirms that accuracy decreases as climates become more arid. Notable exceptions: General Pico (BSk, best R² despite moderate Kt) and Andalgalá (BWk, where Erbs slightly outperforms Reindl-2).")
    add_figure(doc, FIG_DIR/"Fig9_R2_vs_Kt.png",
               "Figure 9. Reindl-2 R² (DNI) vs. mean annual clearness index Kt by Köppen class. Negative trend (dashed) indicates higher aridity degrades model performance.", width=6.0)

    add_figure(doc, FIG_DIR/"Fig6_MBE_boxplot.png",
               "Figure 6. MBE distribution for DNI across 41 cities. DIRINT (red) strongly overestimates; Erbs and Reindl-2 show small negative biases.", width=4.5)

    # ── 4. Discussion ──────────────────────────────────────────────────────────
    heading(doc, "4. Discussion", 1)
    heading(doc, "4.1 Reindl-2 as the Recommended Model for Argentina", 2)
    body(doc, "The consistent superiority of Reindl-2 across 95% of Argentine cities constitutes robust evidence for its adoption as the default decomposition model. The incorporation of sin(α) provides a physically motivated correction for the geometric effect of low sun angles — particularly relevant in Patagonia and during winter in central Argentina. The modest but consistent advantage over Erbs (ΔR² ≈ 0.019 for DNI) is practically meaningful: for a typical Buenos Aires site (annual GHI ≈ 1,600 kWh/m²), the RMSE reduction of 7.7 W/m² propagates to reduced uncertainty in annual solar gains. For DHI-sensitive applications (glazing overheating), Erbs may be preferable.")

    heading(doc, "4.2 DIRINT Structural Limitations", 2)
    body(doc, "DIRINT's substantially lower performance (mean R² = 0.436 vs. 0.904–0.923) reflects a structural limitation: in persistently clear-sky climates (typical of Argentina's arid west and northwest), low ΔKt' values force the model into low-variability bins with inflated Kn values, causing systematic overestimation (MBE = +97.0 W/m²). This is consistent with Ineichen (2008) and Gueymard and Ruiz-Arias (2016), who noted DIRINT was calibrated on highly variable, cloud-rich climates. For users where DIRINT is currently the default (e.g., pvlib-python), this study provides evidence that Reindl-2 should be preferred for Argentine conditions.")

    heading(doc, "4.3 Methodological Limitations", 2)
    body(doc, "(1) Reference data circularity: IWEC2 EPW reference DNI/DHI values are model-derived, not measured by pyrheliometers. Erbs-based models may show artificially high agreement. Future work should validate against measured data from SMN and CONICET's radiometric network. (2) Single-year TMY: interannual variability (especially ENSO-affected northern Argentina) is not captured. (3) Sub-hourly dynamics: all models operate at hourly resolution; cloud enhancement events are not resolved. (4) Spatial representativeness: stations are predominantly at airports.")

    # ── 5. Conclusions ─────────────────────────────────────────────────────────
    heading(doc, "5. Conclusions", 1)
    body(doc, "This study presents the first systematic validation of three GHI decomposition models against TMY data from 41 Argentine cities spanning 32° of latitude and eight Köppen-Geiger climate classes. Main conclusions:")
    for txt in [
        "1. Reindl-2 is the optimal model for DNI estimation across 95.1% of Argentine cities (R² = 0.923 ± 0.026, nRMSE = 21.5%). Its sin(α) term provides physically consistent improvement under low-sun conditions.",
        "2. Erbs is preferred for DHI (R² = 0.978 ± 0.015, RMSE = 16.3 W/m²) and as a robust fallback when temperature data are unavailable.",
        "3. DIRINT systematically overestimates DNI (MBE = +97.0 W/m²) across most Argentine climates and is not recommended as a default model for Argentine applications.",
        "4. Model performance correlates negatively with climate aridity (slope = −0.08 per unit Kt): humid subtropical (Cfa) and tropical (Aw) climates yield the highest accuracy.",
        "5. Seasonal bias analysis reveals systematic winter underestimation of DNI in central Argentina (30°–40°S), suggesting future recalibration efforts should target this region.",
    ]:
        p = doc.add_paragraph(txt, style="List Bullet")
        p.paragraph_format.space_after = Pt(3)

    # ── Software ───────────────────────────────────────────────────────────────
    heading(doc, "Software Availability", 1)
    body(doc, "Solar Decomp is freely available at: https://github.com/gbarea-INAHE/solar_decomp (DOI: 10.5281/zenodo.20262707). Validation scripts and figure generation code are included in the Paper/ subdirectory to ensure full reproducibility.")

    # ── References ─────────────────────────────────────────────────────────────
    heading(doc, "References", 1)
    refs = [
        "Cooper, P.I. (1969). The absorption of radiation in solar stills. Solar Energy, 12(3), 333–346.",
        "Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction. Solar Energy, 28(4), 293–302.",
        "Gueymard, C.A., & Ruiz-Arias, J.A. (2016). Extensive worldwide validation of direct irradiance predictions. Solar Energy, 128, 1–30.",
        "Ineichen, P. (2008). Comparison and validation of three global-to-beam irradiance models. Solar Energy, 82(6), 501–512.",
        "Kasten, F., & Young, A.T. (1989). Revised optical air mass tables. Applied Optics, 28(22), 4735–4738.",
        "Leckner, B. (1978). The spectral distribution of solar radiation at the Earth's surface. Solar Energy, 20(2), 143–150.",
        "Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. ASHRAE Transactions, 98(1), 354–369.",
        "Reindl, D.T., Beckman, W.A., & Duffie, J.A. (1990). Diffuse fraction correlations. Solar Energy, 45(1), 1–7.",
        "Sengupta, M. et al. (2018). The National Solar Radiation Data Base (NSRDB). Renewable and Sustainable Energy Reviews, 89, 51–60.",
        "Spencer, J.W. (1971). Fourier series representation of the position of the sun. Search, 2(5), 172.",
        "Thevenard, D., & Brunger, A. (2002). Development of typical weather years for international locations. ASHRAE Transactions, 108(2), 376–383.",
        "Wilcox, S., & Marion, W. (2008). Users Manual for TMY3 Data Sets. NREL/TP-581-43156.",
    ]
    for r in refs:
        p = doc.add_paragraph(r, style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        p.runs[0].font.size = Pt(9)

    # ── Supplementary: Table S1 ───────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Supplementary Material", 1)
    heading(doc, "Table S1. Study sites — geographic and climate data", 2)
    body(doc, f"Total: {len(df_s1)} cities, {df_s1['N daytime h'].sum():,} daytime hours (GHI ≥ 10 W/m²).")

    cols_s1 = df_s1.columns.tolist()
    tbl_s1  = doc.add_table(rows=1 + len(df_s1), cols=len(cols_s1))
    tbl_s1.style = "Table Grid"
    for j, h in enumerate(cols_s1):
        c = tbl_s1.rows[0].cells[j]; c.text = h
        _set_cell_bg(c, "595959")
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        c.paragraphs[0].runs[0].bold = True; c.paragraphs[0].runs[0].font.size = Pt(7)
    for i, row in df_s1.iterrows():
        for j, val in enumerate(row):
            c = tbl_s1.rows[i+1].cells[j]; c.text = str(val)
            c.paragraphs[0].runs[0].font.size = Pt(7)
            if i % 2 == 0:
                _set_cell_bg(c, "F2F2F2")

    out = ROOT / "paper_draft.docx"
    doc.save(str(out))
    print(f"Word saved: {out}")


def build_excel():
    wb = openpyxl.Workbook()

    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    green_fill  = PatternFill("solid", fgColor="70AD47")
    alt_fill    = PatternFill("solid", fgColor="EEF3FB")
    bold_font   = Font(bold=True, size=10)
    thin        = Side(style="thin", color="BFBFBF")
    border      = Border(left=thin, right=thin, top=thin, bottom=thin)

    def write_table(ws, headers, data, hdr_fill=header_fill, start_row=1):
        for j, h in enumerate(headers, 1):
            c = ws.cell(start_row, j, h)
            c.font = header_font; c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center", wrap_text=True)
            c.border = border
        for i, row in enumerate(data, start_row + 1):
            for j, val in enumerate(row, 1):
                c = ws.cell(i, j, val)
                c.alignment = Alignment(horizontal="center")
                c.border = border
                if i % 2 == 0: c.fill = alt_fill
        ws.row_dimensions[start_row].height = 30

    # Sheet 1 — Table 1
    ws1 = wb.active; ws1.title = "Table1_Climate_Distribution"
    ws1["A1"] = "Table 1. Distribution of study sites by Köppen-Geiger class and IRAM 11603 zone."
    ws1["A1"].font = Font(bold=True, size=11)
    ws1.merge_cells("A1:D1")
    write_table(ws1, t1_headers, t1_data, start_row=2)
    for col, w in zip("ABCD", [12,22,10,14]): ws1.column_dimensions[col].width = w

    # Sheet 2 — Table 2
    ws2 = wb.create_sheet("Table2_Global_Stats")
    ws2["A1"] = "Table 2. Mean validation statistics for DNI and DHI across 41 Argentine cities (mean ± std)."
    ws2["A1"].font = Font(bold=True, size=11)
    ws2.merge_cells("A1:H1")
    h2 = ["Model","DNI R²","DNI RMSE (W/m²)","DNI MBE (W/m²)","DNI nRMSE (%)","DHI R²","DHI RMSE (W/m²)","DHI MBE (W/m²)"]
    write_table(ws2, h2, t2_data, start_row=2)
    for col, w in zip("ABCDEFGH", [10,18,18,18,16,18,18,16]): ws2.column_dimensions[col].width = w
    # Highlight best values
    best_cells = [("C4","E4"),("F3","G3")]  # Reindl2 DNI, Erbs DHI
    for ref in ["C4","E4","F3","G3"]:
        ws2[ref].font = Font(bold=True, size=10)

    # Sheet 3 — Table 3
    ws3 = wb.create_sheet("Table3_By_Koppen")
    ws3["A1"] = "Table 3. Mean Reindl-2 DNI performance by Köppen-Geiger class."
    ws3["A1"].font = Font(bold=True, size=11)
    ws3.merge_cells("A1:F1")
    write_table(ws3, t3_headers, t3_data, hdr_fill=PatternFill("solid", fgColor="70AD47"), start_row=2)
    for col, w in zip("ABCDEF", [8,22,6,18,14,14]): ws3.column_dimensions[col].width = w

    # Sheet 4 — Table S1
    ws4 = wb.create_sheet("TableS1_Sites")
    ws4["A1"] = f"Table S1. Study sites — 41 cities, {df_s1['N daytime h'].sum():,} daytime hours."
    ws4["A1"].font = Font(bold=True, size=11)
    ws4.merge_cells(f"A1:{chr(64+len(df_s1.columns))}1")
    write_table(ws4, df_s1.columns.tolist(), df_s1.values.tolist(),
                hdr_fill=PatternFill("solid", fgColor="595959"), start_row=2)
    for col, w in zip("ABCDEFGHIJ", [8,24,8,8,8,6,10,8,6,14]): ws4.column_dimensions[col].width = w

    # Sheet 5 — Full city stats
    ws5 = wb.create_sheet("City_Stats_Full")
    write_table(ws5, df_cities.columns.tolist(), df_cities.values.tolist())
    ws5["A1"].value = None
    for j, h in enumerate(df_cities.columns, 1):
        c = ws5.cell(1, j, h); c.font = header_font; c.fill = header_fill
        c.alignment = Alignment(horizontal="center"); c.border = border

    out = ROOT / "resultados_validacion" / "paper_tables.xlsx"
    wb.save(str(out))
    print(f"Excel saved: {out}")


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    build_word()
    build_excel()
    print("Done.")
