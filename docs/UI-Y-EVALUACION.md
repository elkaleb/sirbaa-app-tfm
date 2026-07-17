# UI y evaluación — SIRBAA Sensores

Esta guía explica qué hace cada parte de la interfaz de Streamlit y cómo se están evaluando los lances, tanto desde el archivo del observador como desde la señal del termómetro.

## 1. Objetivo de la interfaz

La app tiene dos caminos de análisis que se complementan:

1. **Cruce observador ↔ sensor**
   - Usa el archivo de lances capturado por el observador.
   - Convierte cada lance en un intervalo de evaluación configurable.
   - Por metodología SIRBAA, el intervalo recomendado es `hr_fincal` → `hr_inicob` (o `Hora_2` → `Hora_3`).
   - Busca las lecturas del sensor que caen dentro de ese intervalo.
   - Calcula TFM como promedio de temperatura dentro del lance.

2. **Detección desde termómetro**
   - Usa únicamente la serie de temperatura del sensor.
   - Busca patrones térmicos que parezcan lances.
   - Propone segmentos detectados por ML.
   - Permite compararlos visualmente contra los lances del observador.

La intención no es reemplazar al observador desde el inicio, sino tener una herramienta para comparar, auditar y ajustar poco a poco.

## 1.1 Nota metodológica

La detección ML debe interpretarse como una herramienta de apoyo para auditoría, no como una clasificación definitiva de lances.

La metodología combina:

- **Agrupamiento no supervisado con K-Means** para separar estados térmicos del sensor sin usar umbrales fijos de temperatura.
- **Suavizado de serie temporal** mediante media móvil para reducir ruido puntual antes de agrupar.
- **Estadística descriptiva y robusta** para caracterizar cada segmento: promedio, mediana, mínimo, máximo, desviación estándar, cuartiles, IQR y contraste contra entorno.
- **Revisión visual y comparación con observador** como paso final de validación.

Referencias base:

- MacQueen, J. (1967). *Some Methods for Classification and Analysis of Multivariate Observations*. Proceedings of the 5th Berkeley Symposium on Mathematical Statistics and Probability.
- Lloyd, S. P. (1982). *Least Squares Quantization in PCM*. IEEE Transactions on Information Theory, 28(2), 129-137.
- Tukey, J. W. (1977). *Exploratory Data Analysis*. Addison-Wesley.

Interpretación práctica: un segmento corto, con pocas lecturas, bajo contraste térmico, delta pequeño o señales estadísticas contradictorias debe revisarse como posible falso positivo o mala delimitación, no eliminarse automáticamente.

---

## 2. Partes principales de la UI

## 2.1 Carga de archivos

La parte superior tiene dos cargadores:

- **Archivo de lances (CSV/XLSX)**
- **Archivo de sensores (CSV/XLSX)**

### Qué evalúa

Para lances:

- Lee CSV o Excel (`.xlsx`/`.xls`).
- Si el Excel tiene varias hojas, permite seleccionar la hoja que contiene los datos antes de detectar encabezado.
- Detecta automáticamente si el CSV o Excel trae una leyenda o filas antes del encabezado real.
- En CSV detecta automáticamente el separador más probable: coma, punto y coma, tabulador o barra vertical.
- Busca columnas útiles del archivo de lances, incluyendo identificador, fecha y horas.
- Normaliza variantes comunes de nombres de columna, por ejemplo `clave lance` → `clave_lance`, `clave viaje` → `clave_viaje` o `hr fincal` → `hr_fincal`.
- La columna mínima requerida para depurar filas vacías es `clave_lance`, pero puede venir escrita con espacios o mayúsculas.
- Normaliza fechas y horas antes de comparar contra sensores. Soporta fechas como texto (`16/07/2026`, `2026-07-16`), fechas de Excel y horas en formatos `HH:MM`, `HH.MM`, hora decimal numérica (`10.9833` ≈ `10:59`) o fracción de día Excel.
- El intervalo de evaluación se selecciona en la UI. Recomendado por SIRBAA: `hr_fincal` → `hr_inicob`; en archivos alternos: `Hora_2` → `Hora_3`.
- Elimina filas sin `clave_lance`, porque no representan un lance usable.
- Oculta columnas completamente vacías para limpiar la vista.

Para sensores:

