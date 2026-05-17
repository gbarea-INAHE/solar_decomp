#!/bin/bash
echo "Instalando dependencias..."
pip install streamlit pandas numpy plotly openpyxl --quiet
echo "Iniciando Solar Decomp..."
streamlit run app_solar.py
