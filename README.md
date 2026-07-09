# Mantenimiento Predictivo Aerogeneradores

POC de **mantenimiento predictivo** para parque eólico (aerogeneradores AEG_51 y AEG_52) usando datos SCADA reales. Detecta **derateo** (sub-desempeño) y genera **alertas tempranas** semanas antes del evento, siguiendo el enfoque del acelerador oficial de Databricks para turbinas eólicas.

## Arquitectura

```
CSV SCADA (Volume/raw)
        ↓
01_ingest_features  →  bronze_scada + silver_scada_10min
        ↓
02_pdm_model        →  NBM + Health Index + clasificador de alerta
        ↓                  gold_* tables + modelo UC
03_wrap_proba       →  endpoint de probabilidad (0–1)
        ↓
Lakeview Dashboard  →  KPIs, health, energía perdida, alertas
```

## Contenido del repositorio

| Ruta | Descripción |
|------|-------------|
| `notebooks/01_ingest_features.py` | Ingesta Bronze + features Silver (10 min) |
| `notebooks/02_pdm_model.py` | Normal Behavior Model, Health Index, alerta temprana |
| `notebooks/03_wrap_proba.py` | Wrapper MLflow para endpoint de probabilidad |
| `dashboards/engie_peru_pdm.lvdash.json` | Dashboard Lakeview |
| `sql/01_setup.sql` | Creación de schema y volumen |
| `resources/pdm_pipeline.job.yml` | Jobs de Databricks (Asset Bundle) |
| `docs/GUIA-DESPLIEGUE-UI.md` | **Guía por interfaz gráfica (sin terminal)** |
| `docs/GUIA-DESPLIEGUE.md` | Guía con CLI + Asset Bundle |

## Tablas Unity Catalog (generadas por los notebooks)

| Tabla | Capa | Contenido |
|-------|------|-----------|
| `bronze_scada` | Bronze | SCADA crudo tipado |
| `silver_scada_10min` | Silver | Remuestreo 10 min + features térmicas |
| `gold_health_timeline` | Gold | Health Index, alert_score, derateo |
| `gold_derate_events` | Gold | Episodios de derateo por día |
| `gold_model_metrics` | Gold | Métricas del clasificador (ROC-AUC, etc.) |
| `gold_alert_drivers` | Gold | Importancia de variables |

## Modelo y endpoint

- **Modelo UC:** `<catalog>.engie_peru_pdm.derate_early_warning`
- **Endpoint:** `engie-peru-derate-ew` (devuelve probabilidad de derateo en 72 h)

## Despliegue

| Perfil | Guía |
|--------|------|
| **Interfaz gráfica (sin terminal)** | **[docs/GUIA-DESPLIEGUE-UI.md](docs/GUIA-DESPLIEGUE-UI.md)** |
| **CLI + Asset Bundle** | [docs/GUIA-DESPLIEGUE.md](docs/GUIA-DESPLIEGUE.md) |

Resumen CLI:

```bash
git clone https://github.com/mousasdatabricks/pdm.git
cd pdm

databricks auth login --host https://TU-WORKSPACE.cloud.databricks.com --profile tu-perfil
databricks bundle validate -t dev -p tu-perfil
databricks bundle deploy -t dev -p tu-perfil
databricks bundle run engie_peru_pdm_pipeline -t dev -p tu-perfil
```

## Parámetros clave (notebook 02)

| Parámetro | Default | Significado |
|-----------|---------|-------------|
| `BASELINE_DAYS` | 90 | Ventana sana para entrenar NBM |
| `HORIZON_HOURS` | 72 | Horizonte de anticipación de alerta |
| `GAP_HOURS` | 6 | Ignora derateo inmediato (solo anticipación) |
| `DERATE_RATIO` | 0.90 | Umbral de sub-desempeño |

## Licencia

Uso interno / demo. Los datos SCADA son propiedad del cliente.
