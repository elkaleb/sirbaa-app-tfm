# Actualización 2026-07-16 — Zoom y validación manual de segmentos ML

## Resumen

Se agregaron dos mejoras para la revisión visual y la construcción progresiva de datos de entrenamiento:

1. zoom/pan en la gráfica de temperatura,
2. validación manual de segmentos detectados por ML.

El objetivo es resolver un caso práctico: algunos archivos nuevos generan segmentos ML que visualmente no corresponden a lances reales y no siempre se eliminan ajustando presets.

## 1. Zoom/pan en la gráfica

La gráfica principal ahora permite explorar mejor la serie temporal.

Uso esperado:

- hacer zoom sobre un tramo específico de tiempo,
- desplazarse horizontalmente por la señal,
- revisar con más detalle si un segmento rojo corresponde a un evento real.

Esto ayuda especialmente cuando el archivo tiene muchos días, muchos lances o segmentos muy cercanos.

## 2. Validación manual del segmento ML

Se agregó una marca manual para el segmento ML seleccionado.

Opciones:

- `sin revisar`
- `sí es lance`
- `no es lance`
- `dudoso`

La marca aparece también como columna en la tabla de segmentos ML:

- `manual_validation`
- `include_in_report`

## 3. Qué pasa cuando se marca `no es lance`

Por defecto, los segmentos marcados como `no es lance` se excluyen del cruce observador ↔ ML y de las descargas filtradas.

Importante: **no se borran**.

La app conserva dos niveles:

1. tabla completa de segmentos ML detectados,
2. conjunto filtrado para reporte/cruce cuando se activa la exclusión de falsos lances.

Esto mantiene trazabilidad: se puede revisar qué detectó el modelo, qué decidió el analista y qué entró finalmente al reporte.

## 4. Por qué no saltar todavía directo a tablas de entrenamiento completas

La recomendación práctica es avanzar por fases.

### Fase actual: validación ligera dentro del reporte

Ventajas:

- resuelve el problema inmediato de falsos segmentos ML,
- permite limpiar el reporte comparativo sin perder evidencia,
- captura criterio humano de forma simple,
- no obliga todavía a diseñar todo el pipeline de entrenamiento.

### Siguiente fase: dataset de entrenamiento

Cuando haya suficientes marcas humanas, conviene exportarlas a tablas de entrenamiento.

Una estructura futura podría incluir:

#### Tabla `ml_segment_validations`

Una fila por segmento detectado:

| columna | descripción |
|---|---|
| `source_file` | archivo del sensor/lances |
| `segment_id` | ID del segmento ML |
| `segment_label` | etiqueta visual del segmento |
| `start_ts` | inicio del segmento |
| `end_ts` | fin del segmento |
| `manual_validation` | sí/no/dudoso/sin revisar |
| `validation_user` | quién validó |
| `validated_at` | fecha de validación |
| `preset_name` | preset ML usado |
| `ml_params` | parámetros ML completos |
| `features_json` | métricas del segmento usadas como features |

#### Tabla `ml_segment_features`

Una fila por segmento con variables para entrenamiento:

- duración,
- número de lecturas,
- promedio/mediana/mínimo/máximo,
- delta,
- desviación estándar,
- IQR,
- contraste contra entorno,
- cluster,
- métricas de solapamiento con lances observados.

## 5. Decisión actual

Por ahora, la app implementa la fase ligera:

- marcar manualmente segmentos ML,
- excluir falsos lances del cruce y descarga filtrada,
- conservar todo en pantalla para auditoría.

Esto ya deja una base natural para convertir esas marcas en tablas de entrenamiento cuando el flujo de validación esté más estable.

