"""
reporter.py — Generación de reporte de calidad y exportación de resultados.

Produce:
  · Reporte de calidad (dict → JSON / texto)
  · DataFrame de exportación (CSV / Excel)
  · Estadísticas comparativas DIRINT vs Erbs
"""
from __future__ import annotations

import io
import json
import math
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from validator import flag_summary, quality_distribution


# ── Columnas de exportación ───────────────────────────────────────────────────

EXPORT_COLS_FULL = [
    "timestamp_start",
    "timestamp_center",
    "GHI_h",
    "DNI_dirint",
    "DHI_dirint",
    "DNI_erbs",
    "DHI_erbs",
    "DNI_reindl2",
    "DHI_reindl2",
    "DNI",          # modelo primario
    "DHI",          # modelo primario
    "Kt",
    "Ktp",
    "Kn_dirint",
    "W_cm",
    "cos_Z",
    "zenith_deg",
    "AM",
    "G0n",
    "G0h",
    "coverage",
    "quality_score",
    "flag_kt_cloud_enh",
    "flag_kt_unphysical",
    "flag_dni_high",
    "flag_dni_unphysical",
    "flag_dni_negative",
    "flag_dhi_exceeds_ghi",
    "flag_dhi_negative",
    "flag_night_nonzero",
    "flag_low_coverage",
    "flag_invalid_hour",
]

EXPORT_COLS_MINIMAL = [
    "timestamp_start",
    "GHI_h",
    "DNI",
    "DHI",
    "Kt",
    "zenith_deg",
    "quality_score",
]


def build_quality_report(
    df_validated: pd.DataFrame,
    site_info: dict,
    primary_model: str = "DIRINT",
) -> dict:
    """
    Construye el reporte de calidad completo.

    Parámetros
    ----------
    df_validated : DataFrame post-validator.validate
    site_info    : dict con lat, lon, tz_hr, nombre de archivo, etc.
    primary_model: "DIRINT" o "Erbs"

    Retorna
    -------
    dict con secciones: metadata, summary, flags, model_comparison,
    quality_distribution, monthly_stats.
    """
    n_total   = len(df_validated)
    n_daytime = int((df_validated["G0h"] > 0).sum())
    n_valid   = int(df_validated["GHI_h"].notna().sum())

    # ── Estadísticas diurnas ──────────────────────────────────────────────────
    day_mask  = (df_validated["G0h"] > 0) & df_validated["GHI_h"].notna()
    df_day    = df_validated[day_mask]

    def _safe_mean(col):
        return float(df_day[col].mean()) if len(df_day) > 0 else float("nan")

    def _safe_sum(col):
        return float(df_day[col].sum()) if len(df_day) > 0 else float("nan")

    # Energía acumulada [Wh/m²] (cada fila = 1 hora)
    ghi_energy  = _safe_sum("GHI_h")
    dni_energy  = float(df_day["DNI"].sum()) if "DNI" in df_day else float("nan")
    dhi_energy  = float(df_day["DHI"].sum()) if "DHI" in df_day else float("nan")

    # ── Comparación de modelos ────────────────────────────────────────────────
    model_comparison = _model_comparison(df_day)

    # ── Estadísticas mensuales ────────────────────────────────────────────────
    monthly = _monthly_stats(df_validated)

    report = {
        "metadata": {
            "generated_at":   datetime.now().isoformat(timespec="seconds"),
            "primary_model":  primary_model,
            "source_file":    site_info.get("filename", ""),
            "latitude_deg":   site_info.get("lat_deg"),
            "longitude_deg":  site_info.get("lon_deg"),
            "tz_hr":          site_info.get("tz_hr"),
            "resolution":     site_info.get("resolution", ""),
        },
        "summary": {
            "n_total_hours":      n_total,
            "n_daytime_hours":    n_daytime,
            "n_valid_hours":      n_valid,
            "n_invalid_hours":    n_total - n_valid,
            "ghi_total_Wh_m2":    ghi_energy,
            "dni_total_Wh_m2":    dni_energy,
            "dhi_total_Wh_m2":    dhi_energy,
            "ghi_mean_daytime":   _safe_mean("GHI_h"),
            "dni_mean_daytime":   _safe_mean("DNI") if "DNI" in df_day.columns else float("nan"),
            "dhi_mean_daytime":   _safe_mean("DHI") if "DHI" in df_day.columns else float("nan"),
            "kt_mean":            _safe_mean("Kt"),
            "kt_max":             float(df_day["Kt"].max()) if len(df_day) > 0 else float("nan"),
            "quality_score_mean": float(df_validated["quality_score"].mean(skipna=True)),
            "quality_score_min":  float(df_validated["quality_score"].min(skipna=True)),
        },
        "flags":               flag_summary(df_validated),
        "model_comparison":    model_comparison,
        "quality_distribution": quality_distribution(df_validated),
        "monthly_stats":       monthly,
    }

    return report