- Lee CSV o Excel.
- Si el Excel tiene varias hojas, permite seleccionar la hoja que contiene los datos antes de leer la tabla.
- En CSV detecta automáticamente el separador más probable: coma, punto y coma, tabulador o barra vertical. Esto permite leer exportaciones como `N.°;Fecha Tiempo;Temp...` sin que queden en una sola columna.
- Detecta encabezado si hay filas iniciales no útiles.
- Normaliza la columna de tiempo antes del análisis. Soporta texto con fecha/hora, fechas nativas de Excel y seriales numéricos de Excel.
- Oculta columnas vacías.
- Oculta columnas técnicas del logger con una regla general: columnas sin nombre, casi vacías/`None`, contadores secuenciales y columnas de estado/evento. También reconoce ejemplos comunes como `N.°`, `Host conectado`, `Parado` y `Final de archivo`, pero no depende solo de esos nombres.
- Muestra una vista previa de las primeras 20 filas para validar que el archivo se leyó correctamente. El análisis usa todas las filas cargadas, no solo la vista previa.

### Qué debe revisar el usuario

- Que la hoja seleccionada sea la correcta cuando el archivo sea Excel multihoja.
- Que el encabezado detectado sea correcto.
- Que la vista previa muestre columnas reales, no leyendas.
- Que las filas eliminadas tengan sentido.

---

## 2.2 Normalización de fechas y horas

Después de cargar el archivo de lances, la app muestra una etapa explícita de normalización antes de calcular TFM o cruzar contra sensores.

La decisión de diseño es importante: la app no debe intentar adivinar todos los formatos posibles de forma silenciosa. Primero se transforman las columnas necesarias de manera visible, y luego el resto del flujo trabaja con la tabla **Lances normalizados**.

### Transformaciones actuales

**Fecha**

- Normaliza la columna de fecha a `YYYY-MM-DD`.
- Sirve cuando el archivo trae fechas como texto (`28/01/2021`), ISO (`2021-01-28`) o fecha nativa de Excel.

**Horas decimales**

- Convierte columnas de hora decimal a `HH:MM`.
- Ejemplos:
  - `7.5` → `07:30`
  - `7.6` → `07:36`
  - `10.9833` → `10:59`
  - `22.6667` → `22:40`

La app puede sugerir columnas candidatas, especialmente cuando detecta minutos imposibles si se interpretaran como `HH.MM`, pero el usuario decide qué columnas transformar.

### Flujo recomendado

1. Revisar la columna de fecha sugerida.
2. Activar solo las columnas de hora que realmente estén en formato decimal.
3. Revisar la vista previa de la normalización.
4. Confirmar que la tabla **Lances normalizados** muestre fechas y horas esperadas.
5. Pasar a seleccionar el intervalo TFM.

### Por qué existe esta etapa

En algunos archivos, columnas como `Hora_2` o `Hora_3` vienen como número decimal:

```text
10.9833
22.6667
```

Eso no significa `10:98` ni `22:66`; significa hora decimal:

```text
10.9833 ≈ 10:59
22.6667 ≈ 22:40
```

Al convertirlo antes del cálculo, el resto de la app puede seguir usando el mismo flujo de intervalos sin meter reglas ocultas en cada función.

---

## 2.3 Selección de columnas del sensor

Después de cargar sensores, la app pide:

- **Columna de tiempo**
- **Columna de temperatura**

### Qué evalúa

La app normaliza esas columnas internamente como:

- `reading_ts`: timestamp de lectura.
- `temp_c`: temperatura numérica.

Luego intenta:

- convertir fechas/horas con `pd.to_datetime`,
- convertir temperatura a número,
- aceptar coma decimal cuando venga como texto,
- conservar otras columnas como contexto.

### Qué debe revisar el usuario

- Que la columna de tiempo realmente tenga fecha/hora de lectura.
- Que la columna de temperatura sea la del sensor correcto.
- Si la gráfica sale rara, esta selección es lo primero que hay que revisar.

---

## 2.4 Ajustes ML de detección

Esta sección controla cómo se detectan lances desde la temperatura.

### Número de clusters

Indica cuántos grupos térmicos intenta separar el modelo.

Valor recomendado inicial: `3`.

Interpretación esperada:

- un grupo puede representar temperatura de fondo,
- otro transición,
- otro posible periodo de lance/superficie.

La app no usa nombres biológicos fijos para los clusters. Ordena los grupos por temperatura suavizada y toma el grupo de menor temperatura como candidato de lance.

Cuando el modelo propone segmentos que no son lances reales, el analista puede marcarlos manualmente como `no es lance`. Esa marca no borra el segmento, pero puede excluirlo del cruce y de las descargas filtradas.

