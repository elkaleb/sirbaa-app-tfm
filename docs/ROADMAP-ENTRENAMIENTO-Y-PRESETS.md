# Roadmap — Presets, reanálisis y entrenamiento progresivo

Fecha: 2026-07-15

## Objetivo

Convertir la app de validación de lances en un sistema cada vez más repetible y más inteligente conforme se analizan archivos reales.

La evolución recomendada tiene tres etapas:

1. **Presets reproducibles** — guardar/cargar parámetros que funcionaron para un archivo, sensor o pesquería.
2. **Dataset de validación** — registrar decisiones humanas sobre segmentos detectados: lance real, falso positivo, fragmentación, lance observado no detectado.
3. **Modelo entrenable** — usar esos ejemplos validados para aprender reglas/patrones y mejorar la detección.

---

## 1. Presets reproducibles

Estado: **implementado en UI** como primera fase.

Los presets se guardan como JSON locales en:

```text
data/presets/
```

La interfaz permite:

- cargar un preset guardado,
- aplicar sus parámetros ML,
- guardar la configuración actual con nombre y notas,
- mantener la trazabilidad en el JSON del preset y, más adelante, en metadata separada de corridas.

### Qué problema resuelven

Actualmente los parámetros ML se ajustan visualmente en la UI. Eso ayuda a explorar, pero si se quiere repetir un análisis después, hace falta guardar exactamente qué configuración produjo cierto resultado.

### Qué debe guardar un preset

Un preset debería incluir:

```json
{
  "preset_name": "merluza_sensor_edf_v1",
  "created_at": "2026-07-15T00:00:00Z",
  "description": "Parámetros que funcionaron para un sensor y pesquería específicos",
  "context": {
    "pesqueria": "Merluza",
    "sensor_tipo": "EDF",
    "archivo_sensor": "sensor_ejemplo.csv",
    "archivo_lances": "lances_ejemplo.csv"
  },
  "ml_params": {
    "n_clusters": 3,
    "rolling_window": 5,
    "smoothing_window": 3,
    "merge_gap_minutes": 15,
    "context_window_minutes": 60,
    "min_segment_points": 5
  },
  "notes": "Detecta 8 segmentos y coincide bien con lances observados."
}
```

### Cómo se usaría

En la UI:

- botón **Guardar preset actual**,
- selector **Cargar preset**,
- botón **Aplicar preset y reanalizar**.

Esto permite reanalizar datos de forma rápida y repetible.

### Ventaja

Antes de entrenar un modelo, los presets ya crean trazabilidad:

- qué parámetros se usaron,
- en qué archivo funcionaron,
- con qué notas del analista,
- qué resultados generaron.

---

## 2. Dataset de validación humana

### Por qué es necesario

Para “entrenar” de verdad, la app necesita ejemplos etiquetados. K-Means no aprende de decisiones pasadas; solo agrupa el archivo actual.

El aprendizaje aparece cuando guardamos decisiones humanas como:

- este segmento ML sí fue lance real,
- este segmento ML fue falso positivo,
- este lance observado no fue detectado por ML,
- este lance fue fragmentado en varios segmentos,
- estos dos segmentos deberían unirse.

### Qué guardar por cada segmento ML

Cada segmento detectado puede convertirse en una fila de entrenamiento:

```text
archivo_id
segment_id
start_ts
end_ts
duration_min
n_points
mean_temp
median_temp
min_temp
max_temp
delta_temp
std_temp
q1_temp
q3_temp
iqr_temp
env_mean_temp
env_contrast_temp
env_before_mean_temp
env_after_mean_temp
env_n_points
ml_params_json
observed_overlap_min
observed_overlap_ratio
human_label
human_notes
validated_by
validated_at
```

### Etiquetas sugeridas

Para empezar, etiquetas simples:

- `lance_valido`
- `falso_positivo`
- `fragmento_de_lance`
- `lance_no_detectado`
- `dudoso`

También se puede guardar una columna booleana inicial:

```text
is_true_lance = 1 / 0 / null
```

Y una razón:

```text
validation_reason = "coincide con observador", "duracion corta", "sin contraste", etc.
```

### Dónde guardar

Opciones:

1. **CSV/Parquet local** en `data/validation/`
   - simple,
   - versionable parcialmente,
   - suficiente para MVP.

2. **SQLite**
   - mejor para acumular validaciones,
   - fácil de consultar,
   - durable y portable.

3. **BigQuery / base central**
   - útil cuando haya más usuarios/analistas,
   - mejor para dashboards y análisis histórico.

Recomendación inicial: **SQLite + export CSV**.

---

## 3. Cómo se puede “entrenar” el sistema

Hay varios niveles de entrenamiento. Conviene avanzar de menor a mayor complejidad.

## Nivel A — Reglas calibradas por datos validados

