# Solar Decomp — GHI → DNI + DHI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://solar-decomp.streamlit.app)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20262706.svg)](https://doi.org/10.5281/zenodo.20262706)

**Solar Decomp** is an open-source web application for decomposing global horizontal irradiance (GHI) time series into direct normal irradiance (DNI) and diffuse horizontal irradiance (DHI), using physically rigorous solar radiation models.

**Authors:** Dr. Arq. Gustavo Barea Paci · Dra. Arq. Carolina Ganem — [INAHE-CONICET](https://www.mendoza-conicet.gob.ar/inahe/), Argentina.

---

## Live Application

The application is publicly available at:

> **[https://solar-decomp.streamlit.app](https://solar-decomp.streamlit.app)**

No installation required. Upload your CSV, Excel or EPW file and download results immediately.

---

## Features

- **Three decomposition models** running in parallel:
  - **DIRINT** (Perez et al., 1992, via pvlib-python): coefficient table indexed by Kt', solar zenith angle, ΔKt' and precipitable water.
  - **Erbs** (Erbs et al., 1982): piecewise polynomial Kd(Kt); robust fallback requiring no precipitable water data.
  - **Reindl-2** (Reindl et al., 1990): empirical model incorporating solar elevation angle sin(α).
- **Automatic input detection**: column names (GHI, DNI, DHI, temperature, pressure), timestamp formats, and temporal resolution (1-min, 15-min, 60-min).
- **Solar geometry engine**: analytical integration of cos(Z) over hourly intervals (Spencer, 1971 / Cooper, 1969), air mass (Kasten & Young, 1989), and precipitable water from the dew point (optional; see Methods).
- **Physical quality control**: 10 flag types + quality score (0–100) with configurable penalties.
- **Interactive visualizations**: time series, monthly energy bars, DIRINT vs Erbs scatter, clearness index histogram, quality score timeline.
- **EPW input**: EnergyPlus Weather files (one record per hour, including TMY files) are read directly; site latitude, longitude, time zone and elevation are taken from the header.
- **Consistency with the file's own DNI/DHI**: when the input has DNI and/or DHI columns (for example, the radiation fields of an EPW, or measurements), each model is compared with them (n, RMSE, MBE, nRMSE, R²). This is consistency with that reference, not accuracy, unless the reference is a measurement.
- **Export**: CSV (full or minimal), Excel (data + quality report), JSON report.

---

## Input Format

| Column | Required | Description | Example names |
|--------|----------|-------------|---------------|
| Timestamp | **Yes** | Date and time (any standard format) | `timestamp`, `datetime`, `fecha`, `date`, `date_time`, `Date/Time` |
| GHI [W/m²] | **Yes** | Global horizontal irradiance | `GHI`, `global_horizontal_irradiance`, `global_solar`, `swdown` |
| DNI [W/m²] | No | Direct normal irradiance (reference only) | `DNI`, `direct_normal_irradiance`, `normal_solar` |
| DHI [W/m²] | No | Diffuse horizontal irradiance (reference only) | `DHI`, `diffuse_horizontal_irradiance`, `diffuse_solar` |
| Temperature [°C] | No | Dry-bulb air temperature | `temp_C`, `t2m`, `temperatura`, `dry_bulb` (a column named only `temp` or `temperature` is **not** recognized) |
| Pressure [kPa, hPa or Pa] | No | Atmospheric pressure; the unit is inferred from the magnitude of the median (kPa 30–110, hPa 300–1100, Pa 30 000–110 000) and the tool stops with an error if it is not a plausible surface pressure | `pressure`, `press_kPa`, `atmospheric_pressure` |
| Relative humidity [%] | No | Relative humidity, 0–100 (not a fraction); with temperature it is converted to dew point | `RH`, `relative_humidity`, `humedad` |
| Dew point [°C] | No | Dew point temperature; takes priority over humidity | `dew_point`, `Tdew`, `punto_de_rocio` |

Supported timestamp formats include `YYYY-MM-DD HH:MM:SS`, `YYYY/MM/DD @ HH:MM:SS`, `DD/MM/YYYY HH:MM`, and ISO 8601 variants.
Columns with separate `year`, `month`, `day`, `hour` fields are also supported.

A **downloadable template** (Excel + CSV) is available directly from the application sidebar.

### EPW files

An `.epw` file (EnergyPlus Weather, **one record per hour**) can be uploaded directly. From the data records the tool reads GHI, dry-bulb temperature, atmospheric pressure (Pa), relative humidity and dew point, and from the `LOCATION` header the latitude, longitude, time zone and elevation, which pre-fill the *Site* fields (check them before running).

- Hour *h* (1–24) of an EPW is the interval **ending** at *h*, in the standard local time of the header's time zone; the tool uses the start of the interval (hour 1 = 00:00).
- EPW missing-value codes (9999, 99.9, 999, 999999) become missing values (NaN).
- The file's DNI and DHI are **not preserved** by default: they are the reference against which the three models are compared (see *Consistency with the file's own DNI/DHI*). In an IWEC2 file they are not measurements: the DNI is a Gompertz split of the file's own GHI and the DHI follows by closure, so a small difference means similarity to that generator, not accuracy.
- TMY files take each month from a different year; the years of the file are kept, rows are ordered chronologically by those years, and the DIRINT is computed on continuous segments (a warning is shown).
- A file that is not a valid EPW (missing `LOCATION` or `DATA PERIODS`, more than one record per hour, non-numeric fields, hours outside 1–24, dates out of calendar order, no valid GHI) stops with an explicit error message.

---

## Output Columns

| Column | Description | Units |
|--------|-------------|-------|
| `timestamp_start` | Start of hourly interval | — |
| `GHI_h` | Hourly-averaged GHI | W/m² |
| `DNI_dirint` | DNI from DIRINT model | W/m² |
| `DHI_dirint` | DHI from DIRINT model | W/m² |
| `DNI_erbs` | DNI from Erbs model | W/m² |
| `DHI_erbs` | DHI from Erbs model | W/m² |
| `DNI` / `DHI` | Primary model output | W/m² |
| `Kt` | Clearness index (GHI/G0h) | — |
| `Ktp` | Modified clearness index Kt' | — |
| `W_cm` | Precipitable water derived from the dew point (NaN when the dew point is not used) | cm |
| `zenith_deg` | Solar zenith angle | ° |
| `AM` | Air mass (Kasten & Young) | — |
| `quality_score` | Quality score (0–100) | — |
| `flag_*` | Physical quality flags | boolean |

---

## Local Installation

```bash
git clone https://github.com/gbarea-INAHE/solar_decomp.git
cd solar_decomp
pip install -r requirements.txt
streamlit run app_solar.py
```

**Requirements**: Python 3.11 or higher. The software was tested with Python 3.14, streamlit 1.65, pandas 3.0, numpy 2.5, plotly 7.1, openpyxl 3.1 and pvlib 0.16.1; these dependency versions require Python 3.11 or higher, and older Python versions have not been tested.

---

## Running Tests

```bash
python test_pipeline.py
python test_dirint_perez1992.py
python test_dewpoint_humidity.py
python test_loader_templates.py
python test_epw_loader.py
python test_reference_consistency.py
python test_pressure_units.py
```

`test_pipeline.py` performs an end-to-end verification using the included `test_data_15min.csv` (synthetic 15-min data for Buenos Aires, full year). The EPW tests generate synthetic EPW files in memory; no EPW data are distributed with this repository.

---

## Methods

### DIRINT — Perez et al. (1992)

Since version 1.1.0 the DIRINT model is the one of Perez et al. (1992) as implemented in `pvlib.irradiance.dirint`: DNI is obtained from the DISC model multiplied by a coefficient taken from a table indexed by:
- Modified clearness index Kt'
- Solar zenith angle
- Hourly variability ΔKt' (average of the absolute differences with the previous and the next hour)
- Precipitable water W

By default W is not provided and the "unknown precipitable water" class of Perez et al. is used. If the input file has relative humidity (with temperature) or dew point and the option is enabled, W is derived from the dew point (W = exp(0.07·Td − 0.075)). Series with time gaps (for example a TMY with months from different years) are split into continuous 1-hour segments before calling pvlib.

Versions 1.0.0 used its own look-up table, which does not match the one of Perez et al. (1992); it is kept in the code (`legacy_dirint=True`) only to reproduce results published with that version.

The modified clearness index corrects for geometric air mass effects:

$$Kt' = \frac{Kt}{1.031 \cdot e^{-1.4/(0.9 + 9.4/AM)} + 0.1}$$

### Erbs et al. (1982)

The Erbs model uses a piecewise polynomial for the diffuse fraction Kd = DHI/GHI as a function of the clearness index Kt:

$$K_d = \begin{cases} 1 - 0.09\,Kt & Kt \leq 0.22 \\ 0.9511 - 0.1604\,Kt + 4.388\,Kt^2 - 16.638\,Kt^3 + 12.336\,Kt^4 & 0.22 < Kt \leq 0.80 \\ 0.165 & Kt > 0.80 \end{cases}$$

### Solar Geometry

Solar position is calculated with the formulas of Spencer (1971) and Cooper (1969) (see `solar_geometry.py`). The cos(Z) used for Kt calculation is the analytical integral over each hourly interval, consistent with the convention used in building energy simulation tools.

---

## Citation

If you use Solar Decomp in your research, please cite:

```bibtex
@software{barea_ganem_2026_solar_decomp,
  author       = {Barea, Gustavo and Ganem, Carolina},
  title        = {Solar Decomp: GHI to DNI+DHI solar irradiance decomposition},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20262706},
  url          = {https://github.com/gbarea-INAHE/solar_decomp},
  orcid        = {0000-0002-5643-3206}
}
```

See also [`CITATION.cff`](CITATION.cff) for the machine-readable citation file.

**Analysis scripts and data.** The scripts and derived data of the consistency study that uses this tool (IWEC2 weather files and ground measurements) are in a separate repository, [solar_decomp_analysis](https://github.com/gbarea-INAHE/solar_decomp_analysis) (DOI [10.5281/zenodo.23405259](https://doi.org/10.5281/zenodo.23405259); all versions: [10.5281/zenodo.23405258](https://doi.org/10.5281/zenodo.23405258)).

---

## References

- Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. *ASHRAE Transactions*, 98(1), 354–369.
- Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation. *Solar Energy*, 28(4), 293–302. https://doi.org/10.1016/0038-092X(82)90302-4
- Kasten, F., & Young, A.T. (1989). Revised optical air mass tables and approximation formula. *Applied Optics*, 28(22), 4735–4738.
- Spencer, J.W. (1971). Fourier series representation of the position of the sun. *Search*, 2(5), 172.
- Cooper, P.I. (1969). The absorption of radiation in solar stills. *Solar Energy*, 12(3), 333–346.
- Leckner, B. (1978). The spectral distribution of solar radiation at the Earth's surface. *Solar Energy*, 20(2), 143–150.

---

## License

This project is released under the [MIT License](LICENSE).

&copy; 2026 Gustavo Barea — INAHE-CONICET