### Ventana de suavizado

Suaviza la temperatura antes de clasificar.

- Valor bajo: conserva detalle, pero puede meter ruido.
- Valor alto: limpia la señal, pero puede borrar cambios cortos.

### Suavizado de etiquetas

Después de clasificar punto por punto, suaviza la etiqueta `lance/no lance`.

Sirve para evitar cortes pequeños dentro de un mismo lance.

### Unir tramos cercanos (min)

Si el modelo detecta dos tramos de lance separados por pocos minutos, la app puede unirlos.

Esto ayuda cuando visualmente es un solo lance, pero el modelo lo partió por una interrupción corta.

### Mínimo de puntos por lance

Descarta candidatos con pocas lecturas.

Sirve para evitar falsos lances muy pequeños.

---

## 3. Cómo se evalúa la detección ML

La función principal es `detect_lance_segments_ml`.

El proceso actual es:

1. Ordenar lecturas por tiempo.
2. Convertir temperatura a número.
3. Calcular `temp_smooth` con media móvil.
4. Entrenar `KMeans` sobre la temperatura suavizada.
5. Identificar el cluster con menor temperatura media como candidato de lance.
6. Generar una etiqueta punto por punto:
   - `is_lance_ml_raw`: clasificación directa del cluster.
   - `is_lance_ml`: clasificación después de suavizar etiquetas.
7. Separar puntos consecutivos en segmentos.
8. Unir segmentos cercanos según `Unir tramos cercanos (min)`.
9. Descartar segmentos con menos puntos que el mínimo configurado.
10. Recalcular IDs y métricas finales.

### Columnas importantes generadas

En puntos:

- `reading_ts`: tiempo de lectura.
- `temp_c`: temperatura original.
- `temp_smooth`: temperatura suavizada.
- `ml_cluster`: cluster asignado por KMeans.
- `is_lance_ml_raw`: candidato original antes de suavizar.
- `is_lance_ml`: candidato final después de suavizar/unir/filtrar.
- `segment_id`: segmento final al que pertenece la lectura.

En segmentos:

- `segment_id`: número de segmento detectado.
- `segment_label`: etiqueta visual, por ejemplo `Lance 1`.
- `start_ts`: inicio del segmento.
- `end_ts`: fin del segmento.
- `n_points`: lecturas incluidas.
- `mean_temp`: temperatura promedio.
- `median_temp`: mediana de temperatura.
- `min_temp`: temperatura mínima.
- `max_temp`: temperatura máxima.
- `delta_temp`: diferencia entre temperatura máxima y mínima del segmento.
- `std_temp`: desviación estándar de temperatura dentro del segmento.
- `q1_temp`: primer cuartil de temperatura.
- `q3_temp`: tercer cuartil de temperatura.
- `iqr_temp`: rango intercuartílico (`q3_temp - q1_temp`).
- `env_mean_temp`: temperatura promedio del entorno antes/después del segmento.
- `env_contrast_temp`: diferencia entre entorno y segmento (`env_mean_temp - mean_temp`).
- `env_before_mean_temp`: promedio de temperatura antes del segmento.
- `env_after_mean_temp`: promedio de temperatura después del segmento.
- `env_n_points`: lecturas usadas para calcular el entorno.
- `duration_min`: duración en minutos.
- `duration_hhmm`: duración legible.
- `false_lance_risk`: nivel de alerta estadística para posible falso lance (`sin_alertas`, `bajo`, `medio`, `alto`).
- `false_lance_flags`: explicación de qué señales dispararon la alerta.
- `validation_hint`: sugerencia práctica para revisión del analista.
- `manual_validation`: decisión humana sobre si el segmento es lance real.
- `include_in_report`: indica si el segmento entra al cruce/reporte filtrado.

### Sugerencias para identificar posibles falsos lances

La app agrega una guía explicable para cada segmento detectado por ML. No marca automáticamente “verdadero/falso”; solo prioriza qué revisar.

Las señales se calculan comparando cada segmento contra los demás segmentos del mismo archivo, para evitar usar umbrales fijos de temperatura. Entre las alertas posibles están:

- **Duración corta**: el segmento dura menos que la mayoría de los segmentos detectados. Puede ser ruido o un fragmento de otro lance.
- **Pocas lecturas**: hay pocos puntos del sensor dentro del segmento. Las estadísticas son menos confiables.
- **Poco contraste térmico contra el entorno**: `env_contrast_temp` es bajo. Si el segmento no se diferencia de la temperatura previa/posterior, puede ser falso positivo.
- **Segmento no más frío que el entorno**: `env_contrast_temp <= 0`. Como el modelo busca el cluster más frío, esto amerita revisión.
- **Delta térmico bajo**: `delta_temp` es bajo frente a otros segmentos. Puede indicar tramo plano sin evento claro.
- **Desviación estándar baja**: `std_temp` baja puede señalar poca señal interna o temperatura demasiado estable.
- **Desviación estándar alta**: `std_temp` alta puede indicar mezcla de eventos, transiciones o mala delimitación.
- **IQR bajo**: `iqr_temp` bajo indica poca diferenciación robusta de la señal térmica.

El resultado se resume en:

- `false_lance_risk`: prioridad de revisión.
- `false_lance_flags`: razones concretas.
- `validation_hint`: recomendación breve para el analista.

---

## 4. Gráfica de temperatura

La gráfica combina varias capas:

1. **Línea gris**
   - Serie completa de temperatura del sensor.

2. **Bandas rojas**
   - Segmentos detectados por ML.
   - Una banda más intensa indica el segmento seleccionado.

3. **Bandas azules opcionales**
   - Lances del archivo del observador.
   - Se activan con `Superponer lances del observador`.
   - Se dibujan usando las columnas seleccionadas en **Intervalo de evaluación TFM**. Por defecto: `fecha + hr_fincal` como inicio y `fecha + hr_inicob` como fin; o `Hora_2` → `Hora_3` si ese formato existe.
   - La banda azul cubre verticalmente todo el rango visible de temperatura para que el intervalo observado sea fácil de comparar contra los segmentos rojos.
   - El tooltip muestra cuántas lecturas del sensor caen dentro de ese intervalo.

La gráfica permite zoom/pan para revisar tramos específicos de la serie temporal con más detalle.

### Qué evalúa la gráfica

Permite comparar visualmente:

- si los segmentos ML caen donde la temperatura cambia,
- si los lances del observador coinciden con esos cambios,
- si el ML está fragmentando un lance en varios,
- si está detectando tramos donde el observador no registró lance,
- si hay lances del observador sin señal térmica clara.

### Cómo interpretar coincidencias

- **Rojo y azul se empalman bien**: buena coincidencia entre sensor y observador.
- **Rojo dividido en muchas partes dentro de un mismo azul**: probablemente hace falta subir suavizado o unir tramos cercanos.
- **Muchos rojos sin azul**: posible falso positivo, o eventos térmicos no registrados como lance.
- **Azul sin rojo**: posible lance sin cambio térmico fuerte, columna incorrecta, sensor desfasado o parámetros muy estrictos.

Si aparecen menos bandas azules que lances en el archivo, normalmente significa que algunos lances no pudieron convertirse a intervalos válidos por fecha/hora. La app muestra cuántos lances observados logró dibujar.

---

## 5. Tabla de lances detectados por ML

La tabla muestra los segmentos finales después de suavizar, unir y filtrar.

Esta tabla ya funciona como cálculo estadístico de temperatura para los lances detectados por ML. En ese sentido, `mean_temp` es equivalente al TFM promedio para el segmento detectado desde el termómetro.

Cada columna incluye ayuda contextual en la interfaz para explicar qué mide y para qué sirve durante la validación.

Además, el segmento seleccionado puede marcarse manualmente con una de estas opciones:

- `sin revisar`
- `sí es lance`
- `no es lance`
- `dudoso`

La marca se refleja en `manual_validation`. La columna `include_in_report` indica si el segmento entra al cruce/reporte filtrado. Por defecto, `no es lance` queda fuera del cruce observador ↔ ML y de la descarga filtrada, pero se conserva en la tabla completa para auditoría.

### Qué evalúa

Cada fila representa un candidato de lance detectado por el termómetro.

Sirve para revisar:

- inicio y fin,
- duración,
- número de lecturas,
- rango de temperatura,
- temperatura promedio,
- mediana,
- desviación estándar,
- delta térmico,
- rango intercuartílico,
- validación manual del analista.

### Medidas útiles para detectar posibles falsos positivos