def _model_comparison(df_day: pd.DataFrame) -> dict:
    """Comparativa estadística entre los tres modelos (DIRINT, Erbs, Reindl-2)."""
    required = ["DNI_dirint", "DNI_erbs"]
    if not all(c in df_day.columns for c in required):
        return {}

    def rmse(a, b):
        valid = ~np.isnan(a) & ~np.isnan(b)
        return float(np.sqrt(np.mean((a[valid] - b[valid])**2))) if valid.sum() > 0 else float("nan")

    def mbe(a, b):
        valid = ~np.isnan(a) & ~np.isnan(b)
        return float(np.mean(a[valid] - b[valid])) if valid.sum() > 0 else float("nan")

    def stats(col_a, col_b, label_a, label_b):
        mask = df_day[col_a].notna() & df_day[col_b].notna()
        if mask.sum() == 0:
            return {}
        a = df_day.loc[mask, col_a].values
        b = df_day.loc[mask, col_b].values
        return {
            f"{label_a}_mean": float(np.nanmean(a)),
            f"{label_b}_mean": float(np.nanmean(b)),
            "RMSE_W_m2": rmse(a, b),
            "MBE_W_m2":  mbe(a, b),
            "diff_pct":  float(100 * (np.nanmean(a) - np.nanmean(b)) / (np.nanmean(b) + 1e-9)),
        }

    result: dict = {}
    result["DNI_DIRINT_vs_Erbs"]    = stats("DNI_dirint", "DNI_erbs",    "DIRINT", "Erbs")
    result["DHI_DIRINT_vs_Erbs"]    = stats("DHI_dirint", "DHI_erbs",    "DIRINT", "Erbs")
    if "DNI_reindl2" in df_day.columns:
        result["DNI_DIRINT_vs_Reindl2"] = stats("DNI_dirint", "DNI_reindl2", "DIRINT", "Reindl2")
        result["DHI_DIRINT_vs_Reindl2"] = stats("DHI_dirint", "DHI_reindl2", "DIRINT", "Reindl2")
        result["DNI_Erbs_vs_Reindl2"]   = stats("DNI_erbs",   "DNI_reindl2", "Erbs",   "Reindl2")
        result["DHI_Erbs_vs_Reindl2"]   = stats("DHI_erbs",   "DHI_reindl2", "Erbs",   "Reindl2")

    # Backward-compatible keys for existing UI code
    if result.get("DNI_DIRINT_vs_Erbs"):
        s = result["DNI_DIRINT_vs_Erbs"]
        result["DNI"] = {"DIRINT_mean": s.get("DIRINT_mean"), "Erbs_mean": s.get("Erbs_mean"),
                         "RMSE_W_m2": s.get("RMSE_W_m2"), "MBE_W_m2": s.get("MBE_W_m2"),
                         "diff_pct": s.get("diff_pct")}
    if result.get("DHI_DIRINT_vs_Erbs"):
        s = result["DHI_DIRINT_vs_Erbs"]
        result["DHI"] = {"DIRINT_mean": s.get("DIRINT_mean"), "Erbs_mean": s.get("Erbs_mean"),
                         "RMSE_W_m2": s.get("RMSE_W_m2"), "MBE_W_m2": s.get("MBE_W_m2"),
                         "diff_pct": s.get("diff_pct")}
    return result


