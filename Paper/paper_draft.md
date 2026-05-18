# Decomposition of Global Horizontal Irradiance into Direct Normal and Diffuse Horizontal Irradiance for Argentine Climates: A Systematic Validation of Three Empirical Models Using TMY Data from 41 Cities

**Authors:** Gustavo Barea Paci¹, Carolina Ganem¹

¹ Instituto de Ambiente, Hábitat y Energía (INAHE-CONICET), Mendoza, Argentina.

**Corresponding author:** gbarea@mendoza-conicet.gob.ar

**Proposed journal:** *Solar Energy* / *Renewable Energy* / *Energy and Buildings*

**Keywords:** solar irradiance decomposition; DIRINT; Erbs model; Reindl-2; DNI; DHI; Argentina; Köppen-Geiger; IRAM 11603; building energy simulation

---

## Abstract

Decomposition models that estimate direct normal irradiance (DNI) and diffuse horizontal irradiance (DHI) from global horizontal irradiance (GHI) are essential tools for building energy simulation and solar resource assessment in regions where only GHI is routinely measured. This study presents a systematic validation of three widely used decomposition models — DIRINT (Perez et al., 1992), Erbs (Erbs et al., 1982), and Reindl-2 (Reindl et al., 1990) — against Typical Meteorological Year (TMY) reference data from 41 Argentine cities spanning latitudes 22.6°S to 54.8°S and eight Köppen-Geiger climate classes. The analysis was conducted using the open-source Solar Decomp software, which implements an analytical solar geometry engine based on Spencer (1971) and Cooper (1969). Results show that the Reindl-2 model achieves the best DNI estimation in 39 of 41 cities (R² = 0.923 ± 0.026; nRMSE = 21.5%; MBE = −19.5 W/m²), while Erbs yields the lowest DHI errors (R² = 0.978 ± 0.015; RMSE = 16.3 W/m²). DIRINT systematically overestimates DNI (MBE = +97 W/m²) in persistently clear-sky climates, limiting its applicability across most of Argentina's territory. Model performance correlates negatively with the mean clearness index (Kt), indicating that greater atmospheric variability improves decomposition accuracy. The Solar Decomp tool and all validation scripts are publicly available at https://github.com/gbarea-INAHE/solar_decomp.

---

## 1. Introduction

Accurate knowledge of the solar radiation components — global horizontal irradiance (GHI), direct normal irradiance (DNI), and diffuse horizontal irradiance (DHI) — is fundamental for building energy simulation, solar collector design, and urban thermal comfort assessment. However, routine meteorological networks in Argentina, as in most of Latin America, measure only GHI. DNI and DHI are rarely available from direct measurements, creating a systematic gap between the data collected by weather stations and the multi-component radiation inputs required by simulation software such as EnergyPlus, DesignBuilder, or TRNSYS.

Typical Meteorological Year (TMY) files in EnergyPlus Weather (EPW) format — the standard input for building energy simulation — include DNI and DHI values, but these are generally estimated from GHI using decomposition models or satellite-derived products rather than direct pyranometer measurements (Wilcox and Marion, 2008; Sengupta et al., 2018). When practitioners apply EPW files to their simulation workflows, they implicitly accept the decomposition methodology embedded in those files. Understanding the accuracy of different decomposition approaches across the diverse climatic regions of Argentina is therefore directly relevant to the quality of energy simulation results.

Empirical GHI decomposition models estimate the diffuse fraction (K_d = DHI/GHI) or the beam transmittance (K_n = DNI/G₀ₙ) as a function of the clearness index (K_t = GHI/G₀h) and additional predictors such as solar elevation, precipitable water, or short-term variability of K_t. The three models evaluated in this study represent the most widely cited approaches in the literature:

