# Actualización 2026-07-16 — Carga flexible y normalización explícita

## Resumen

Se agregó una etapa visible de **Normalización de fechas y horas** antes del procesamiento principal de la app.

El objetivo es evitar que la lógica interna intente adivinar todos los formatos posibles de cada archivo. En su lugar, la app muestra y aplica transformaciones controladas antes de construir intervalos de lance, calcular TFM o comparar contra sensores.

## Cambios principales

### 1. Lances y sensores aceptan CSV o Excel

Ambos cargadores aceptan:

- `.csv`
- `.xlsx`
- `.xls`

Para archivos CSV, la app detecta automáticamente separadores comunes:

- coma `,`
- punto y coma `;`
- tabulador
- barra vertical `|`

También detecta encabezados aunque haya una leyenda o filas iniciales antes de la tabla real.

### 2. Normalización de nombres de columnas

El archivo de lances puede traer variantes de nombres. La app normaliza nombres comunes a las columnas internas esperadas.

Ejemplos:

| En archivo | Interno |
|---|---|
| `clave lance` | `clave_lance` |
| `clave viaje` | `clave_viaje` |
| `hr fincal` | `hr_fincal` |
| `hr inicob` | `hr_inicob` |

La UI avisa qué columnas fueron renombradas.

### 3. Nueva sección: Normalización de fechas y horas

Después de cargar lances y antes de elegir el intervalo TFM, la app muestra una sección llamada:

> **Normalización de fechas y horas**

Esta sección prepara el archivo antes del cálculo. Después de aplicarla, el resto de la app sigue trabajando con el flujo normal.

Transformaciones actuales:

1. **Normalizar columna de fecha a `YYYY-MM-DD`**
   - Útil cuando la fecha viene como texto, Excel o con hora incluida.
   - Ejemplos: `28/01/2021`, `2021-01-28`, fecha nativa de Excel.

2. **Convertir columnas de hora decimal a `HH:MM`**
   - Útil cuando columnas como `Hora_1`, `Hora_2`, `Hora_3`, `Hora_4` vienen como horas decimales.
   - Ejemplos:
     - `7.5` → `07:30`
     - `7.6` → `07:36`
     - `10.9833` → `10:59`
     - `22.6667` → `22:40`

La app sugiere columnas candidatas cuando detecta valores que parecen horas decimales, pero el usuario conserva control desde la UI.

## Decisión de arquitectura

Se decidió **no** meter todas las reglas de interpretación dentro del parser base.

Razón: si la app intenta adivinar todos los escenarios silenciosamente, se vuelve más difícil auditar por qué un lance se calculó de cierta manera.

El enfoque adoptado es:

1. cargar archivo,
2. limpiar encabezados/columnas,
3. aplicar normalización explícita y visible,
4. mostrar **Lances normalizados**,
5. seleccionar intervalo TFM,
6. calcular TFM, reporte integrado y comparación ML.

Esto hace que las transformaciones sean revisables antes de empezar el análisis.

## Por qué aparecía `hora_invalida`

En un archivo nuevo, columnas como `Hora_2` y `Hora_3` traían valores numéricos de hora decimal:

```text
7.6
10.9833
22.6667
```

Antes, el cálculo esperaba formatos como `HH:MM` o, en algunos casos, `HH.MM`. Entonces `10.9833` podía interpretarse como si fuera `10:98`, lo cual es inválido.

Con la nueva etapa, esos valores se transforman explícitamente antes del cálculo:

```text
10.9833 → 10:59
22.6667 → 22:40
```

## Qué revisar al cargar un archivo nuevo

1. Confirmar que el encabezado detectado sea correcto.
2. Revisar mensajes de columnas renombradas.
3. En **Normalización de fechas y horas**:
   - confirmar la columna de fecha,
   - activar/desactivar columnas de hora decimal según corresponda,
   - revisar la vista previa transformada.
4. Verificar que la tabla **Lances normalizados** muestre fechas y horas esperadas.
5. Seleccionar intervalo TFM: recomendado `hr_fincal` → `hr_inicob` o `Hora_2` → `Hora_3`.

## Verificación técnica

Se validó con pruebas sintéticas:

- carga de lances CSV y XLSX,
- columnas `clave lance` → `clave_lance`,
- fechas texto e ISO,
- horas decimales como `7.5`, `7.6`, `10.9833`, `22.6667`,
- cálculo posterior de intervalos usando las columnas ya normalizadas.

