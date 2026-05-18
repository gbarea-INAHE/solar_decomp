"""
epw_parser.py — Lee archivos EPW y retorna metadatos + DataFrame horario.

EPW columnas relevantes (0-based, tras split por coma):
  0:year  1:month  2:day  3:hour(1-24)  6:temp_C  9:pressure_Pa
  13:GHI(Wh/m²)  14:DNI(Wh/m²)  15:DHI(Wh/m²)

Los valores de radiación en EPW son Wh/m² para el intervalo horario,
equivalentes a W/m² promedio horario.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd


def parse_epw(path: str | Path) -> tuple[dict, pd.DataFrame]:
    """
    Retorna:
      meta  : dict con city, lat, lon, tz, elevation
      df    : DataFrame horario con columnas timestamp, GHI, DNI, DHI, temp_C, pressure_kPa
    """
    path = Path(path)
    rows = []
    meta = {}

    with open(path, encoding="latin-1") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if i == 0:
                parts = line.split(",")
                meta = {
                    "city":      parts[1].strip(),
                    "country":   parts[3].strip(),
                    "source":    parts[4].strip(),
                    "wmo":       parts[5].strip(),
                    "lat":       float(parts[6]),
                    "lon":       float(parts[7]),
                    "tz":        float(parts[8]),
                    "elevation": float(parts[9]),
                    "file":      path.name,
                }
            if i < 8:
                continue
            p = line.split(",")
            if len(p) < 16:
                continue
            try:
                year  = int(p[0])
                month = int(p[1])
                day   = int(p[2])
                hour  = int(p[3])   # 1-24 en EPW
                # hora 24 del 31/12 → primer instante del año siguiente; tratar como 0
                if hour == 24:
                    hour = 0
                # timestamp_start = inicio del intervalo (hora - 1)
                ts_start = pd.Timestamp(year=year, month=month, day=day, hour=hour - 1 if hour > 0 else 0)
                rows.append({
                    "timestamp":    ts_start,
                    "GHI":          float(p[13]),
                    "DNI_ref":      float(p[14]),
                    "DHI_ref":      float(p[15]),
                    "temp_C":       float(p[6]),
                    "pressure_kPa": float(p[9]) / 1000.0,
                })
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)
    return meta, df
