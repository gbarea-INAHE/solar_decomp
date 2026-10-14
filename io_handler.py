"""
io_handler.py — Carga, detección de columnas y análisis de resolución temporal.

Soporta:
  - CSV / Excel (.xlsx, .xls)
  - EPW (EnergyPlus Weather, 1 registro por hora; ver read_epw)
  - Detección automática de columna GHI (alias comunes)
  - Detección automática de timestamp (múltiples formatos)
  - Detección de resolución temporal: 1-min, 15-min, 60-min
  - Columnas opcionales: DNI, DHI, temperatura, presión
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config import RES_TOLERANCES

# ── Alias de columnas ─────────────────────────────────────────────────────────

# Orden: más específico primero (evita capturas erróneas)
GHI_ALIASES = [
    r"^ghi$", r"^global_horizontal_irradiance$", r"^global.*horiz",
    r"^irradiancia.*global", r"^gh$", r"^g_h$", r"^ghi_w",
    r"^solar.*global", r"^swdown$", r"^ssrd$",          # ERA5 / WRF
    r"^global.*solar", r"^global_solar",                 # plantilla v2
]
DNI_ALIASES = [
    r"^dni$", r"^direct_normal_irradiance$", r"^direct.*normal",
    r"^irradiancia.*directa", r"^bn$", r"^dni_w", r"^beam$",
    r"^normal.*solar", r"^normal_solar",                 # plantilla v2
]
DHI_ALIASES = [
    r"^dhi$", r"^diffuse_horizontal_irradiance$", r"^diffuse.*horiz",
    r"^irradiancia.*difusa", r"^dh$", r"^d_h$", r"^dif$",
    r"^diffuse.*solar", r"^diffuse_solar",               # plantilla v2
]
TEMP_ALIASES = [
    r"^temp.*dry|^tdb$|^dry.*bulb|^temperatura|^temp_c|^air.*temp|^t2m$",
    r"^dry_bulb",                                        # plantilla v2
]
PRESSURE_ALIASES = [
    r"^pressure|^presion|^press_kpa|^p_kpa|^p_hpa|^sp$|^msl$",
    r"^atmospheric.*pressure",                           # plantilla v2
]
HUMIDITY_ALIASES = [
    r"^rh$|^rh_|^relative.*humid|^humidity|^humedad|^hum_rel|^hr_pct|^hr_%",
]
DEWPOINT_ALIASES = [
    r"^dew|^tdew|^t_dew|^td$|^td_|^temp.*dew|^punto.*roc",
]
TIMESTAMP_ALIASES = [
    r"^timestamp|^datetime|^fecha|^time$|^date$|^dt$|^hora$",
    r"^date.*time|^time.*stamp",
    r"^date_time$|^date/_time$",                         # plantilla v2 (Date/Time)
]


def _match_col(col: str, patterns: list[str]) -> bool:
    """True si el nombre de columna (normalizado) coincide con algún patrón."""
    c = col.strip().lower().replace(" ", "_").replace("-", "_")
    return any(re.search(p, c) for p in patterns)


def _find_col(df: pd.DataFrame, patterns: list[str]) -> Optional[str]:
    """Devuelve el nombre original de la primera columna que coincide."""
    for col in df.columns:
        if _match_col(col, patterns):
            return col
    return None


# ── Detección de timestamp ────────────────────────────────────────────────────

_TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d @ %H:%M:%S",   # plantilla v2: 2005/01/01 @ 00:00:00
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y%m%d%H%M",
    "%Y%m%d%H%M%S",
]


def _parse_timestamp_col(series: pd.Series) -> pd.Series:
    """
    Intenta parsear una Serie de strings/objects a datetime.
    Prueba formatos conocidos; fallback a pd.to_datetime(infer).
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    sample = series.dropna().iloc[0] if not series.dropna().empty else None
    if sample is None:
        raise ValueError("Columna de timestamp vacía.")

    # Intentar formatos explícitos primero
    for fmt in _TS_FORMATS:
        try:
            parsed = pd.to_datetime(series, format=fmt, errors="raise")
            return parsed
        except Exception:
            continue

    # Fallback inferido
    try:
        return pd.to_datetime(series, infer_datetime_format=True, errors="raise")
    except Exception:
        raise ValueError(
            f"No se pudo parsear la columna de timestamp. "
            f"Muestra: '{sample}'. Formatos soportados: {_TS_FORMATS}"
        )


