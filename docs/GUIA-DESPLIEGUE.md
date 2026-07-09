# Guía de despliegue — Engie Perú PdM (para principiantes)

Esta guía explica cómo desplegar el proyecto **Mantenimiento Predictivo Aerogeneradores** en un workspace de Databricks, sin asumir experiencia previa con Asset Bundles ni MLflow.

**Tiempo estimado:** 45–90 minutos (primera vez).

---

## ¿Qué hace este proyecto?

1. **Lee datos SCADA** de dos aerogeneradores (temperaturas, potencia, viento, etc.).
2. **Calcula un Health Index** por turbina (temperaturas anómalas vs. comportamiento normal).
3. **Entrena un modelo** que predice si habrá **derateo** (pérdida de potencia) en las próximas 72 horas.
4. **Muestra resultados** en un dashboard Lakeview y expone el modelo como API.

---

## Requisitos previos

| Requisito | Detalle |
|-----------|---------|
| Workspace Databricks | Con Unity Catalog habilitado |
| Permisos | Crear schema, tablas, volúmenes, jobs y modelos en UC |
| SQL Warehouse | Serverless o Pro (para el dashboard) |
| Databricks CLI | Versión ≥ 0.292 — [instalación](https://docs.databricks.com/dev-tools/cli/install.html) |
| Datos SCADA | Archivo `DataScada_MLAeros_runinng.csv.gz` (~24 MB) |

---

## Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/mousasdatabricks/pdm.git
cd pdm
```

---

## Paso 2 — Autenticarse en Databricks

```bash
databricks auth login \
  --host https://TU-WORKSPACE.cloud.databricks.com \
  --profile mi-perfil
```

Verifica que funciona:

```bash
databricks current-user me --profile mi-perfil
```

> **Tip:** Sustituye `TU-WORKSPACE` por la URL de tu workspace (ej. `fevm-serverless-stable-cvpomp`).

---

## Paso 3 — Configurar el catálogo (Unity Catalog)

### Opción A — Interfaz web (recomendada para principiantes)

1. En Databricks, ve a **Data** → **Catalog Explorer**.
2. Elige un catálogo existente (o pide a tu admin que cree uno).
3. Abre **SQL Editor** y ejecuta el contenido de `sql/01_setup.sql`, cambiando el catálogo si hace falta:

```sql
USE CATALOG tu_catalogo;
CREATE SCHEMA IF NOT EXISTS engie_peru_pdm;
USE SCHEMA engie_peru_pdm;
CREATE VOLUME IF NOT EXISTS raw;
```

### Opción B — CLI

```bash
databricks schemas create engie_peru_pdm tu_catalogo --profile mi-perfil
databricks volumes create engie_peru_pdm raw tu_catalogo --profile mi-perfil
```

---

## Paso 4 — Subir los datos SCADA

El notebook de ingesta espera este archivo en el volumen:

```
/Volumes/<catalog>/engie_peru_pdm/raw/DataScada_MLAeros_runinng.csv.gz
```

### Desde la UI

1. **Catalog Explorer** → tu catálogo → `engie_peru_pdm` → **Volumes** → `raw`.
2. Clic en **Upload** y selecciona `DataScada_MLAeros_runinng.csv.gz`.

### Desde la CLI

```bash
databricks fs cp \
  ./DataScada_MLAeros_runinng.csv.gz \
  dbfs:/Volumes/tu_catalogo/engie_peru_pdm/raw/DataScada_MLAeros_runinng.csv.gz \
  --profile mi-perfil
```

> Sin este archivo, el notebook `01_ingest_features` fallará al leer el CSV.

---

## Paso 5 — Ajustar variables en los notebooks

Abre cada notebook en `notebooks/` y actualiza estas líneas si tu catálogo/schema difieren del default:

```python
CATALOG = "tu_catalogo"      # línea ~12 en 01 y 02
SCHEMA  = "engie_peru_pdm"
```

Archivos a revisar:

- `notebooks/01_ingest_features.py`
- `notebooks/02_pdm_model.py`
- `notebooks/03_wrap_proba.py` (usa el nombre completo del modelo UC)

---

## Paso 6 — Configurar el Asset Bundle

Edita `databricks.yml` y cambia el `host` de tu workspace:

```yaml
targets:
  dev:
    workspace:
      host: https://TU-WORKSPACE.cloud.databricks.com
    variables:
      catalog: tu_catalogo
      schema: engie_peru_pdm
```

Valida la configuración:

```bash
databricks bundle validate -t dev --profile mi-perfil
```

Si ves errores de permisos o host, revisa el perfil y la URL.

---

## Paso 7 — Desplegar notebooks y jobs

```bash
databricks bundle deploy -t dev --profile mi-perfil
```

Esto sube los notebooks al workspace y crea dos jobs:

| Job | Tareas |
|-----|--------|
| **Engie Peru - PdM Aerogeneradores POC** | `01_ingest_features` → `02_pdm_model` |
| **Engie PdM - proba wrapper** | `03_wrap_proba` |

---

## Paso 8 — Ejecutar el pipeline

### Desde la terminal

```bash
# Pipeline principal (ingesta + modelo)
databricks bundle run engie_peru_pdm_pipeline -t dev --profile mi-perfil

# Wrapper de probabilidad (después de que el modelo esté registrado)
databricks bundle run engie_peru_pdm_wrap_proba -t dev --profile mi-perfil
```

### Desde la UI

1. **Workflows** → **Jobs**.
2. Abre **Engie Peru - PdM Aerogeneradores POC**.
3. Clic en **Run now**.
4. Cuando termine con éxito, ejecuta **Engie PdM - proba wrapper**.

**Orden obligatorio:** primero el pipeline principal, luego el wrapper.

---

## Paso 9 — Importar el dashboard

1. En Databricks, ve a **Dashboards** → **Create dashboard** → **Import**.
2. Selecciona `dashboards/engie_peru_pdm.lvdash.json`.
3. Si el catálogo en las consultas SQL no coincide, edita cada dataset y reemplaza:
   - `serverless_stable_cvpomp_catalog` → `tu_catalogo`
4. Asigna un **SQL Warehouse** al dashboard.

El dashboard muestra:

- KPIs (energía no generada, ROC-AUC, turbinas)
- Health Index diario por turbina
- Power ratio y energía perdida
- Top drivers del modelo
- Tabla de alertas (`alert_score > 0.6`)

---

## Paso 10 (opcional) — Endpoint de serving

Para exponer el modelo como API REST:

1. **Serving** → **Create serving endpoint**.
2. Nombre sugerido: `engie-peru-derate-ew`.
3. Modelo: `<catalog>.engie_peru_pdm.derate_early_warning` (versión más reciente, la del wrapper).
4. Tamaño: **Small**, CPU, **Scale to zero** activado.

Prueba con un ejemplo (ajusta URL y token):

```bash
curl -X POST \
  "https://TU-WORKSPACE.cloud.databricks.com/serving-endpoints/engie-peru-derate-ew/invocations" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataframe_split": {"columns": ["rise_main_shaft_front_bearing_temp_C", "..."], "data": [[0.1, ...]]}}'
```

> Las columnas deben coincidir con las features del modelo (ver salida del notebook `02_pdm_model`).

---

## Verificación — checklist

Marca cada ítem cuando funcione:

- [ ] Schema `engie_peru_pdm` y volumen `raw` creados
- [ ] CSV SCADA subido al volumen
- [ ] Job principal completado sin errores
- [ ] Tablas `bronze_scada`, `silver_scada_10min`, `gold_*` visibles en Catalog Explorer
- [ ] Modelo `derate_early_warning` registrado en Unity Catalog
- [ ] Job wrapper completado (versión 2+ del modelo)
- [ ] Dashboard importado y con datos
- [ ] (Opcional) Endpoint de serving en estado **Ready**

---

## Solución de problemas

| Error | Causa probable | Solución |
|-------|----------------|----------|
| `Path does not exist` al leer CSV | Archivo no subido al volumen | Repetir Paso 4 |
| `CATALOG_NOT_FOUND` | Catálogo incorrecto en notebooks | Actualizar `CATALOG` en notebooks |
| `TABLE_OR_VIEW_NOT_FOUND` | Pipeline no ejecutado | Ejecutar job principal (Paso 8) |
| `Model version not found` en wrapper | Modelo aún no registrado | Ejecutar `02_pdm_model` primero |
| Dashboard vacío | Warehouse no asignado o tablas gold vacías | Asignar warehouse; re-ejecutar pipeline |
| `PERMISSION_DENIED` | Falta permiso en UC | Pedir `USE CATALOG`, `CREATE TABLE` al admin |

---

## Flujo resumido (diagrama)

```
[Subir CSV] → [Deploy bundle] → [Run job pipeline]
                                        ↓
                              [Tablas gold + modelo UC]
                                        ↓
                              [Run job wrapper] → [Endpoint opcional]
                                        ↓
                              [Importar dashboard]
```

---

## Siguientes pasos

- Programar el job con un **trigger** diario/semanal en Workflows.
- Conectar el endpoint a una app o alerta (email, Slack).
- Ajustar `HORIZON_HOURS` y `DERATE_RATIO` según operaciones del parque.
- Ampliar a más turbinas cuando haya datos SCADA adicionales.

---

## Ayuda

- Documentación Databricks Asset Bundles: https://docs.databricks.com/dev-tools/bundles/
- Acelerador Wind Turbines: buscar en Databricks Solution Accelerators
- Issues del repo: https://github.com/mousasdatabricks/pdm/issues
