# Actualización 2026-07-16 — Hojas Excel y descarga personalizada

Esta actualización cierra dos ajustes pequeños pero útiles de la interfaz:

1. seleccionar la hoja correcta cuando un archivo Excel trae múltiples pestañas;
2. ajustar la descarga del reporte para que el nombre personalizado quede alineado con el botón de descarga.

---

## 1. Selección de hoja en archivos Excel

Antes, cuando el archivo de lances o sensores era `.xlsx`/`.xls`, la app leía la primera hoja por defecto. Eso podía fallar o confundir cuando el libro traía varias pestañas y los datos reales estaban en otra hoja.

Ahora, si se carga un Excel con múltiples hojas, la UI muestra un selector independiente para:

- **Hoja de Excel para lances**
- **Hoja de Excel para sensores**

La app lee la hoja seleccionada y después aplica el mismo flujo de siempre:

- detección de encabezado real,
- normalización de columnas,
- normalización explícita de fechas/horas,
- selección de intervalo TFM,
- cruce con sensores,
- detección ML.

Esto evita tener que modificar el archivo original solo para dejar la hoja correcta como primera pestaña.

---

## 2. Carga de lances y sensores con Excel multihoja

El soporte aplica a ambos archivos:

### Lances

- Se puede cargar CSV, XLSX o XLS.
- Si es Excel, se selecciona hoja antes de detectar el encabezado.
- La nota de formato indica la hoja usada.
- La normalización posterior no cambia: columnas como `clave lance`, `hr fincal` o `Hora_2` se siguen normalizando como antes.

### Sensores

- Se puede cargar CSV, XLSX o XLS.
- Si es Excel, se selecciona hoja antes de leer la tabla.
- Después se eligen columna de tiempo y columna de temperatura.

---

## 3. Descarga del reporte integrado

El reporte comparativo sigue descargándose como CSV.

El nombre por defecto continúa siendo:

```text
reporte_lances_tfm_ml.csv
```

La interfaz permite escribir un nombre personalizado con o sin `.csv`. La app limpia caracteres problemáticos para crear un nombre seguro de archivo.

Cambio visual: el campo de nombre personalizado quedó debajo del área/botón de descarga para evitar que la interfaz se viera desalineada.

---

## 4. Validación realizada

Se probó con un Excel temporal de múltiples hojas para confirmar que:

- `_excel_sheet_names()` lista las hojas correctamente,
- `_load_lances_file(sheet_name=...)` carga la hoja elegida,
- `_load_sensor_file(sheet_name=...)` carga la hoja elegida,
- el flujo conserva la detección de encabezado en Excel,
- la descarga usa el nombre limpio elegido por el usuario.

---

## 5. Impacto práctico

Para Kaleb/Oscar:

- ya no hace falta editar el Excel antes de cargarlo si los datos vienen en una pestaña secundaria;
- se reduce riesgo de analizar una hoja equivocada;
- el reporte final puede nombrarse según viaje, sensor o fecha antes de descargarlo.