- **`delta_temp`**: si el segmento casi no cambia de temperatura, puede ser un falso positivo o un tramo plano.
- **`std_temp`**: mide variabilidad interna; valores muy bajos pueden indicar poca señal real, valores muy altos pueden indicar mezcla de eventos o ruido.
- **`iqr_temp`**: mide dispersión robusta ignorando picos extremos; ayuda cuando hay spikes aislados del sensor.
- **`env_contrast_temp`**: compara el promedio del segmento contra el promedio del entorno anterior/posterior. Si el valor es alto y positivo, el lance se distingue térmicamente de lo que había alrededor. Si está cerca de cero, puede ser un falso positivo o un tramo poco contrastante.
- **`duration_min` + `n_points`**: segmentos muy cortos o con pocas lecturas suelen ser menos confiables.
- **`median_temp` vs `mean_temp`**: si difieren mucho, puede haber picos raros dentro del segmento.

### Cómo se calcula el contraste contra entorno

Para cada segmento detectado, la app toma lecturas del termómetro antes y después del lance usando la ventana configurada en **Ventana de entorno para contraste (min)**.

Ejemplo con ventana de 60 minutos:

- 60 minutos antes del inicio del segmento,
- 60 minutos después del fin del segmento,
- excluye las lecturas dentro del segmento.

Luego calcula:

```text
env_mean_temp = promedio(lecturas antes + lecturas después)
env_contrast_temp = env_mean_temp - mean_temp
```

Como la detección actual busca segmentos más fríos, un valor positivo indica que el segmento está por debajo de su entorno. Esto ayuda a identificar si el lance tiene una señal térmica clara.

### Selección tabla ↔ gráfica

La app tiene sincronización básica:

- seleccionar una fila resalta su banda en la gráfica,
- hacer click en una banda puede actualizar el segmento seleccionado,
- debajo se muestra la subtabla de lecturas internas de ese segmento.

Cuando cambian los parámetros ML y cambia el número de segmentos, la selección se reinicia contra el resultado nuevo para evitar que quede apuntando a una selección anterior.

Esto permite auditar por qué el modelo llamó “lance” a ese tramo.

---

## 6. Subtabla de lecturas del segmento ML

Debajo de la tabla ML se muestran las lecturas que caen dentro del segmento seleccionado.

### Qué evalúa

Permite revisar punto por punto:

- timestamp,
- temperatura original,
- temperatura suavizada,
- cluster asignado,
- si quedó marcado como lance,
- `segment_id`.

Esta parte es clave para depurar casos donde la gráfica parece correcta pero la tabla no, o viceversa.

---

## 7. Comparación observador ↔ ML y TFM observado

La sección **Comparación observador ↔ ML y TFM observado** usa el archivo de lances tradicional y lo conecta con los segmentos detectados por ML.

Esto es diferente de la tabla ML superior:

- la tabla superior calcula estadísticas para segmentos detectados desde el termómetro,
- esta sección calcula TFM usando los intervalos reportados por el observador.
- si ya existen segmentos ML, también busca qué segmento detectado se solapa con cada lance observado.

La sección se calcula automáticamente cuando están cargados ambos archivos; ya no depende de un botón separado.

### Qué evalúa

Para cada lance:

1. Usa la columna de fecha seleccionada.
2. Combina fecha + columna de inicio seleccionada para crear `lance_inicio_ts`. Recomendado: `hr_fincal` o `Hora_2`.
3. Combina fecha + columna de fin seleccionada para crear `lance_fin_ts`. Recomendado: `hr_inicob` o `Hora_3`.
4. Si la hora final es menor que la inicial, asume cruce de medianoche y suma un día.
5. Busca lecturas del sensor donde:

```text
lance_inicio_ts <= reading_ts <= lance_fin_ts
```

6. Calcula:

- `tfm_promedio`
- `tfm_mediana`
- `tfm_min`
- `tfm_max`
- `tfm_delta`
- `tfm_std`
- `tfm_q1`
- `tfm_q3`
- `tfm_iqr`
- `tfm_n_lecturas`
- `tfm_match_status`

Si hay detección ML disponible, agrega además:

- `ml_segment_id`: segmento ML que más se solapa con el lance observado.
- `ml_segment_label`: etiqueta del segmento ML, por ejemplo `Lance 1`.
- `ml_overlap_min`: minutos de solapamiento entre lance observado y segmento ML.
- `ml_overlap_ratio_observed`: proporción del lance observado cubierta por el segmento ML.
- `ml_start_ts` / `ml_end_ts`: inicio y fin del segmento ML asociado.
- `ml_duration_min`: duración del segmento ML asociado.
- `ml_n_points`: lecturas dentro del segmento ML asociado.
- `ml_mean_temp`: temperatura promedio del segmento ML.
- `ml_median_temp`, `ml_min_temp`, `ml_max_temp`, `ml_delta_temp`, `ml_std_temp`, `ml_iqr_temp`: estadísticos térmicos del segmento ML asociado.
- `ml_env_contrast_temp`: contraste térmico del segmento ML contra su entorno.
- `ml_false_lance_risk`, `ml_false_lance_flags`, `ml_validation_hint`: sugerencias de validación heredadas del segmento ML asociado.
- `tfm_vs_ml_mean_delta`: diferencia entre `tfm_promedio` observado y `ml_mean_temp`.

