# Solar Decomp — GHI → DNI + DHI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://solar-decomp.streamlit.app)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)

**Solar Decomp** is an open-source web application for decomposing global horizontal irradiance (GHI) time series into direct normal irradiance (DNI) and diffuse horizontal irradiance (DHI), using physically rigorous solar radiation models.

**Developed at** [INAHE-CONICET](https://www.mendoza-conicet.gob.ar/inahe/), Argentina.

---

## Live Application

The application is publicly available at:

> **[https://solar-decomp.streamlit.app](https://solar-decomp.streamlit.app)**

No installation required. Upload your CSV or Excel file and download results immediately.

---

## Features

- **Two decomposition models** running in parallel:
  - **DIRINT** (Perez et al., 1992): 3D lookup table [W × ΔKt' × Kt']; recommended for high-resolution data and variable climates.
  - **Erbs** (Erbs et al., 1982): piecewise polynomial Kd(Kt); robust fallback requiring no precipitable water data.
- **Automatic input detection**: column names (GHI, DNI, DHI, temperature, pressure), timestamp formats, and temporal resolution (1-min, 15-min, 60-min).
- **Solar geometry engine**: analytical integration of cos(Z) over hourly intervals (Yallop algorithm), air mass (Kasten & Young, 1989), and precipitable water estimation (Leckner, 1978).
- **Physical quality control**: 10 flag types + quality score (0–100) with configurable penalties.
- **Interactive visualizations**: time series, monthly energy bars, DIRINT vs Erbs scatter, clearness index histogram, quality score timeline.
- **Export**: CSV (full or minimal), Excel (data + quality report), JSON report.

---

## Input Format

| Column | Required | Description | Example names |
|--------|----------|-------------|---------------|
| Timestamp | **Yes** | Date and time (any standard format) | `timestamp`, `datetime`, `fecha`, `date` |
| GHI [W/m²] | **Yes** | Global horizontal irradiance | `GHI`, `global_horizontal_irradiance`, `swdown` |
| DNI [W/m²] | No | Direct normal irradiance (reference only) | `DNI`, `direct_normal_irradiance` |
| DHI [W/m²] | No | Diffuse horizontal irradiance (reference only) | `DHI`, `diffuse_horizontal_irradiance` |
| Temperature [°C] | No | Dry-bulb air temperature | `temp`, `temp_C`, `t2m` |
| Pressure [kPa/hPa] | No | Atmospheric pressure | `pressure`, `press_kPa` |

Supported timestamp formats include `YYYY-MM-DD HH:MM:SS`, `DD/MM/YYYY HH:MM`, and ISO 8601 variants.
Columns with separate `year`, `month`, `day`, `hour` fields are also supported.

A **downloadable template** (Excel + CSV) is available directly from the application sidebar.

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
| `W_cm` | Estimated precipitable water | cm |
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

**Requirements**: Python 3.9 or higher.

---

## Running Tests

```bash
python test_pipeline.py
```

The test suite performs an end-to-end verification using the included `test_data_15min.csv` (synthetic 15-min data for Buenos Aires, full year).

---

## Methods

### DIRINT — Perez et al. (1992)

The DIRINT model estimates DNI using a 3D lookup table indexed by:
- Precipitable water W [cm] (4 bins)
- Hourly variability of the modified clearness index ΔKt' (5 bins)
- Modified clearness index Kt' = Kt / f(AM) (11 bins)

The modified clearness index corrects for geometric air mass effects:

$$Kt' = \frac{Kt}{1.031 \cdot e^{-1.4/(0.9 + 9.4/AM)} + 0.1}$$

### Erbs et al. (1982)

The Erbs model uses a piecewise polynomial for the diffuse fraction Kd = DHI/GHI as a function of the clearness index Kt:

$$K_d = \begin{cases} 1 - 0.09\,Kt & Kt \leq 0.22 \\ 0.9511 - 0.1604\,Kt + 4.388\,Kt^2 - 16.638\,Kt^3 + 12.336\,Kt^4 & 0.22 < Kt \leq 0.80 \\ 0.165 & Kt > 0.80 \end{cases}$$

### Solar Geometry

Solar position is calculated using the Yallop (1992) algorithm. The cos(Z) used for Kt calculation is the analytical integral over each hourly interval, consistent with the convention used in building energy simulation tools.

---

## Citation

If you use Solar Decomp in your research, please cite:

```bibtex
@software{barea_solar_decomp_2025,
  author       = {Barea, Gustavo},
  title        = {Solar Decomp: GHI to DNI+DHI solar irradiance decomposition},
  year         = {2025},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://github.com/gbarea-INAHE/solar_decomp},
  orcid        = {0000-0002-5643-3206}
}
```

See also [`CITATION.cff`](CITATION.cff) for the machine-readable citation file.

---

## References

- Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. *ASHRAE Transactions*, 98(1), 354–369.
- Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation. *Solar Energy*, 28(4), 293–302. https://doi.org/10.1016/0038-092X(82)90302-4
- Kasten, F., & Young, A.T. (1989). Revised optical air mass tables and approximation formula. *Applied Optics*, 28(22), 4735–4738.
- Yallop, B.D. (1992). A method for calculating the frequency of occultation and transit of Venus and Mercury. *RGO NAO Technical Note No. 69*.
- Leckner, B. (1978). The spectral distribution of solar radiation at the Earth's surface. *Solar Energy*, 20(2), 143–150.

---

## License

This project is released under the [MIT License](LICENSE).

&copy; 2025 Gustavo Barea — INAHE-CONICET