def _build_timestamp_from_parts(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Si no hay columna timestamp unificada, intenta construirla desde
    columnas separadas: year, month, day, hour (y opcionalmente minute).
    """
    required = ["year", "month", "day", "hour"]
    cols_lower = {c.lower(): c for c in df.columns}
    if not all(r in cols_lower for r in required):
        return None

    try:
        ts = pd.to_datetime({
            "year":   df[cols_lower["year"]],
            "month":  df[cols_lower["month"]],
            "day":    df[cols_lower["day"]],
            "hour":   df[cols_lower["hour"]],
            "minute": df[cols_lower["minute"]] if "minute" in cols_lower else 0,
        })
        return ts
    except Exception:
        return None


# ── Detección de resolución temporal ─────────────────────────────────────────

def detect_resolution_sec(timestamps: pd.Series) -> int:
    """
    Detecta la resolución temporal en segundos a partir de las diferencias.

    Proceso:
      1. Calcula diferencias consecutivas en segundos.
      2. Toma la mediana (robusto frente a gaps).
      3. Clasifica en {60, 900, 3600} con tolerancias de config.RES_TOLERANCES.
      4. Si no encaja en ninguna → error con valor mediano informativo.

    Returns:
        int — 60, 900 o 3600
    """
    if len(timestamps) < 2:
        raise ValueError("Se necesitan al menos 2 registros para detectar resolución.")

    diffs_s = timestamps.sort_values().diff().dropna().dt.total_seconds()
    # Filtrar diferencias ≤ 0 o absurdamente grandes (>2 h)
    valid = diffs_s[(diffs_s > 0) & (diffs_s <= 7200)]
    if valid.empty:
        raise ValueError("No se encontraron diferencias de tiempo válidas.")

    median_s = float(valid.median())

    for res, (lo, hi) in RES_TOLERANCES.items():
        if lo <= median_s <= hi:
            return res

    raise ValueError(
        f"Resolución temporal no reconocida. Mediana de diferencias: {median_s:.0f} s. "
        f"Soportadas: 60 s (1-min), 900 s (15-min), 3600 s (60-min)."
    )


# ── Carga principal ───────────────────────────────────────────────────────────

class LoadedData:
    """Contenedor con el DataFrame cargado y metadata de detección."""

    def __init__(
        self,
        df: pd.DataFrame,
        timestamp_col: str,
        ghi_col: str,
        resolution_sec: int,
        dni_col: Optional[str] = None,
        dhi_col: Optional[str] = None,
        temp_col: Optional[str] = None,
        pressure_col: Optional[str] = None,
        warnings: Optional[list[str]] = None,
        humidity_col: Optional[str] = None,
        dewpoint_col: Optional[str] = None,
        epw_meta: Optional[dict] = None,
    ):
        self.df = df
        self.timestamp_col = timestamp_col
        self.ghi_col = ghi_col
        self.resolution_sec = resolution_sec
        self.dni_col = dni_col
        self.dhi_col = dhi_col
        self.temp_col = temp_col
        self.pressure_col = pressure_col
        self.humidity_col = humidity_col
        self.dewpoint_col = dewpoint_col
        self.epw_meta = epw_meta                  # dict con el encabezado del EPW (None si el archivo no es EPW)
        self.warnings: list[str] = warnings or []

    @property
    def is_epw(self) -> bool:
        return self.epw_meta is not None

    @property
    def resolution_label(self) -> str:
        labels = {60: "1-min", 900: "15-min", 3600: "60-min"}
        return labels.get(self.resolution_sec, f"{self.resolution_sec}s")

    def __repr__(self) -> str:
        return (
            f"LoadedData(rows={len(self.df)}, res={self.resolution_label}, "
            f"ghi='{self.ghi_col}', ts='{self.timestamp_col}')"
        )


# ── Lector de EPW ───────────────────────────────────────────────────────────

# Campos (base 0) del registro de datos EPW estándar de 35 columnas que usa la herramienta, y sus códigos de dato faltante
_EPW_COLS = {
    0: "year", 1: "month", 2: "day", 3: "hour", 6: "t_db", 7: "t_dew", 8: "rh", 9: "p_pa",
    13: "ghi", 14: "dni", 15: "dhi",
}
_EPW_MISSING = {"ghi": 9999.0, "dni": 9999.0, "dhi": 9999.0, "t_db": 99.9, "t_dew": 99.9, "rh": 999.0, "p_pa": 999999.0}


def _epw_text(path_or_buffer) -> tuple[str, str]:
    """Devuelve (texto, nombre) de un EPW dado como ruta o como buffer (p. ej., el UploadedFile de Streamlit)."""
    if isinstance(path_or_buffer, (str, Path)):
        raw = Path(path_or_buffer).read_bytes()
        name = Path(path_or_buffer).name
    else:
        name = getattr(path_or_buffer, "name", "archivo.epw")
        if hasattr(path_or_buffer, "seek"):
            path_or_buffer.seek(0)
        raw = path_or_buffer.read()
        if hasattr(path_or_buffer, "seek"):
            path_or_buffer.seek(0)
    if isinstance(raw, str):
        return raw, name
    try:
        return raw.decode("utf-8"), name
    except UnicodeDecodeError:
        return raw.decode("latin-1"), name       # codificación original de los EPW


def read_epw(path_or_buffer) -> tuple[dict, pd.DataFrame]:
    """
    Lee un archivo EPW (EnergyPlus Weather) con 1 registro por hora. Falla de forma explícita si no cumple el formato.

    - La hora h (1..24) del EPW es el intervalo que TERMINA en h, en hora estándar local del huso del encabezado:
      timestamp (inicio del intervalo) = fecha + (h − 1) horas.
    - Los códigos de dato faltante del EPW (9999, 99.9, 999, 999999) pasan a NaN en los campos que se usan.
    - Un EPW de tipo TMY toma cada mes de un año distinto: se conservan los años del archivo.

    Returns:
        (meta, df): meta = {file, city, state, country, source, wmo, lat, lon, tz, elev, n_rows, years};
        df con las columnas timestamp, GHI, DNI, DHI, temp_C, pressure_Pa (unidad nativa del EPW), RH, dew_point_C.
    Raises:
        ValueError con un mensaje explícito ante cualquier incumplimiento del formato.
    """
    text, name = _epw_text(path_or_buffer)
    lines = text.splitlines()
    k = next((i for i, ln in enumerate(lines[:20]) if ln.strip().upper().startswith("DATA PERIODS")), None)
    if k is None:
        raise ValueError(f"{name}: no es un EPW válido (no se encontró la línea DATA PERIODS en el encabezado).")
    loc = lines[0].split(",")
    if loc[0].strip().upper() != "LOCATION" or len(loc) < 10:
        raise ValueError(f"{name}: la primera línea no es un registro LOCATION válido: {lines[0][:80]!r}")
    try:
        lat, lon, tz, elev = (float(loc[i]) for i in (6, 7, 8, 9))
    except ValueError:
        raise ValueError(f"{name}: latitud, longitud, huso o elevación no numéricos en LOCATION: {lines[0][:80]!r}") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -12 <= tz <= 14):
        raise ValueError(f"{name}: LOCATION fuera de rango (lat={lat}, lon={lon}, huso={tz}).")
    dp = lines[k].split(",")
    try:
        steps = int(dp[2])
    except (IndexError, ValueError):
        raise ValueError(f"{name}: DATA PERIODS sin número de registros por hora: {lines[k][:80]!r}") from None
    if steps != 1:
        raise ValueError(f"{name}: el EPW tiene {steps} registros por hora; solo se admite 1 registro por hora.")
    rows = [ln.split(",") for ln in lines[k + 1:] if ln.strip()]
    if not rows:
        raise ValueError(f"{name}: el EPW no tiene registros de datos.")
    short = [i for i, r in enumerate(rows) if len(r) < 29]
    if short:
        raise ValueError(f"{name}: {len(short)} registros con menos de 29 campos (el primero, en la línea {k + 2 + short[0]}).")
    d = pd.DataFrame({nm: [r[i] for r in rows] for i, nm in _EPW_COLS.items()})
    try:
        d = d.apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError) as e:
        raise ValueError(f"{name}: valores no numéricos en los campos de fecha o de datos: {e}") from None
    for col, code in _EPW_MISSING.items():
        d[col] = d[col].where(d[col] < code, np.nan)
    if not d["hour"].between(1, 24).all():
        raise ValueError(f"{name}: el campo hora debe estar entre 1 y 24.")
    try:
        date = pd.to_datetime(d[["year", "month", "day"]].astype(int), errors="raise")
    except Exception as e:
        raise ValueError(f"{name}: fechas inválidas (año, mes, día): {e}") from None
    key = (d["month"] * 10000 + d["day"] * 100 + d["hour"]).to_numpy()
    if not (np.diff(key) > 0).all():
        raise ValueError(f"{name}: (mes, día, hora) no es estrictamente creciente; un EPW debe estar en orden de calendario.")
    if d["ghi"].isna().all():
        raise ValueError(f"{name}: no hay ningún valor válido de irradiancia global horizontal (GHI).")
    out = pd.DataFrame({
        "timestamp": date + pd.to_timedelta(d["hour"].astype(int) - 1, unit="h"),
        "GHI": d["ghi"], "DNI": d["dni"], "DHI": d["dhi"],
        "temp_C": d["t_db"], "pressure_Pa": d["p_pa"], "RH": d["rh"], "dew_point_C": d["t_dew"],
    })
    meta = {
        "file": name, "city": loc[1].strip(), "state": loc[2].strip(), "country": loc[3].strip(),
        "source": loc[4].strip(), "wmo": loc[5].strip(), "lat": lat, "lon": lon, "tz": tz, "elev": elev,
        "n_rows": len(out), "years": sorted(int(y) for y in d["year"].unique()),
    }
    return meta, out


def load_file(
    path_or_buffer,
    timestamp_col: Optional[str] = None,
    ghi_col: Optional[str] = None,
) -> LoadedData:
    """
    Carga un CSV, Excel o EPW y detecta automáticamente columnas y resolución.

    Args:
        path_or_buffer : ruta (str/Path) o buffer de bytes (para Streamlit).
        timestamp_col  : nombre exacto de columna timestamp (override auto-detect).
        ghi_col        : nombre exacto de columna GHI (override auto-detect).

    Returns:
        LoadedData

    Raises:
        ValueError si no se puede detectar GHI o timestamp.
    """
    warnings_list: list[str] = []

    # ── Leer archivo ──────────────────────────────────────────────────────────
    ext = ""
    if isinstance(path_or_buffer, (str, Path)):
        ext = Path(path_or_buffer).suffix.lower()
    elif hasattr(path_or_buffer, "name"):          # Streamlit UploadedFile
        ext = Path(path_or_buffer.name).suffix.lower()

    epw_meta = None
    if ext == ".epw":
        epw_meta, df = read_epw(path_or_buffer)
        warnings_list.append(
            f"EPW «{epw_meta['city']}» ({epw_meta['country']}): lat={epw_meta['lat']:.4f}, lon={epw_meta['lon']:.4f}, "
            f"huso UTC{epw_meta['tz']:+.1f}, elevación {epw_meta['elev']:.0f} m (leídos del encabezado)."
        )
        if len(epw_meta["years"]) > 1:
            warnings_list.append(
                f"El EPW toma sus meses de años distintos ({epw_meta['years'][0]}–{epw_meta['years'][-1]}, típico de un TMY): "
                "se conservan los años del archivo, las filas quedan en orden cronológico y el DIRINT se calcula por tramos continuos."
            )
        if epw_meta["n_rows"] not in (8760, 8784):
            warnings_list.append(f"El EPW tiene {epw_meta['n_rows']} registros (se esperaban 8760 u 8784).")
    elif ext in (".xlsx", ".xls"):
        df = _read_excel_template_aware(path_or_buffer)
    else:
        # CSV: ignorar líneas de comentario iniciales (#) e inferir separador
        df = _read_csv_robust(_skip_leading_comment_lines(path_or_buffer))

    if df.empty:
        raise ValueError("El archivo está vacío o no contiene datos.")

    # ── Detectar / validar columna GHI ───────────────────────────────────────
    if ghi_col:
        if ghi_col not in df.columns:
            raise ValueError(f"Columna GHI especificada '{ghi_col}' no encontrada.")
    else:
        ghi_col = _find_col(df, GHI_ALIASES)
        if ghi_col is None:
            cols = list(df.columns)
            raise ValueError(
                f"No se detectó columna GHI. Columnas disponibles: {cols}. "
                f"Use el parámetro ghi_col= para especificarla."
            )

    # ── Detectar / validar columna timestamp ─────────────────────────────────
    if timestamp_col:
        if timestamp_col not in df.columns:
            raise ValueError(f"Columna timestamp '{timestamp_col}' no encontrada.")
        df["_timestamp"] = _parse_timestamp_col(df[timestamp_col])
    else:
        ts_col = _find_col(df, TIMESTAMP_ALIASES)
        if ts_col is not None:
            df["_timestamp"] = _parse_timestamp_col(df[ts_col])
            timestamp_col = ts_col
        else:
            # Intentar construir desde columnas separadas
            ts_built = _build_timestamp_from_parts(df)
            if ts_built is not None:
                df["_timestamp"] = ts_built
                timestamp_col = "_timestamp"
                warnings_list.append(
                    "Timestamp construido desde columnas separadas (year/month/day/hour)."
                )
            else:
                raise ValueError(
                    "No se detectó columna de timestamp. "
                    "Columnas esperadas: 'timestamp', 'datetime', 'fecha', 'date', etc., "
                    "o columnas separadas: year, month, day, hour."
                )

    # ── Detectar columnas opcionales ─────────────────────────────────────────
    dni_col  = _find_col(df, DNI_ALIASES)
    dhi_col  = _find_col(df, DHI_ALIASES)
    temp_col = _find_col(df, TEMP_ALIASES)
    pres_col = _find_col(df, PRESSURE_ALIASES)
    hum_col  = _find_col(df, HUMIDITY_ALIASES)
    dew_col  = _find_col(df, DEWPOINT_ALIASES)

    # ── Limpiar GHI: coerce numérico, NaN explícito ───────────────────────────
    df[ghi_col] = pd.to_numeric(df[ghi_col], errors="coerce")
    n_invalid = df[ghi_col].isna().sum()
    if n_invalid > 0:
        warnings_list.append(
            f"{n_invalid} valores no numéricos en '{ghi_col}' → NaN."
        )

    # ── Detectar resolución ───────────────────────────────────────────────────
    resolution_sec = detect_resolution_sec(df["_timestamp"])

    # ── Advertencias ─────────────────────────────────────────────────────────
    if dni_col:
        warnings_list.append(f"Columna DNI detectada: '{dni_col}' (referencia, no usada en descomposición).")
    if dhi_col:
        warnings_list.append(f"Columna DHI detectada: '{dhi_col}' (referencia, no usada en descomposición).")

    return LoadedData(
        df=df,
        timestamp_col=timestamp_col,
        ghi_col=ghi_col,
        resolution_sec=resolution_sec,
        dni_col=dni_col,
        dhi_col=dhi_col,
        temp_col=temp_col,
        pressure_col=pres_col,
        warnings=warnings_list,
        humidity_col=hum_col,
        dewpoint_col=dew_col,
        epw_meta=epw_meta,
    )


def _skip_leading_comment_lines(path_or_buffer):
    """
    Si el CSV empieza con líneas de comentario (las que comienzan con '#', como las de la plantilla descargable),
    devuelve un buffer de texto sin esas líneas iniciales. Si no empieza con '#', devuelve el objeto original sin cambios.
    Solo se ignoran las líneas iniciales: un '#' dentro de los datos no se toca.
    """
    if isinstance(path_or_buffer, (str, Path)):
        with open(path_or_buffer, "rb") as f:
            raw = f.read()
        seekable = False
    else:
        raw = path_or_buffer.read()
        seekable = hasattr(path_or_buffer, "seek")
        if seekable:
            path_or_buffer.seek(0)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    if not raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#"):
        return path_or_buffer
    lines = raw.decode("utf-8-sig", errors="replace").splitlines(keepends=True)
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("#")):
        i += 1
    return io.StringIO("".join(lines[i:]))


def _read_excel_template_aware(path_or_buffer) -> pd.DataFrame:
    """
    Lee un Excel. Si el libro tiene una hoja llamada «Plantilla» (la plantilla descargable trae primero «Instrucciones»),
    lee esa hoja; en cualquier otro caso lee la primera hoja, como antes.
    """
    xl = pd.ExcelFile(path_or_buffer, engine="openpyxl")
    sheet = next((n for n in xl.sheet_names if str(n).strip().lower() == "plantilla"), xl.sheet_names[0])
    return xl.parse(sheet)


def _read_csv_robust(path_or_buffer) -> pd.DataFrame:
    """
    Lee CSV intentando separadores comunes (,  ;  \\t  |).
    Elige el que produce más columnas (heurístico simple).
    """
    separators = [",", ";", "\t", "|"]
    best_df = None
    best_ncols = 0

    for sep in separators:
        try:
            df = pd.read_csv(path_or_buffer, sep=sep, low_memory=False)
            if len(df.columns) > best_ncols:
                best_ncols = len(df.columns)
                best_df = df
            # Reset buffer si es seekable
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
        except Exception:
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
            continue

    if best_df is None or best_ncols < 2:
        raise ValueError("No se pudo leer el CSV. Verifique el formato y separador.")

    return best_df


# ── Utilidades de inspección ──────────────────────────────────────────────────

def summarize_loaded(ld: LoadedData) -> dict:
    """Resumen estadístico básico para mostrar en UI."""
    ghi = ld.df[ld.ghi_col].dropna()
    ts  = ld.df["_timestamp"]

    return {
        "n_rows":          len(ld.df),
        "resolution":      ld.resolution_label,
        "start":           str(ts.min()),
        "end":             str(ts.max()),
        "ghi_col":         ld.ghi_col,
        "ghi_min":         float(ghi.min()),
        "ghi_max":         float(ghi.max()),
        "ghi_mean":        float(ghi.mean()),
        "ghi_nan_pct":     float(ld.df[ld.ghi_col].isna().mean() * 100),
        "has_dni":         ld.dni_col is not None,
        "has_dhi":         ld.dhi_col is not None,
        "has_temp":        ld.temp_col is not None,
        "has_pressure":    ld.pressure_col is not None,
        "has_humidity":    ld.humidity_col is not None,
        "has_dewpoint":    ld.dewpoint_col is not None,
        "warnings":        ld.warnings,
    }
