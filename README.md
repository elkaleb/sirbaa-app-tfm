# SIRBAA Sensores Pipeline

Aplicación Streamlit para validar lances de pesca combinando:

- lances observados por analista,
- lecturas de temperatura de sensores,
- detección automática de segmentos candidatos con ML no supervisado,
- reporte comparativo con estadísticos térmicos y sugerencias de revisión.

La app está pensada como herramienta de apoyo para auditoría: no reemplaza el criterio del analista.

## Funcionalidades

- Carga de archivo de lances en CSV.
- Carga de sensores en CSV/XLSX.
- Detección automática de encabezado y separador CSV.
- Limpieza de columnas técnicas del logger.
- Cálculo de TFM y estadísticos por lance observado.
- Detección de lances candidatos desde temperatura con K-Means.
- Superposición visual de lances observados vs segmentos ML.
- Sugerencias explicables para revisar posibles falsos lances.
- Reporte integrado descargable: `reporte_lances_tfm_ml.csv`.
- Presets JSON de parámetros ML para repetir análisis.

## Estructura

```text
streamlit_app.py                  # App principal
src/sirbaa_pipeline/time_match.py # Lectura, limpieza y cruce temporal
src/sirbaa_pipeline/lance_ml.py   # Detección ML y métricas de segmentos
docs/UI-Y-EVALUACION.md          # Guía de uso y metodología
docs/ROADMAP-ENTRENAMIENTO-Y-PRESETS.md
requirements.txt
```

## Uso local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

También se incluyen scripts auxiliares:

```bash
./scripts/bootstrap_streamlit.sh
./scripts/run_streamlit.sh
```

## Publicación en Streamlit Community Cloud

1. Subir este repo a GitHub.
2. En Streamlit Community Cloud, crear una app nueva desde el repo.
3. Main file path: `streamlit_app.py`.
4. Python dependencies: `requirements.txt`.

No se incluyen datos reales en el repo. Los archivos se cargan desde la interfaz.

## Metodología

La detección ML usa K-Means sobre la serie de temperatura suavizada para separar estados térmicos sin umbrales fijos.

La validación se apoya en estadística descriptiva y robusta:

- promedio,
- mediana,
- mínimo/máximo,
- delta térmico,
- desviación estándar,
- cuartiles e IQR,
- contraste contra entorno térmico inmediato.

Referencias base:

- MacQueen, J. (1967). *Some Methods for Classification and Analysis of Multivariate Observations*.
- Lloyd, S. P. (1982). *Least Squares Quantization in PCM*.
- Tukey, J. W. (1977). *Exploratory Data Analysis*.

## Documentación

- [UI y evaluación](docs/UI-Y-EVALUACION.md)
- [Roadmap de entrenamiento y presets](docs/ROADMAP-ENTRENAMIENTO-Y-PRESETS.md)

## Privacidad de datos

Este repo público no debe contener archivos reales de sensores/lances, notebooks con rutas locales, presets con nombres de archivos sensibles ni outputs de análisis.