La tabla mostrada en pantalla y el CSV descargable se presentan como **reporte de lances**: conserva las columnas originales del archivo de lances y agrega los valores calculados por sensor/ML. Esto permite que un analista trabaje directamente sobre un solo archivo integrado.

El nombre del archivo descargable puede personalizarse desde la interfaz. Se puede escribir con o sin `.csv`; la app limpia caracteres problemáticos para generar un nombre de archivo seguro.

Si un segmento ML se marca manualmente como `no es lance` y está activada la exclusión de falsos lances, ese segmento no se usa para el cruce con lances observados ni para descargas filtradas. La detección original se conserva en la tabla completa de segmentos ML.

Esto ayuda a responder preguntas como:

- ¿El lance observado coincide con un segmento detectado por el termómetro?
- ¿Cuánto se traslapan en tiempo?
- ¿El promedio de temperatura del observador y el promedio ML son parecidos?
- ¿Hay lances observados sin segmento ML o segmentos ML sin lance observado?

### Estados posibles

- `ok`: hubo lecturas válidas dentro del lance.
- `sin_lecturas`: el intervalo no encontró lecturas del sensor.
- `hora_invalida`: inicio o fin no se pudo convertir a hora válida.

---

## 8. Subtabla de lecturas dentro del lance del observador

Después de calcular TFM, la app permite seleccionar un lance del observador y ver sus lecturas internas.

La selección se hace directamente desde la tabla **Resultado comparativo**. Al seleccionar una fila, la auditoría inferior se actualiza con las lecturas del sensor dentro de ese lance. Ya no es necesario usar un menú desplegable separado.

### Qué evalúa

Sirve para auditar el cálculo TFM:

- cuántas lecturas entraron al promedio,
- qué rango térmico cubren,
- si el intervalo del observador está bien armado,
- si hay desfase de fecha/hora entre archivos.

Para facilitar la revisión, esta tabla oculta columnas que estén vacías dentro del lance seleccionado. Esto evita que aparezcan columnas del sensor llenas de `None` cuando no aportan información en esa ventana concreta.

---

## 9. Cómo calibrar cuando visualmente deberían ser 3 lances

Si la gráfica muestra demasiados lances, probar en este orden:

1. Subir **Unir tramos cercanos (min)**.
   - Junta fragmentos separados por gaps cortos.

2. Subir **Suavizado de etiquetas**.
   - Reduce cambios rápidos de lance/no lance.

3. Subir ligeramente **Ventana de suavizado**.
   - Limpia ruido en temperatura.

4. Subir **Mínimo de puntos por lance**.
   - Elimina candidatos muy cortos.

5. Revisar **Número de clusters**.
   - `3` es el punto inicial.
   - `2` puede ser más simple.
   - `4` o `5` pueden separar demasiado si la señal tiene variaciones pequeñas.

La meta práctica no es forzar siempre 3, sino entender si los segmentos extra son ruido, fragmentación del mismo lance o eventos térmicos reales no registrados.

---

## 10. Limitaciones actuales

- KMeans solo ve temperatura suavizada por ahora; no usa duración, pendiente o contexto operativo como variables principales.
- La selección tabla ↔ gráfica depende de soporte de Streamlit/Altair y puede requerir pequeños ajustes si cambia la versión.
- El cruce observador ↔ ML usa el mayor solapamiento temporal; todavía no clasifica automáticamente falso positivo/falso negativo con umbrales operativos.

---

## 11. Próximas mejoras sugeridas

1. Agregar métricas de evaluación:
   - lances observador encontrados,
   - lances ML sin observador,
   - lances observador sin ML,
   - fragmentación por lance.

2. Permitir guardar una configuración de parámetros por pesquería o tipo de sensor.

3. Agregar una vista de diagnóstico de clusters:
   - medias por cluster,
   - distribución de temperatura,
   - puntos coloreados por cluster.
