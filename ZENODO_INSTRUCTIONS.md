# Instructivo: Publicación en Zenodo y generación de DOI

Este instructivo te guía paso a paso para obtener un DOI citable para Solar Decomp, vinculado a tu repositorio de GitHub.

---

## Paso 1 — Crear el repositorio en GitHub

1. Ingresar a [github.com](https://github.com) con tu cuenta **gbarea-INAHE**.
2. Hacer click en **"New repository"** (botón verde, esquina superior derecha).
3. Configurar:
   - **Repository name**: `solar_decomp`
   - **Description**: `GHI → DNI + DHI solar irradiance decomposition (DIRINT + Erbs)`
   - **Visibility**: Public (requerido para Zenodo gratuito)
   - Dejar desmarcado "Initialize this repository" (ya tenés el código)
4. Hacer click en **"Create repository"**.
5. En tu máquina local, desde la carpeta del proyecto:
   ```bash
   git init
   git add .
   git commit -m "Initial release v1.0.0"
   git branch -M main
   git remote add origin https://github.com/gbarea-INAHE/solar_decomp.git
   git push -u origin main
   ```

---

## Paso 2 — Crear un Release en GitHub (versión citable)

1. En tu repositorio de GitHub, hacer click en **"Releases"** (panel derecho).
2. Click en **"Create a new release"**.
3. En **"Choose a tag"**, escribir `v1.0.0` y seleccionar **"+ Create new tag: v1.0.0 on publish"**.
4. **Release title**: `Solar Decomp v1.0.0`
5. En la descripción pegar:
   ```
   First public release of Solar Decomp.
   
   GHI → DNI + DHI decomposition using DIRINT (Perez et al., 1992) and Erbs (1982) models.
   Supports 1-min, 15-min and 60-min solar radiation time series.
   Includes physical quality control and interactive Streamlit web interface.
   ```
6. Click en **"Publish release"**.

---

## Paso 3 — Conectar GitHub con Zenodo

1. Ir a [zenodo.org](https://zenodo.org) e ingresar con tu cuenta (o crear una con tu email institucional CONICET).
2. En el menú superior, hacer click en tu usuario → **"GitHub"**.
3. Verás la lista de tus repositorios de GitHub. Buscar `solar_decomp`.
4. Activar el **toggle** (interruptor) que aparece a la derecha del repositorio `solar_decomp`.
   - Esto habilita el "webhook" automático: cada nuevo Release de GitHub generará automáticamente un DOI en Zenodo.

> **Nota**: Si no ves el repositorio, hacer click en "Sync now" para actualizar la lista.

---

## Paso 4 — Obtener el DOI

Una vez activado el webhook:

1. Volver a GitHub y asegurarse de que el Release `v1.0.0` ya fue publicado (Paso 2).
2. Zenodo detectará automáticamente el Release y creará el registro.
3. Ir a [zenodo.org/account/settings/github](https://zenodo.org/account/settings/github) para verificar.
4. Hacer click en el repositorio `solar_decomp` para ver el registro de Zenodo.
5. El DOI tendrá el formato: `10.5281/zenodo.XXXXXXX`

---

## Paso 5 — Completar los metadatos en Zenodo

En el registro de Zenodo, hacer click en **"Edit"** para completar los metadatos:

| Campo | Valor |
|-------|-------|
| **Title** | Solar Decomp: GHI to DNI+DHI solar irradiance decomposition |
| **Authors** | Barea, Gustavo — INAHE-CONICET — ORCID: 0000-0002-5643-3206 |
| **Description** | (copiar el Abstract del CITATION.cff) |
| **Keywords** | solar irradiance, GHI decomposition, DNI, DHI, DIRINT, Erbs, solar energy |
| **License** | MIT License |
| **Version** | 1.0.0 |
| **Language** | English |
| **Resource type** | Software |
| **Related identifiers** | URL del repo GitHub (is_supplement_to) |

Hacer click en **"Save"** y luego **"Publish"**.

---

## Paso 6 — Actualizar el DOI en el código

Una vez que tengas el DOI real (ej. `10.5281/zenodo.1234567`):

1. Editar `README.md`: reemplazar `10.5281/zenodo.XXXXXXX` con el DOI real (2 apariciones).
2. Editar `CITATION.cff`: reemplazar `10.5281/zenodo.XXXXXXX` con el DOI real.
3. Hacer commit y push:
   ```bash
   git add README.md CITATION.cff
   git commit -m "Add Zenodo DOI"
   git push
   ```

---

## Paso 7 — Despliegue en Streamlit Community Cloud

1. Ir a [share.streamlit.io](https://share.streamlit.io) e ingresar con tu cuenta de GitHub.
2. Click en **"New app"**.
3. Configurar:
   - **Repository**: `gbarea-INAHE/solar_decomp`
   - **Branch**: `main`
   - **Main file path**: `app_solar.py`
4. Click en **"Deploy!"**
5. La app estará disponible en: `https://gbarea-inahe-solar-decomp-app-solar-XXXXX.streamlit.app`
   - Podés configurar una URL personalizada en **"Settings" → "General" → "App URL"**: `solar-decomp`

---

## Resumen del flujo

```
Código local  →  git push  →  GitHub repo
                                   |
                              GitHub Release v1.0.0
                                   |
                           Zenodo webhook (automático)
                                   |
                              DOI generado
                                   |
                         Actualizar README + CITATION.cff
```

---

## Versiones futuras

Para cada nueva versión del software:
1. Hacer los cambios en el código.
2. Actualizar el número de versión en `CITATION.cff`.
3. Crear un nuevo Release en GitHub (ej. `v1.1.0`).
4. Zenodo generará automáticamente un nuevo DOI para esa versión, pero mantendrá el DOI "concepto" que siempre apunta a la versión más reciente.

---

*Instructivo preparado para Solar Decomp — INAHE-CONICET, Mayo 2025.*