def _monthly_stats(df: pd.DataFrame) -> dict:
    """Estadísticas mensuales de GHI, DNI, DHI y quality_score."""
    if "timestamp_start" not in df.columns:
        return {}

    df2 = df.copy()
    df2["_month"] = pd.to_datetime(df2["timestamp_start"]).dt.month

    result = {}
    for m, grp in df2.groupby("_month"):
        day_mask = grp["G0h"] > 0
        grp_day  = grp[day_mask]
        result[int(m)] = {
            "GHI_sum_kWh_m2":  round(float(grp_day["GHI_h"].sum()) / 1000, 2),
            "DNI_sum_kWh_m2":  round(float(grp_day["DNI"].sum()) / 1000, 2) if "DNI" in grp_day else float("nan"),
            "DHI_sum_kWh_m2":  round(float(grp_day["DHI"].sum()) / 1000, 2) if "DHI" in grp_day else float("nan"),
            "Kt_mean":         round(float(grp_day["Kt"].mean()), 3) if not grp_day.empty else float("nan"),
            "quality_mean":    round(float(grp["quality_score"].mean(skipna=True)), 1),
            "n_hours":         int(len(grp)),
        }
    return result


# ── Exportación CSV / Excel ───────────────────────────────────────────────────

def export_csv(df_validated: pd.DataFrame, minimal: bool = False) -> bytes:
    """Retorna CSV como bytes para st.download_button."""
    cols = EXPORT_COLS_MINIMAL if minimal else EXPORT_COLS_FULL
    cols_present = [c for c in cols if c in df_validated.columns]
    buf = io.BytesIO()
    df_validated[cols_present].to_csv(buf, index=False, float_format="%.4f")
    return buf.getvalue()


_LEGEND_ROWS = [
    ("timestamp_start",      "—",       "Inicio del intervalo horario"),
    ("timestamp_center",     "—",       "Centro del intervalo horario (usado en cálculos)"),
    ("GHI_h",                "W/m²",    "Irradiancia global horizontal promediada al intervalo horario"),
    ("DNI_dirint",           "W/m²",    "DNI calculado con modelo DIRINT (Perez et al., 1992)"),
    ("DHI_dirint",           "W/m²",    "DHI calculado con modelo DIRINT"),
    ("DNI_erbs",             "W/m²",    "DNI calculado con modelo Erbs (Erbs et al., 1982)"),
    ("DHI_erbs",             "W/m²",    "DHI calculado con modelo Erbs"),
    ("DNI_reindl2",          "W/m²",    "DNI calculado con modelo Reindl-2 (Reindl et al., 1990)"),
    ("DHI_reindl2",          "W/m²",    "DHI calculado con modelo Reindl-2"),
    ("DNI",                  "W/m²",    "DNI columna principal (DIRINT por compatibilidad)"),
    ("DHI",                  "W/m²",    "DHI columna principal (DIRINT por compatibilidad)"),
    ("Kt",                   "—",       "Índice de claridad: GHI / G0h (0 = nublado, ~1 = cielo despejado)"),
    ("Ktp",                  "—",       "Índice de claridad modificado Kt' (corregido por masa de aire)"),
    ("Kn_dirint",            "—",       "Factor de beam normalizado usado internamente por DIRINT"),
    ("W_cm",                 "cm",      "Agua precipitable estimada (Leckner, 1978). Usada por DIRINT."),
    ("cos_Z",                "—",       "Coseno del ángulo cenital solar (promedio analítico del intervalo)"),
    ("zenith_deg",           "°",       "Ángulo cenital solar en el centro del intervalo"),
    ("AM",                   "—",       "Masa de aire óptica (Kasten & Young, 1989)"),
    ("G0n",                  "W/m²",    "Irradiancia extraterrestre normal (sin atmósfera)"),
    ("G0h",                  "W/m²",    "Irradiancia extraterrestre horizontal = G0n × cos(Z)"),
    ("coverage",             "fracción","Fracción de registros sub-horarios válidos en el intervalo (0–1)"),
    ("quality_score",        "0–100",   "Puntaje de calidad del dato horario. 100 = sin flags. Penaliza cada flag según su severidad."),
    ("flag_kt_cloud_enh",    "bool",    "Kt > 0.9: posible cloud enhancement (sobreestimación transitoria por nube brillante)"),
    ("flag_kt_unphysical",   "bool",    "Kt > 1.05: valor físicamente imposible, probable error de sensor o calibración"),
    ("flag_dni_high",        "bool",    "DNI > G0n: supera la irradiancia extraterrestre (imposible físicamente)"),
    ("flag_dni_unphysical",  "bool",    "DNI > 1000 W/m² con ángulo cenital alto: combinación sospechosa"),
    ("flag_dni_negative",    "bool",    "DNI < 0: valor negativo (error numérico o de sensor)"),
    ("flag_dhi_exceeds_ghi", "bool",    "DHI > GHI: la difusa no puede superar la global horizontal"),
    ("flag_dhi_negative",    "bool",    "DHI < 0: valor negativo (error numérico o de sensor)"),
    ("flag_night_nonzero",   "bool",    "GHI > 0 cuando el sol está bajo el horizonte (cos Z ≤ 0)"),
    ("flag_low_coverage",    "bool",    "Menos del 75 % de registros sub-horarios disponibles en el intervalo"),
    ("flag_invalid_hour",    "bool",    "Hora descartada por múltiples flags críticos simultáneos"),
]


