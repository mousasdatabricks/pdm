# Guía de despliegue por interfaz gráfica (sin terminal)

Esta guía explica **cada paso usando solo la interfaz web de Databricks**. No necesitas instalar la CLI ni usar la terminal.

**Tiempo estimado:** 60–90 minutos (primera vez).

**Repositorio:** https://github.com/mousasdatabricks/pdm

---

## Índice

1. [Antes de empezar](#1-antes-de-empezar)
2. [Descargar el proyecto desde GitHub](#2-descargar-el-proyecto-desde-github)
3. [Crear schema y volumen en Unity Catalog](#3-crear-schema-y-volumen-en-unity-catalog)
4. [Subir los datos SCADA](#4-subir-los-datos-scada)
5. [Importar los notebooks al workspace](#5-importar-los-notebooks-al-workspace)
6. [Ajustar el catálogo en los notebooks](#6-ajustar-el-catálogo-en-los-notebooks)
7. [Crear el Job principal (pipeline)](#7-crear-el-job-principal-pipeline)
8. [Ejecutar el pipeline y verificar resultados](#8-ejecutar-el-pipeline-y-verificar-resultados)
9. [Crear y ejecutar el Job del wrapper](#9-crear-y-ejecutar-el-job-del-wrapper)
10. [Importar el dashboard Lakeview](#10-importar-el-dashboard-lakeview)
11. [Crear el endpoint de serving (opcional)](#11-crear-el-endpoint-de-serving-opcional)
12. [Programar ejecuciones automáticas (opcional)](#12-programar-ejecuciones-automáticas-opcional)
13. [Checklist final](#13-checklist-final)
14. [Solución de problemas](#14-solución-de-problemas)

---

## 1. Antes de empezar

### Lo que necesitas

| Requisito | Cómo verificarlo |
|-----------|------------------|
| Acceso a un workspace Databricks | Puedes iniciar sesión en `https://TU-WORKSPACE.cloud.databricks.com` |
| Unity Catalog habilitado | En el menú lateral aparece **Catalog** o **Data** |
| Permisos para crear tablas y volúmenes | Pregunta a tu admin si puedes crear schemas en un catálogo |
| SQL Warehouse activo | Menú **SQL** → **SQL Warehouses** → al menos uno en estado **Running** o **Serverless** |
| Archivo de datos SCADA | `DataScada_MLAeros_runinng.csv.gz` (~24 MB) |

### Lo que vas a construir

```
CSV en Volume
    → Notebook 01 (ingesta)
    → Notebook 02 (modelo + tablas gold)
    → Notebook 03 (wrapper probabilidad)
    → Dashboard Lakeview
    → (Opcional) Endpoint API
```

### Valores que usarás (ajústalos a tu entorno)

A lo largo de la guía sustituye estos placeholders:

| Placeholder | Ejemplo en el proyecto original |
|-------------|----------------------------------|
| `TU_CATALOGO` | `serverless_stable_cvpomp_catalog` |
| `TU_WORKSPACE` | `fevm-serverless-stable-cvpomp` |
| Schema | `engie_peru_pdm` (recomendado mantener este nombre) |

---

## 2. Descargar el proyecto desde GitHub

1. Abre en el navegador: **https://github.com/mousasdatabricks/pdm**
2. Clic en el botón verde **Code** → **Download ZIP**
3. Descomprime el ZIP en tu computadora
4. Dentro de la carpeta `pdm` encontrarás:
   - `notebooks/` — los 3 notebooks Python
   - `dashboards/engie_peru_pdm.lvdash.json` — el dashboard
   - `sql/01_setup.sql` — script SQL de referencia

> **Alternativa:** si tu workspace tiene **Repos** habilitado, puedes clonar el repo directamente (ver [Apéndice A](#apéndice-a--conectar-el-repo-por-repos-git)).

---

## 3. Crear schema y volumen en Unity Catalog

### 3.1 Abrir Catalog Explorer

1. En el menú lateral izquierdo, clic en **Catalog** (o **Data** → **Catalog Explorer**)
2. En el panel izquierdo verás la lista de **Catalogs**

### 3.2 Elegir un catálogo

1. Expande un catálogo donde tengas permisos de escritura (ej. `TU_CATALOGO`)
2. Si no ves ninguno, contacta al administrador del workspace

### 3.3 Crear el schema

**Opción A — Desde Catalog Explorer**

1. Clic derecho sobre el catálogo → **Create schema**
2. Completa:
   - **Schema name:** `engie_peru_pdm`
   - **Comment (opcional):** `POC Mantenimiento Predictivo Aerogeneradores`
3. Clic en **Create**

**Opción B — Desde SQL Editor**

1. Menú lateral → **SQL** → **SQL Editor**
2. Arriba a la derecha, selecciona un **SQL Warehouse** (Serverless o Pro)
3. Pega y ejecuta (cambia el catálogo):

```sql
USE CATALOG TU_CATALOGO;

CREATE SCHEMA IF NOT EXISTS engie_peru_pdm
  COMMENT 'POC Mantenimiento Predictivo — Aerogeneradores';
```

4. Clic en **Run** (o `Ctrl+Enter` / `Cmd+Enter`)
5. Debe aparecer un mensaje de éxito en la parte inferior

### 3.4 Crear el volumen para datos crudos

**Desde SQL Editor** (más sencillo):

```sql
USE CATALOG TU_CATALOGO;
USE SCHEMA engie_peru_pdm;

CREATE VOLUME IF NOT EXISTS raw
  COMMENT 'Datos SCADA crudos (CSV comprimido)';
```

**Desde Catalog Explorer:**

1. Navega a `TU_CATALOGO` → `engie_peru_pdm`
2. Pestaña **Volumes** → **Create volume**
3. Nombre: `raw` → **Create**

### 3.5 Verificar

En Catalog Explorer deberías ver:

```
TU_CATALOGO
 └── engie_peru_pdm
      └── Volumes
           └── raw
```

---

## 4. Subir los datos SCADA

El notebook de ingesta lee el archivo desde:

```
/Volumes/TU_CATALOGO/engie_peru_pdm/raw/DataScada_MLAeros_runinng.csv.gz
```

### Pasos en la UI

1. **Catalog** → `TU_CATALOGO` → `engie_peru_pdm` → **Volumes** → `raw`
2. Clic en **Upload to this volume** (o icono de subida)
3. Selecciona el archivo `DataScada_MLAeros_runinng.csv.gz` desde tu computadora
4. Espera a que termine la carga (~24 MB)

### Verificar

- En la lista del volumen debe aparecer `DataScada_MLAeros_runinng.csv.gz`
- El tamaño debe ser aproximadamente **24 MB**

> **Importante:** el nombre del archivo debe coincidir exactamente. Si tu archivo tiene otro nombre, renómbralo antes de subirlo o edita la variable `RAW` en el notebook `01_ingest_features` (celda 2).

---

## 5. Importar los notebooks al workspace

Vas a subir los 3 archivos `.py` de la carpeta `notebooks/` del ZIP.

### 5.1 Crear carpeta en el workspace

1. Menú lateral → **Workspace**
2. Navega a tu carpeta de usuario (ej. `/Users/tu.email@empresa.com`)
3. Clic en el menú **⋮** junto a tu nombre → **Create** → **Folder**
4. Nombre sugerido: `engie_peru_pdm`

### 5.2 Importar cada notebook

Repite estos pasos para **cada uno** de los archivos:

- `01_ingest_features.py`
- `02_pdm_model.py`
- `03_wrap_proba.py`

**Procedimiento:**

1. Entra en la carpeta `engie_peru_pdm`
2. Clic en **⋮** (arriba a la derecha) → **Import**
3. En **Import from**, elige **File**
4. Arrastra el archivo `.py` o haz clic para seleccionarlo
5. **Import as:** Notebook
6. Clic en **Import**

### 5.3 Verificar

Deberías ver 3 notebooks en:

```
Workspace
 └── Users
      └── tu.email@empresa.com
           └── engie_peru_pdm
                ├── 01_ingest_features
                ├── 02_pdm_model
                └── 03_wrap_proba
```

### 5.4 Configurar el cluster / compute

Los notebooks necesitan un **compute** para ejecutarse:

1. Abre cualquier notebook importado
2. Arriba, en el selector de compute, clic en **Connect**
3. Elige una de estas opciones:
   - **Serverless** (recomendado si está disponible en tu workspace)
   - **Job cluster** (se configurará al crear el Job en el paso 7)
   - Un **All-purpose cluster** existente

> Para la ejecución manual de prueba puedes usar Serverless. Para el Job, se creará compute automáticamente.

---

## 6. Ajustar el catálogo en los notebooks

Cada notebook tiene variables al inicio que deben apuntar a **tu** catálogo.

### 6.1 Notebook `01_ingest_features`

1. Abre el notebook en el workspace
2. Busca la **celda 2** (después del título markdown)
3. Edita estas líneas:

```python
CATALOG = "TU_CATALOGO"        # ← cambia aquí
SCHEMA  = "engie_peru_pdm"
RAW     = f"/Volumes/{CATALOG}/{SCHEMA}/raw/DataScada_MLAeros_runinng.csv.gz"
```

4. **No ejecutes aún** — primero crearemos el Job

### 6.2 Notebook `02_pdm_model`

1. Abre el notebook
2. En la celda de parámetros (celda ~3), edita:

```python
CATALOG = "TU_CATALOGO"
SCHEMA  = "engie_peru_pdm"
```

3. Más abajo hay una línea de experimento MLflow:

```python
mlflow.set_experiment("/Shared/engie_peru_pdm")
```

   Si no tienes permiso en `/Shared`, cámbiala a tu carpeta:

```python
mlflow.set_experiment("/Users/tu.email@empresa.com/engie_peru_pdm")
```

   Luego crea ese experimento: menú **Machine Learning** → **Experiments** → **Create experiment** con ese path.

### 6.3 Notebook `03_wrap_proba`

1. Abre el notebook
2. Edita la línea del modelo:

```python
MODEL = "TU_CATALOGO.engie_peru_pdm.derate_early_warning"
```

### 6.4 Guardar cambios

Los notebooks se guardan automáticamente. Verifica que no queden celdas con el catálogo antiguo (`serverless_stable_cvpomp_catalog`) si no es el tuyo.

---

## 7. Crear el Job principal (pipeline)

El Job ejecuta los notebooks **01** y **02** en secuencia.

### 7.1 Iniciar creación del Job

1. Menú lateral → **Jobs & Pipelines** (o **Workflows**)
2. Clic en **Create** → **Job**

### 7.2 Configuración general

| Campo | Valor |
|-------|-------|
| **Job name** | `PdM Aerogeneradores POC` |
| **Description (opcional)** | Pipeline ingesta + modelo PdM |

### 7.3 Tarea 1 — Ingesta

1. En la sección **Tasks**, clic en **Add task** (si no hay ninguna)
2. Configura la primera tarea:

| Campo | Valor |
|-------|-------|
| **Task name** | `ingest_features` |
| **Type** | `Notebook` |
| **Source** | `Workspace` |
| **Path** | Navega a `/Users/.../engie_peru_pdm/01_ingest_features` |
| **Compute** | Serverless o New job cluster (ver abajo) |

**Compute recomendado (Job cluster):**

- Clic en **Add new job cluster** si no tienes uno
- **Databricks runtime:** 15.x o superior
- **Worker type:** según tu workspace (ej. `i3.xlarge` o equivalente serverless)
- **Workers:** 2 (suficiente para este POC)

### 7.4 Tarea 2 — Modelo

1. Clic en **+ Add task**
2. Configura:

| Campo | Valor |
|-------|-------|
| **Task name** | `pdm_model` |
| **Type** | `Notebook` |
| **Path** | `/Users/.../engie_peru_pdm/02_pdm_model` |
| **Depends on** | `ingest_features` |
| **Run if** | `All succeeded` |
| **Compute** | Mismo cluster que la tarea 1 (recomendado) |

### 7.5 Dependencias visuales

En el diagrama del Job deberías ver:

```
ingest_features  ──►  pdm_model
```

Si `pdm_model` no depende de `ingest_features`, edita la tarea 2 → sección **Depends on** → selecciona `ingest_features`.

### 7.6 Guardar el Job

1. Clic en **Create** (o **Save** si estás editando)
2. El Job aparecerá en la lista de **Jobs & Pipelines**

---

## 8. Ejecutar el pipeline y verificar resultados

### 8.1 Lanzar la ejecución

1. Abre el Job **PdM Aerogeneradores POC**
2. Clic en **Run now** (arriba a la derecha)
3. Se abrirá la vista de **Run** con el estado de cada tarea

### 8.2 Monitorear el progreso

| Estado | Significado |
|--------|-------------|
| **Pending** | En cola |
| **Running** | Ejecutándose |
| **Succeeded** | Completado OK |
| **Failed** | Error — ver logs |

**Para ver logs de una tarea:**

1. Clic en el nombre de la tarea (ej. `ingest_features`)
2. Pestaña **Logs** o **Output**
3. Si falló, revisa el mensaje de error al final

**Tiempos orientativos:**

- `01_ingest_features`: 5–15 min
- `02_pdm_model`: 15–45 min (entrena varios modelos)

### 8.3 Verificar tablas creadas

1. **Catalog** → `TU_CATALOGO` → `engie_peru_pdm` → pestaña **Tables**
2. Deben existir:

| Tabla | Descripción |
|-------|-------------|
| `bronze_scada` | Datos crudos tipados |
| `silver_scada_10min` | Features cada 10 min |
| `gold_health_timeline` | Health Index + alert_score |
| `gold_derate_events` | Episodios de derateo |
| `gold_model_metrics` | ROC-AUC y métricas |
| `gold_alert_drivers` | Importancia de variables |

3. Clic en una tabla → **Sample data** para ver filas

### 8.4 Verificar el modelo en Unity Catalog

1. Menú **Catalog** → `TU_CATALOGO` → `engie_peru_pdm`
2. Pestaña **Models** (o **Machine Learning** → **Models**)
3. Debe aparecer: `derate_early_warning` con al menos **versión 1**

También puedes ir a **Machine Learning** → **Models** → buscar `derate_early_warning`.

---

## 9. Crear y ejecutar el Job del wrapper

Este paso registra la **versión 2** del modelo, que devuelve probabilidad (0–1) en lugar de clase. Es necesario antes de crear el endpoint.

### 9.1 Crear el Job

1. **Jobs & Pipelines** → **Create** → **Job**
2. Configuración:

| Campo | Valor |
|-------|-------|
| **Job name** | `PdM - proba wrapper` |
| **Task name** | `wrap` |
| **Type** | `Notebook` |
| **Path** | `/Users/.../engie_peru_pdm/03_wrap_proba` |

3. **Create**

### 9.2 Ejecutar

1. Abre el Job → **Run now**
2. Espera estado **Succeeded**

### 9.3 Verificar nueva versión del modelo

1. **Catalog** → modelo `derate_early_warning`
2. Debe haber **versión 2** (o superior) con descripción/run `derate_proba_wrapper`
3. En la salida del notebook verás: `VERSION_NUEVA: 2`

> **Orden obligatorio:** no ejecutes este Job antes de que el Job principal haya registrado la versión 1 del modelo.

---

## 10. Importar el dashboard Lakeview

### 10.1 Importar el archivo JSON

1. Menú lateral → **Dashboards** (o **SQL** → **Dashboards**)
2. Clic en **Create** → **Import dashboard**
3. Selecciona el archivo `dashboards/engie_peru_pdm.lvdash.json` del ZIP descargado
4. Clic en **Import**

### 10.2 Asignar SQL Warehouse

1. Abre el dashboard importado
2. Arriba, junto al nombre, busca el selector de **Warehouse** (o icono de configuración)
3. Selecciona un SQL Warehouse **Serverless** o **Pro** en estado activo
4. Si no hay warehouse, ve a **SQL** → **SQL Warehouses** → **Create** (Serverless es la opción más simple)

### 10.3 Actualizar referencias al catálogo

El dashboard importado puede tener consultas con el catálogo original. Si tus tablas están en otro catálogo:

1. En el dashboard, clic en **Edit** (modo edición)
2. Panel lateral → **Data** (o lista de datasets)
3. Para cada dataset, clic en el nombre → se abre el editor SQL
4. Reemplaza todas las ocurrencias de:
   - `serverless_stable_cvpomp_catalog` → `TU_CATALOGO`
5. Clic en **Run** en cada dataset para validar que devuelve datos
6. **Save** el dashboard

**Datasets principales:**

| Dataset | Qué muestra |
|---------|-------------|
| `ds_kpis` | Energía no generada, ROC-AUC, nº turbinas |
| `ds_health_daily` | Health Index diario por turbina |
| `ds_powerratio_daily` | Power ratio cuando produce |
| `ds_energy_turbine` | Energía perdida por turbina |
| `ds_drivers` | Top variables del modelo |
| `ds_alert_table` | Alertas con score > 0.6 |

### 10.4 Publicar y compartir

1. Clic en **Publish** (si está en borrador)
2. Para compartir: **Share** → añade usuarios o grupos con permiso **Can view**

### 10.5 Qué deberías ver

- **KPIs** en la parte superior (números, no vacíos)
- Gráficos de **Health Index** por turbina (AEG_51, AEG_52)
- Tabla de **alertas recientes**
- Si todo está vacío → revisa warehouse y que el pipeline haya terminado OK

---

## 11. Crear el endpoint de serving (opcional)

Permite llamar al modelo vía API REST (integración con apps, alertas, etc.).

### 11.1 Abrir Serving

1. Menú **Serving** (o **Machine Learning** → **Serving**)
2. Clic en **Create serving endpoint**

### 11.2 Configuración

| Campo | Valor |
|-------|-------|
| **Endpoint name** | `engie-peru-derate-ew` |
| **Model** | `TU_CATALOGO.engie_peru_pdm.derate_early_warning` |
| **Version** | La más reciente (versión 2+ del wrapper) |
| **Workload size** | Small |
| **Workload type** | CPU |
| **Scale to zero** | Activado (ahorra costos cuando no se usa) |

### 11.3 Crear y esperar

1. Clic en **Create**
2. El estado pasará por **Not Ready** → **Ready** (puede tardar varios minutos)
3. Cuando diga **Ready**, el endpoint está operativo

### 11.4 Probar desde la UI

1. Abre el endpoint `engie-peru-derate-ew`
2. Pestaña **Test** (o **Query endpoint**)
3. Pega un JSON de ejemplo con las columnas del modelo
4. Clic en **Send request**
5. La respuesta debe ser un número entre **0 y 1** (probabilidad de derateo)

> Las columnas requeridas son las mismas que en el notebook `02_pdm_model` (variables `FEATS`). Puedes copiar los nombres desde la salida del notebook o desde la pestaña **Schema** del modelo en MLflow.

---

## 12. Programar ejecuciones automáticas (opcional)

Para actualizar datos y predicciones de forma periódica:

1. Abre el Job **PdM Aerogeneradores POC**
2. Clic en **Edit**
3. Sección **Schedules** → **Add schedule**
4. Configura:
   - **Frequency:** Daily o Weekly
   - **Time:** hora de baja actividad (ej. 02:00)
   - **Timezone:** la de tu región
5. **Save**

Recomendación: programa solo el Job principal. El wrapper solo hace falta re-ejecutarlo si cambias el modelo base.

---

## 13. Checklist final

Marca cada ítem al completarlo:

- [ ] Schema `engie_peru_pdm` visible en Catalog Explorer
- [ ] Volumen `raw` con el CSV SCADA subido
- [ ] 3 notebooks importados en el workspace
- [ ] Variables `CATALOG` / `SCHEMA` actualizadas en los 3 notebooks
- [ ] Job principal creado con 2 tareas en cadena
- [ ] Job principal ejecutado con éxito (**Succeeded**)
- [ ] 6 tablas en `engie_peru_pdm` (bronze, silver, 4 gold)
- [ ] Modelo `derate_early_warning` versión 1 en UC
- [ ] Job wrapper ejecutado con éxito
- [ ] Modelo versión 2+ registrada
- [ ] Dashboard importado, warehouse asignado, datos visibles
- [ ] (Opcional) Endpoint en estado **Ready**
- [ ] (Opcional) Schedule configurado en el Job

---

## 14. Solución de problemas

### Errores en el notebook 01

| Mensaje | Causa | Solución |
|---------|-------|----------|
| `Path does not exist` / no encuentra CSV | Archivo no subido o nombre distinto | Verifica volumen `raw` y nombre exacto del archivo |
| `CATALOG_NOT_FOUND` | Catálogo incorrecto en celda 2 | Corrige `CATALOG = "..."` |
| `PERMISSION_DENIED` | Sin permiso en el catálogo | Pide permisos al admin |

### Errores en el notebook 02

| Mensaje | Causa | Solución |
|---------|-------|----------|
| `TABLE_OR_VIEW_NOT_FOUND: silver_scada_10min` | No se ejecutó el notebook 01 | Ejecuta/re-ejecuta `ingest_features` primero |
| Error en `mlflow.set_experiment` | Path de experimento no existe | Crea el experimento en ML → Experiments |
| `pip install` falla | Sin acceso a PyPI | Pide al admin habilitar cluster con acceso a internet o usar init script |

### Errores en el notebook 03

| Mensaje | Causa | Solución |
|---------|-------|----------|
| `Model version not found` | Modelo v1 no registrado | Ejecuta el Job principal completo antes |
| `RESOURCE_DOES_NOT_EXIST` | Nombre del modelo incorrecto | Verifica `MODEL = "catalog.schema.nombre"` |

### Dashboard vacío

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Todos los widgets vacíos | Warehouse no asignado | Asigna SQL Warehouse en el dashboard |
| Error SQL en dataset | Catálogo antiguo en consultas | Edita datasets y cambia el catálogo |
| KPIs en cero | Pipeline no generó gold | Re-ejecuta Job principal |

### Job falla en la tarea 2 pero la 1 OK

- Abre logs de `pdm_model`
- Suele ser timeout o memoria: aumenta el tamaño del cluster en la configuración del Job
- O ejecuta `02_pdm_model` manualmente en el notebook para ver el error detallado

---

## Apéndice A — Conectar el repo por Repos (Git)

Si tu workspace soporta **Repos**:

1. **Workspace** → **Repos** → **Add Repo**
2. **Git repository URL:** `https://github.com/mousasdatabricks/pdm.git`
3. **Git provider:** GitHub
4. Clic en **Create Repo**
5. Los notebooks quedan en `/Repos/tu.email@empresa.com/pdm/notebooks/`
6. Al crear los Jobs, usa esas rutas en lugar de importar manualmente

Ventaja: actualizaciones con **Pull** desde la UI del repo.

---

## Apéndice B — Ejecutar notebooks manualmente (sin Job)

Útil para depurar antes de crear el Job:

1. Abre `01_ingest_features`
2. Conecta compute (Serverless)
3. Menú **Run** → **Run all**
4. Espera que todas las celdas terminen (✓ verde)
5. Repite con `02_pdm_model` y luego `03_wrap_proba`

> En producción se recomienda usar Jobs para reproducibilidad y scheduling.

---

## Apéndice C — Rutas de menú por versión de UI

Databricks actualiza la interfaz periódicamente. Si no encuentras un menú:

| Lo que buscas | Ubicaciones posibles |
|---------------|---------------------|
| Catálogo / tablas | **Catalog**, **Data**, **Unity Catalog** |
| Jobs | **Jobs & Pipelines**, **Workflows** |
| Dashboards | **Dashboards**, **SQL** → **Dashboards** |
| Modelos ML | **Machine Learning** → **Models**, o dentro del **Catalog** |
| Serving | **Serving**, **Machine Learning** → **Serving** |
| SQL Editor | **SQL** → **SQL Editor** |

---

## ¿Necesitas la versión con terminal?

Para despliegue automatizado con **Databricks Asset Bundle** y CLI, consulta:

**[GUIA-DESPLIEGUE.md](./GUIA-DESPLIEGUE.md)**