- **DIRINT** (Perez et al., 1992): uses a three-dimensional lookup table indexed by precipitable water W, modified clearness index K_t', and hourly K_t' variability (ΔK_t'). It is generally considered the most physically detailed of the three.
- **Erbs** (Erbs et al., 1982): estimates K_d as a piecewise polynomial function of K_t. Requires no auxiliary meteorological data beyond GHI and solar geometry.
- **Reindl-2** (Reindl et al., 1990): extends the Erbs approach by incorporating the solar elevation angle sin(α), improving performance under low-sun conditions.

Previous validation studies have been conducted primarily for North American, European, and East Asian climates (Ineichen, 2008; Gueymard and Ruiz-Arias, 2016; Starke et al., 2018). Systematic validation for South American climates, particularly across the full latitudinal and climatic diversity of Argentina — from subtropical NOA (22°S) to sub-Antarctic Ushuaia (54°S), and from hyperarid Atacama-adjacent deserts to humid Mesopotamia — remains limited. This study addresses that gap.

The specific objectives of this work are:
1. To validate DIRINT, Erbs, and Reindl-2 against TMY reference data for 41 Argentine cities using standardized statistical metrics.
2. To identify the optimal decomposition model for each Köppen-Geiger climate class and IRAM 11603 thermal zone represented in Argentina.
3. To quantify the relationship between model performance and climate aridity (expressed via mean K_t).
4. To provide model selection guidelines for practitioners using Solar Decomp or equivalent tools in Argentine building and solar energy applications.

---

## 2. Data and Methods

### 2.1 Study Sites

The validation dataset comprises 41 meteorological stations distributed across Argentina (22.6°S–54.8°S, 53.9°W–73.0°W), covering eight Köppen-Geiger climate classes and all six IRAM 11603 thermal zones (Table 1). Stations are located at official aerodrome weather sites, ensuring data quality and representativeness of regional climate conditions. Elevation ranges from 6 m (Buenos Aires Aeroparque) to 1,425 m (Malargüe). The full list of stations with geographic coordinates, altitude, and climate classification is provided in the Supplementary Material.

**Table 1.** Distribution of study sites by Köppen-Geiger climate class and IRAM 11603 thermal zone.

| Köppen class | Description | N cities | IRAM zones |
|---|---|---|---|
| Aw | Tropical savanna | 3 | I |
| BSh | Hot steppe | 2 | I–II |
| BSk | Cold steppe | 14 | II–V |
| BWh | Hot desert | 1 | III |
| BWk | Cold desert | 5 | III–IV |
| Cfa | Humid subtropical | 14 | I–III |
| Cfb | Oceanic temperate | 1 | V |
| ET | Tundra / polar | 1 | VI |

### 2.2 Reference Data

TMY data in EPW format were obtained from the IWEC2 (International Weather for Energy Calculations, version 2) dataset (Thevenard and Brunger, 2002), compiled from WMO observation records covering the period 1984–2008 (generally). EPW files provide hourly values of GHI, DNI, and DHI in Wh/m² (equivalent to W/m² average over the hour). It must be noted that EPW reference DNI and DHI values are themselves model-derived in most cases — they are typically estimated from GHI using the DISC or Erbs model during TMY construction — rather than direct pyrheliometer measurements. This circularity imposes a methodological limitation discussed in Section 4.3.

### 2.3 Solar Geometry

Solar position and radiation geometry were computed using the analytical model of Spencer (1971) for the equation of time and Cooper (1969) for solar declination:

**Declination:**
$$\delta = 23.45° \cdot \sin\!\left(\frac{360°(284 + \text{DOY})}{365}\right)$$

**Equation of time (Spencer, 1971):**
$$\text{EoT} = 9.87\sin(2B) - 7.53\cos B - 1.5\sin B \quad [min]$$

where B = 360°(DOY − 81)/364.

The average cosine of the zenith angle over each hourly interval was computed analytically by integrating cos(Z) over ±7.5° of hour angle around the interval center, consistent with the approach used in building energy simulation tools. Air mass was estimated using the Kasten and Young (1989) formula; precipitable water was approximated from temperature and atmospheric pressure following Leckner (1978).

### 2.4 Decomposition Models

#### 2.4.1 DIRINT (Perez et al., 1992)

DIRINT estimates the beam transmittance K_n = DNI/G₀ₙ using a three-dimensional lookup table indexed by precipitable water W [cm] (4 bins), modified clearness index K_t' (11 bins with linear interpolation), and hourly K_t' variability ΔK_t' (5 bins). The modified clearness index corrects K_t for air mass effects:

$$K_t' = \frac{K_t}{1.031 \cdot e^{-1.4/(0.9 + 9.4/AM)} + 0.1}$$

#### 2.4.2 Erbs et al. (1982)

The Erbs model estimates the diffuse fraction K_d = DHI/GHI as a piecewise polynomial:

$$K_d = \begin{cases} 1 - 0.09\,K_t & K_t \leq 0.22 \\ 0.9511 - 0.1604\,K_t + 4.388\,K_t^2 - 16.638\,K_t^3 + 12.336\,K_t^4 & 0.22 < K_t \leq 0.80 \\ 0.165 & K_t > 0.80 \end{cases}$$

#### 2.4.3 Reindl-2 (Reindl et al., 1990)

Reindl-2 incorporates solar elevation as an additional predictor:

$$K_d = \begin{cases} 1 - 0.232\,K_t & K_t \leq 0.30 \\ 1.329 - 1.716\,K_t + (0.267 - 0.357\sin\alpha) & 0.30 < K_t \leq 0.78 \\ 0.426\,K_t - 0.256\sin\alpha + 0.118 & K_t > 0.78 \end{cases}$$

### 2.5 Validation Metrics

Model performance was assessed using four standard metrics computed on all daytime hours (GHI ≥ 10 W/m²) for each city–model combination:

$$\text{RMSE} = \sqrt{\frac{1}{N}\sum(y_i - \hat{y}_i)^2}$$

$$\text{MBE} = \frac{1}{N}\sum(y_i - \hat{y}_i) \quad [\text{positive = overestimate}]$$

$$R^2 = 1 - \frac{\sum(y_i - \hat{y}_i)^2}{\sum(y_i - \bar{y})^2}$$

$$\text{nRMSE} = \frac{\text{RMSE}}{\bar{y}} \times 100\,\%$$

The total validation dataset comprises 352,330 hourly observations across 41 cities and three models.

---

## 3. Results

### 3.1 Global Performance

Table 2 summarizes the mean validation statistics across all 41 cities.

**Table 2.** Mean validation statistics for DNI and DHI across 41 Argentine cities (mean ± std over cities).

| Model | DNI R² | DNI RMSE (W/m²) | DNI MBE (W/m²) | DNI nRMSE (%) | DHI R² | DHI RMSE (W/m²) | DHI MBE (W/m²) |
|---|---|---|---|---|---|---|---|
| DIRINT | 0.436 ± 0.173 | 186.8 | +97.0 | 58.5 | 0.787 ± 0.062 | 51.7 | −30.0 |
| Erbs | 0.904 ± 0.035 | 77.2 | −18.0 | 24.0 | **0.978 ± 0.015** | **16.3** | +2.7 |
| Reindl-2 | **0.923 ± 0.026** | **69.5** | −19.5 | **21.5** | 0.960 ± 0.027 | 21.7 | +12.0 |

Reindl-2 achieves the best overall DNI accuracy, surpassing Erbs by 0.019 R² units and reducing RMSE by 7.7 W/m² (10%). For DHI, Erbs performs marginally better (RMSE 16.3 vs. 21.7 W/m²), indicating that the additional sin(α) term in Reindl-2 introduces a small positive bias in the diffuse component. DIRINT exhibits severe systematic overestimation of DNI (MBE = +97.0 W/m²), consistent with its known limitation in persistently clear-sky climates where low ΔK_t' values force the model into low-variability bins with inflated K_n values.

The Taylor Diagram (Figure 7) illustrates these results spatially: DIRINT points scatter widely around angles of 20°–40° (R ≈ 0.7–0.9) with standard deviations exceeding 1.4σ_obs, while Erbs and Reindl-2 cluster near the reference point (R > 0.95, σ_pred ≈ σ_obs).

### 3.2 City-Level Performance

Reindl-2 ranked as the best model for DNI in 39 of 41 cities (95.1%). Erbs was preferred only for Andalgalá (R² = 0.950) and Viedma (R² = 0.919). The best overall performance was found for General Pico (La Pampa, R² = 0.964, nRMSE = 17.1%), and the weakest for Ushuaia (Tierra del Fuego, R² = 0.868, nRMSE = 31.4%) and Río Gallegos (R² = 0.869, nRMSE = 29.7%). The full city-level results are shown in Figure 4 (heatmap) and Figure 5 (nRMSE bars).

### 3.3 Performance by Climate Zone

**Table 3.** Mean Reindl-2 DNI performance by Köppen-Geiger class (ordered by mean R²).

| Köppen | Description | N | R² | nRMSE (%) | MBE (W/m²) |
|---|---|---|---|---|---|
| Cfa | Humid subtropical | 14 | 0.942 ± 0.010 | 20.2 | −17.9 |
| Aw | Tropical savanna | 3 | 0.939 ± 0.006 | 23.7 | −12.7 |
| BSh | Hot steppe | 2 | 0.923 ± 0.010 | 26.2 | −14.3 |
| BSk | Cold steppe | 14 | 0.918 ± 0.026 | 21.5 | −19.6 |
| BWk | Cold desert | 5 | 0.902 ± 0.023 | 20.2 | −26.8 |
| Cfb | Oceanic temperate | 1 | 0.901 | 23.6 | −18.3 |
| BWh | Hot desert | 1 | 0.897 | 23.8 | −13.7 |
| ET | Tundra | 1 | 0.868 | 31.4 | −18.7 |

Humid subtropical (Cfa) and tropical savanna (Aw) climates yield the highest accuracy, likely because the higher atmospheric variability in these regions creates a wider range of K_t values, improving the statistical conditioning of the diffuse fraction regression. Conversely, polar/subantarctic climates (ET, dominated by Ushuaia) show the highest relative errors, attributable to extreme low-sun angles and frequent mixed-phase precipitation that violates the clear-sky scaling assumptions of the model.

All models show a negative MBE for DNI (underestimation tendency), except DIRINT. Cold desert climates (BWk: Mendoza, San Juan, San Rafael, Malargüe, Trelew) present the largest underestimation bias (MBE = −26.8 W/m²), suggesting that the empirical coefficients of Reindl-2, calibrated primarily on Northern Hemisphere data, may be slightly miscalibrated for the high-irradiance, low-humidity desert conditions of western Argentina.

### 3.4 Seasonal Bias Patterns

The monthly MBE heatmap (Figure 8) reveals systematic seasonal patterns that are consistent across climate zones:

- **Northern Argentina (NOA/NEA, latitudes 22°–30°S):** near-zero or slightly negative MBE throughout the year, with the least bias in summer (DJF).
- **Central Argentina (30°–40°S):** moderate negative MBE in winter months (JJA), with MBE values reaching −40 to −60 W/m² in June–July for cities such as Córdoba, Mendoza, and San Luis. This pattern suggests the model underestimates DNI when solar elevation is low and the probability of cloud-free conditions is high.
- **Patagonia (40°–55°S):** large and variable MBE throughout the year, reflecting the high interannual meteorological variability of this region in the EPW TMY data.

### 3.5 Model Performance vs. Climate Aridity

Figure 9 shows the relationship between Reindl-2 R² and mean annual clearness index (K_t) across 41 cities. A negative trend (slope = −0.08 per unit K_t) indicates that model accuracy decreases as climates become more arid (higher K_t). This is consistent with the theoretical argument that decomposition models are better constrained when the full range of cloudy-to-clear conditions is represented: in persistently clear climates, K_t concentrates near 0.6–0.7 and the model operates near its extrapolation boundary. Notable exceptions include General Pico (BSk, K_t ≈ 0.49, best R²) and Andalgalá (BWk, K_t ≈ 0.55, where Erbs slightly outperforms Reindl-2), suggesting local atmospheric conditions may modulate the relationship.

---

## 4. Discussion

### 4.1 Reindl-2 as the Recommended Model for Argentina

The consistent superiority of Reindl-2 across 95% of Argentine cities constitutes robust evidence for its adoption as the default decomposition model in Solar Decomp and comparable tools applied to Argentine conditions. The incorporation of sin(α) provides a physically motivated correction for the geometric effect of low sun angles on the partitioning between beam and diffuse radiation — an effect that is particularly relevant at the high latitudes of Patagonia and during winter in central Argentina.

The modest but consistent advantage over Erbs (ΔR² ≈ 0.019 for DNI) is practically meaningful: for a typical site in Buenos Aires (annual GHI ≈ 1,600 kWh/m²), the difference in RMSE (77.2 vs. 69.5 W/m²) translates to a reduction in hourly DNI uncertainty of approximately 7.7 W/m², which propagates to reduced uncertainty in annual solar gains in building façades and collector surfaces.

For DHI estimation, practitioners requiring maximum accuracy should note that Erbs provides marginally lower RMSE (16.3 vs. 21.7 W/m²). In building energy simulation contexts where overheating risk depends strongly on diffuse gains through glazing, Erbs may be preferable for DHI-sensitive applications.

### 4.2 DIRINT Performance and Structural Limitations

The substantially lower performance of DIRINT relative to Erbs and Reindl-2 in this evaluation (mean R² = 0.436 vs. 0.904–0.923) merits careful interpretation. DIRINT's three-dimensional structure makes it sensitive to the distribution of ΔK_t' values: in persistently clear-sky climates (typical of Argentina's arid west and northwest), low ΔK_t' dominates the input distribution, forcing the model into low-variability bins with large K_n values and consequently overestimating DNI systematically (MBE = +97.0 W/m²).

This finding is consistent with prior assessments by Ineichen (2008) and Gueymard and Ruiz-Arias (2016), who noted that DIRINT was originally calibrated on highly variable, cloud-rich climates in the northeastern United States and western Europe, and may require recalibration for persistently clear-sky conditions. For users in regions where DIRINT is currently the default (e.g., pvlib-python), this study provides evidence that Reindl-2 should be preferred for Argentine site conditions.

### 4.3 Methodological Limitations

Several limitations of this study must be acknowledged:

1. **Reference data circularity.** IWEC2 EPW reference DNI/DHI values are model-derived (typically from the DISC or Erbs model during TMY construction), not direct pyrheliometer measurements. Consequently, Erbs-based models may show artificially high agreement against EPW reference values. For a fully independent validation, measured DNI data from pyrheliometers (e.g., AERONET or BSRN stations) would be required. The authors plan to address this in future work using data from the Argentine National Meteorological Service (SMN) and CONICET's radiometric network.

2. **Single-year TMY.** EPW files represent a TMY derived from approximately 25 years of data. Interannual variability — particularly relevant in ENSO-affected regions of northern Argentina — is not captured.

3. **Sub-hourly dynamics.** All three models are implemented at hourly resolution. Sub-hourly cloud enhancement events and rapid K_t variability are not resolved, which may underestimate RMSE relative to high-frequency validation datasets.

4. **Spatial representativeness.** The 41 stations are predominantly located at airports, which tend to be in suburban or peri-urban environments. Urban heat island and local aerosol effects at inner-city sites are not captured.

---

## 5. Conclusions

This study presents the first systematic validation of three GHI decomposition models against TMY data from 41 Argentine cities, spanning 32° of latitude and eight Köppen-Geiger climate classes. The main conclusions are:

1. **Reindl-2 is the optimal model for DNI estimation** across 95.1% of Argentine cities (39/41), with a mean R² = 0.923 ± 0.026 and nRMSE = 21.5%. Its sin(α) term provides a physically consistent improvement over Erbs under low-sun-angle conditions.

2. **Erbs is preferred for DHI** (R² = 0.978 ± 0.015, RMSE = 16.3 W/m²) and constitutes the best overall choice when maximum DHI accuracy is required, or as a robust fallback when temperature data for precipitable water estimation are unavailable.

3. **DIRINT systematically overestimates DNI** (MBE = +97.0 W/m²) across most Argentine climates due to structural limitations of its ΔK_t' binning in persistently clear-sky conditions. Its use is not recommended as a default model for Argentine applications.

4. **Model performance correlates negatively with climate aridity** (slope = −0.08 per unit K_t): humid subtropical (Cfa) and tropical (Aw) climates yield the highest accuracy, while cold desert (BWk) and polar (ET) climates present the largest errors.

5. **Seasonal bias analysis** reveals systematic winter underestimation of DNI in central Argentina (30°–40°S), suggesting that future recalibration efforts should target winter clear-sky conditions in this region.

These results provide actionable model selection guidelines for practitioners and researchers using building energy simulation in Argentina, and establish a reproducible benchmark for future validation studies using direct radiometric measurements.

---

## Software Availability

Solar Decomp is freely available at:

> **https://github.com/gbarea-INAHE/solar_decomp**

DOI: 10.5281/zenodo.20262707

The EPW validation scripts ([`Paper/validate_epw_batch.py`](https://github.com/gbarea-INAHE/solar_decomp/blob/main/Paper/validate_epw_batch.py)) and figure generation code ([`Paper/generate_figures.py`](https://github.com/gbarea-INAHE/solar_decomp/blob/main/Paper/generate_figures.py)) are included in the repository to ensure full reproducibility of all results presented here.

---

## Acknowledgements

The authors acknowledge [SMN / CONICET / funding agency]. EPW data from the IWEC2 dataset provided through the EnergyPlus Weather Data portal (U.S. Department of Energy). Solar Decomp development was supported by INAHE-CONICET, Mendoza, Argentina.

---

## References

1. Cooper, P.I. (1969). The absorption of radiation in solar stills. *Solar Energy*, 12(3), 333–346. https://doi.org/10.1016/0038-092X(69)90047-4
2. Erbs, D.G., Klein, S.A., & Duffie, J.A. (1982). Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation. *Solar Energy*, 28(4), 293–302. https://doi.org/10.1016/0038-092X(82)90302-4
3. Gueymard, C.A., & Ruiz-Arias, J.A. (2016). Extensive worldwide validation and climate sensitivity analysis of direct irradiance predictions from 1-min global irradiance. *Solar Energy*, 128, 1–30. https://doi.org/10.1016/j.solener.2015.10.010
4. Ineichen, P. (2008). Comparison and validation of three global-to-beam irradiance models against ground measurements. *Solar Energy*, 82(6), 501–512. https://doi.org/10.1016/j.solener.2007.12.006
5. Kasten, F., & Young, A.T. (1989). Revised optical air mass tables and approximation formula. *Applied Optics*, 28(22), 4735–4738. https://doi.org/10.1364/AO.28.004735
6. Leckner, B. (1978). The spectral distribution of solar radiation at the Earth's surface — elements of a model. *Solar Energy*, 20(2), 143–150. https://doi.org/10.1016/0038-092X(78)90187-1
7. Perez, R., Ineichen, P., Maxwell, E., Seals, R., & Zelenka, A. (1992). Dynamic global-to-direct irradiance conversion models. *ASHRAE Transactions*, 98(1), 354–369.
8. Reindl, D.T., Beckman, W.A., & Duffie, J.A. (1990). Diffuse fraction correlations. *Solar Energy*, 45(1), 1–7. https://doi.org/10.1016/0038-092X(90)90060-P
9. Sengupta, M., Xie, Y., Lopez, A., Habte, A., Maclaurin, G., & Shelby, J. (2018). The National Solar Radiation Data Base (NSRDB). *Renewable and Sustainable Energy Reviews*, 89, 51–60. https://doi.org/10.1016/j.rser.2018.03.003
10. Spencer, J.W. (1971). Fourier series representation of the position of the sun. *Search*, 2(5), 172.
11. Starke, A.R., Lemos, L.F.L., Boland, J., Cardemil, J.M., & Colle, S. (2018). Resolution of the cloud enhancement problem for one-minute diffuse radiation prediction. *Renewable Energy*, 125, 472–484. https://doi.org/10.1016/j.renene.2018.02.107
12. Thevenard, D., & Brunger, A. (2002). The development of typical weather years for international locations: Part I, algorithms. *ASHRAE Transactions*, 108(2), 376–383.
13. Wilcox, S., & Marion, W. (2008). *Users Manual for TMY3 Data Sets*. NREL/TP-581-43156. National Renewable Energy Laboratory, Golden, CO.

---

## Supplementary Material

**Table S1.** Full list of 41 study sites with geographic coordinates, altitude, data source, Köppen-Geiger classification, IRAM 11603 thermal zone, and number of valid daytime hours in the validation dataset.

*(to be generated from validation Excel)*

**Figures S1–S3.** Monthly R², RMSE, and MBE time series for all 41 cities × 3 models.

---

*Draft version — [DATE]. Prepared for submission to Solar Energy / Energy and Buildings.*