def export_excel(
    df_validated: pd.DataFrame,
    report: dict,
    minimal: bool = False,
) -> bytes:
    """
    Retorna archivo Excel (bytes) con tres hojas:
      - 'Datos': DataFrame de resultados
      - 'Reporte_Calidad': resumen de calidad en formato tabla
      - 'Leyenda': descripción de cada columna y flag
    """
    cols = EXPORT_COLS_MINIMAL if minimal else EXPORT_COLS_FULL
    cols_present = [c for c in cols if c in df_validated.columns]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_validated[cols_present].to_excel(writer, sheet_name="Datos", index=False)
        _report_to_sheet(report, writer, sheet_name="Reporte_Calidad")
        pd.DataFrame(
            [(r[0], r[1], r[2]) for r in _LEGEND_ROWS if r[0] in cols_present or not minimal],
            columns=["Columna", "Unidad", "Descripción"],
        ).to_excel(writer, sheet_name="Leyenda", index=False)
    return buf.getvalue()


def _report_to_sheet(report: dict, writer, sheet_name: str = "Reporte"):
    """Escribe el reporte de calidad en una hoja Excel plana (key-value)."""
    rows = []

    def flatten(d, prefix=""):
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                flatten(v, full_key)
            else:
                rows.append({"Indicador": full_key, "Valor": v})

    flatten(report)
    pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


def report_to_json_str(report: dict) -> str:
    """Serializa el reporte a JSON string (para descarga)."""
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


# ── Template de datos de entrada ──────────────────────────────────────────────