Antes de entrenar un modelo complejo, se pueden aprender rangos típicos:

- duración típica de lances reales,
- contraste mínimo usual,
- delta térmico típico,
- número mínimo de lecturas confiables,
- rangos normales de `std_temp` e `iqr_temp`.

La app podría calcular automáticamente, por pesquería/sensor:

```text
lances reales suelen tener:
- duration_min entre P10 y P90
- env_contrast_temp mayor que P25
- n_points mayor que P10
```

Ventaja:

- explicable,
- fácil de auditar,
- compatible con el enfoque actual.

## Nivel B — Clasificador supervisado de segmentos

Cuando existan suficientes segmentos validados, se puede entrenar un modelo que diga:

```text
probabilidad de que este segmento ML sea lance real
```

Modelos candidatos:

- Logistic Regression — simple y explicable.
- Random Forest — robusto con relaciones no lineales.
- Gradient Boosting / XGBoost / LightGBM — potente si hay suficientes datos.

Variables de entrada:

- duración,
- n_points,
- mean/median/min/max,
- delta,
- std,
- IQR,
- contraste contra entorno,
- diferencia antes/después,
- parámetros ML usados,
- overlap con observador cuando exista.

Salida:

```text
true_lance_probability = 0.87
predicted_label = lance_valido
model_reason = contraste alto + duración normal + suficientes puntos
```

## Nivel C — Modelo de secuencia

Más adelante, en lugar de clasificar segmentos ya detectados, se podría entrenar un modelo sobre la serie temporal completa.

Opciones:

- detección de cambios de régimen,
- Hidden Markov Models,
- modelos supervisados por ventana temporal,
- redes temporales si hubiera muchos datos.

No es la primera recomendación porque requiere más datos y es menos explicable.

---

## 4. Estrategia recomendada

### Fase 1 — Presets + trazabilidad

Implementar:

- guardar/cargar presets JSON,
- registrar qué preset se usó en cada reporte,
- guardar `preset_name` y `ml_params_json` en metadata separada de corrida, no en la tabla analítica principal.

### Fase 2 — Validación humana en UI

Agregar una sección para cada segmento ML:

- etiqueta humana,
- notas,
- botón **Guardar validación**.

También para lances observados:

- marcar si está bien detectado,
- marcar si no tiene señal térmica,
- notas de desfase o problemas.

### Fase 3 — Dataset acumulado

Guardar validaciones en SQLite:

```text
data/validation/sirbaa_lance_validation.sqlite
```

Tablas sugeridas:

- `analysis_runs`
- `presets`
- `ml_segments`
- `observed_lances`
- `human_validations`

### Fase 4 — Entrenamiento inicial

Con suficientes datos:

- entrenar clasificador simple,
- validar con separación train/test por archivo o viaje,
- reportar métricas:
  - precision,
  - recall,
  - F1,
  - matriz de confusión.

Importante: separar por viaje/archivo evita que el modelo “memorice” un archivo.

### Fase 5 — Integración en app

Mostrar en UI:

- probabilidad de lance real,
- etiqueta sugerida,
- razones principales,
- comparación contra validación humana.

---

## 5. Criterio práctico para saber cuándo entrenar

No conviene entrenar demasiado pronto.

Señal mínima recomendada:

- al menos 100–200 segmentos ML validados,
- varios archivos/viajes,
- ejemplos de falsos positivos,
- ejemplos de lances válidos,
- diferentes sensores o condiciones si aplican.

Antes de eso, conviene usar:

- presets,
- reglas explicables,
- reportes de validación.

---

## 6. Riesgos y cuidados

### Riesgo: sobreajuste a un archivo

Si se entrena con pocos archivos, el modelo puede aprender patrones específicos de ese viaje.

Mitigación:

- dividir train/test por archivo,
- guardar contexto de pesquería/sensor,
- revisar métricas por grupo.

### Riesgo: etiquetas inconsistentes

Dos analistas pueden etiquetar distinto.

Mitigación:

- definir glosario de etiquetas,
- guardar notas,
- permitir `dudoso`,
- revisar desacuerdos.

### Riesgo: perder explicabilidad

Modelos más complejos pueden ser menos claros.

Mitigación:

- empezar con reglas y modelos simples,
- mantener columnas de razón/sugerencia,
- mostrar evidencia visual y estadística.

---

## Recomendación final

La mejor ruta es:

1. **Guardar/cargar presets** para repetir análisis.
2. **Guardar validaciones humanas** por segmento/lance.
3. **Construir dataset acumulado**.
4. **Aprender reglas calibradas** por pesquería/sensor.
5. **Entrenar clasificador supervisado** cuando haya suficientes ejemplos.

Así la app mejora de forma gradual, auditable y útil para el analista, sin convertir el ML en una caja negra demasiado pronto.