def generate_template_excel() -> bytes:
    """
    Genera un archivo Excel de plantilla para el usuario.
    Hoja 1: Instrucciones con descripcion de cada columna.
    Hoja 2: Plantilla con encabezados y filas de ejemplo.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # ── Hoja 1: Instrucciones ─────────────────────────────────────────────
        instructions = pd.DataFrame([
            ["INSTRUCCIONES — Solar Decomp", ""],
            ["", ""],
            ["COLUMNAS REQUERIDAS", ""],
            ["timestamp", "Fecha y hora. Formatos aceptados: YYYY-MM-DD HH:MM:SS | DD/MM/YYYY HH:MM | ISO 8601"],
            ["GHI", "Irradiancia global horizontal [W/m2]. Nombres aceptados: ghi, global_horizontal_irradiance, swdown, ssrd"],
            ["", ""],
            ["COLUMNAS OPCIONALES (mejoran la precision del modelo DIRINT)", ""],
            ["temp", "Temperatura de bulbo seco [grados C]. Nombres: temp, temp_C, t2m, temperatura"],
            ["pressure", "Presion atmosferica [kPa o hPa]. Nombres: pressure, press_kPa, p_hPa"],
            ["DNI", "Irradiancia directa normal [W/m2] — solo referencia, no se usa en la descomposicion"],
            ["DHI", "Irradiancia difusa horizontal [W/m2] — solo referencia, no se usa en la descomposicion"],
            ["", ""],
            ["RESOLUCIONES TEMPORALES SOPORTADAS", ""],
            ["1-min", "1 muestra por minuto (60 muestras/hora)"],
            ["15-min", "1 muestra cada 15 minutos (4 muestras/hora)"],
            ["60-min", "1 muestra por hora (1 muestra/hora)"],
            ["", ""],
            ["NOTAS", ""],
            ["- El separador de columnas puede ser coma (,) punto y coma (;) tabulacion o barra vertical (|)", ""],
            ["- Los valores faltantes deben estar vacios o como NaN", ""],
            ["- GHI debe estar en W/m2 (no en kW/m2 ni en MJ/m2)", ""],
            ["- La zona horaria se configura en la interfaz de la aplicacion, no en el archivo", ""],
        ], columns=["Campo / Descripcion", "Detalle"])
        instructions.to_excel(writer, sheet_name="Instrucciones", index=False)

        # ── Hoja 2: Plantilla ─────────────────────────────────────────────────
        example_data = pd.DataFrame({
            "timestamp":   [
                "2024-01-15 06:00:00", "2024-01-15 06:15:00",
                "2024-01-15 06:30:00", "2024-01-15 06:45:00",
                "2024-01-15 07:00:00", "2024-01-15 07:15:00",
                "2024-01-15 12:00:00", "2024-01-15 12:15:00",
                "2024-01-15 12:30:00", "2024-01-15 12:45:00",
            ],
            "GHI":         [12.5, 38.2, 75.0, 120.3, 185.7, 245.1, 850.4, 870.2, 860.0, 840.5],
            "temp":        [18.2, 18.3, 18.5, 18.8, 19.1, 19.5, 28.3, 28.6, 28.8, 28.7],
            "pressure":    [101.1, 101.1, 101.1, 101.1, 101.0, 101.0, 100.8, 100.8, 100.8, 100.8],
        })
        example_data.to_excel(writer, sheet_name="Plantilla", index=False)

    # Formato de anchos de columna
    from openpyxl import load_workbook
    buf.seek(0)
    wb = load_workbook(buf)
    ws_instr = wb["Instrucciones"]
    ws_instr.column_dimensions["A"].width = 65
    ws_instr.column_dimensions["B"].width = 90
    ws_templ = wb["Plantilla"]
    for col in ["A", "B", "C", "D"]:
        ws_templ.column_dimensions[col].width = 22

    buf2 = io.BytesIO()
    wb.save(buf2)
    return buf2.getvalue()


def generate_template_csv() -> bytes:
    """Genera CSV de plantilla con filas de ejemplo y encabezado comentado."""
    lines = [
        "# Solar Decomp — Plantilla de datos de entrada",
        "# Columnas requeridas: timestamp, GHI (W/m2)",
        "# Columnas opcionales: temp (grados C), pressure (kPa), DNI (W/m2), DHI (W/m2)",
        "# Resoluciones soportadas: 1-min, 15-min, 60-min",
        "timestamp,GHI,temp,pressure",
        "2024-01-15 06:00:00,12.5,18.2,101.1",
        "2024-01-15 06:15:00,38.2,18.3,101.1",
        "2024-01-15 06:30:00,75.0,18.5,101.1",
        "2024-01-15 06:45:00,120.3,18.8,101.1",
        "2024-01-15 07:00:00,185.7,19.1,101.0",
        "2024-01-15 12:00:00,850.4,28.3,100.8",
        "2024-01-15 12:15:00,870.2,28.6,100.8",
        "2024-01-15 12:30:00,860.0,28.8,100.8",
        "2024-01-15 12:45:00,840.5,28.7,100.8",
    ]
    return "\n".join(lines).encode("utf-8")
