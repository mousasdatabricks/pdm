# Databricks notebook source
# MAGIC %md
# MAGIC # Engie Perú · Mantenimiento Predictivo Aerogeneradores
# MAGIC ## 02 · Modelo · NBM + Detección de derateo + Alerta temprana
# MAGIC
# MAGIC **Enfoque (alineado al acelerador oficial de Databricks para Wind Turbines):**
# MAGIC 1. **Normal Behavior Model (NBM):** un modelo por componente crítico aprende la
# MAGIC    temperatura *esperada* en condiciones sanas (a partir de potencia, viento, ambiente, pitch).
# MAGIC 2. **Residual** = temperatura real − esperada. Un residual que sube de forma sostenida
# MAGIC    es la firma temprana de degradación, **semanas antes** del derateo.
# MAGIC 3. **Health Index** = residual estandarizado agregado por turbina.
# MAGIC 4. **Alerta temprana:** clasificador que predice si habrá un episodio de derateo
# MAGIC    en el horizonte (default 72 h) a partir de la salud térmica actual.

# COMMAND ----------

# DBTITLE 1,Instalar dependencias
# MAGIC %pip install mlflow lightgbm xgboost typing_extensions --upgrade -q

# COMMAND ----------

# DBTITLE 1,Celda 2
CATALOG = "serverless_stable_cvpomp_catalog"
SCHEMA  = "engie_peru_pdm"
spark.sql(f"USE CATALOG {CATALOG}"); spark.sql(f"USE SCHEMA {SCHEMA}")

# Parámetros del MVP
BASELINE_DAYS   = 90      # ventana sana inicial para entrenar el NBM
HORIZON_HOURS   = 72      # horizonte de anticipación de la alerta
GAP_HOURS       = 6       # se ignoran las próximas 6h (queremos anticipar, no detectar)
DERATE_RATIO    = 0.90    # producing & power_ratio < 0.90  => derateo
STEPS_PER_HOUR  = 6       # 10-min -> 6 pasos/hora

import mlflow
import mlflow.sklearn
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score, average_precision_score

CRIT_TEMPS = [
    "main_shaft_front_bearing_temp_C", "main_shaft_rear_bearing_temp_C",
    "generator_bearing_temp_coupling_C", "generator_bearing_temp_non_coupling_C",
    "generator_winding_1_temp_C", "generator_winding_2_temp_high_C", "generator_winding_3_temp_high_C",
    "gearbox_bearing_temp_C",
    "transformer_winding_1_temp_C", "transformer_winding_2_temp_C", "transformer_winding_3_temp_C",
]
NBM_FEATURES = ["active_power_power_kW", "wind_speed_10min_avg_ms", "ambient_temp_C", "Pitch_angle_deg"]

pdf = spark.table("silver_scada_10min").toPandas()
pdf["ts"] = pd.to_datetime(pdf["ts"])
pdf = pdf.sort_values(["turbine", "ts"]).reset_index(drop=True)
print("rows:", len(pdf), "| turbines:", pdf.turbine.unique())

# COMMAND ----------

# MAGIC %md ### 1-3 · NBM, residuales y Health Index (por turbina)

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"/Shared/engie_peru_pdm")

frames = []
for turb, g in pdf.groupby("turbine"):
    g = g.sort_values("ts").reset_index(drop=True)
    t0 = g["ts"].min()
    base = g[(g["ts"] < t0 + pd.Timedelta(days=BASELINE_DAYS)) & (g["producing"] == 1)]
    res_cols = []
    for comp in CRIT_TEMPS:
        tr = base.dropna(subset=NBM_FEATURES + [comp])
        if len(tr) < 500:
            g["res_" + comp] = np.nan; res_cols.append("res_" + comp); continue
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08,
                                          max_depth=6, random_state=42)
        m.fit(tr[NBM_FEATURES], tr[comp])
        pred = m.predict(g[NBM_FEATURES])
        resid = g[comp] - pred
        # estandarizar con el residual sano del baseline
        bmask = (g["ts"] < t0 + pd.Timedelta(days=BASELINE_DAYS)) & (g["producing"] == 1)
        mu, sd = resid[bmask].mean(), resid[bmask].std() + 1e-6
        g["res_" + comp] = (resid - mu) / sd
        res_cols.append("res_" + comp)
    # solo consideramos residual cuando produce (en parada no hay calor que modelar)
    g.loc[g["producing"] == 0, res_cols] = np.nan
    # Health Index = residual estandarizado agregado, suavizado 24h
    g["health_index_raw"] = g[res_cols].mean(axis=1)
    g["health_index"] = (g["health_index_raw"]
                         .rolling(24 * STEPS_PER_HOUR, min_periods=STEPS_PER_HOUR).mean())
    frames.append(g)

df = pd.concat(frames).sort_values(["turbine", "ts"]).reset_index(drop=True)
print("Health Index por turbina (media global):")
print(df.groupby("turbine")["health_index"].mean())

# COMMAND ----------

# MAGIC %md ### 4 · Etiquetado de derateo + alerta temprana

# COMMAND ----------

# flag de derateo a 10 min
df["derate_flag"] = ((df["producing"] == 1) & (df["power_ratio"] < DERATE_RATIO)).astype(int)

H  = HORIZON_HOURS * STEPS_PER_HOUR
GP = GAP_HOURS * STEPS_PER_HOUR

def future_label(s):
    # 1 si hay derateo en la ventana (t+GAP , t+H]
    rev = s[::-1]
    fwd = rev.rolling(H, min_periods=1).max()[::-1]                 # cualquier derate en próximas H
    near = rev.rolling(GP, min_periods=1).max()[::-1]               # derate en próximas GAP
    fut = fwd.copy()
    # restamos la ventana inmediata para forzar anticipación real
    fut_excl = (s[::-1].rolling(H, min_periods=1).max()[::-1].fillna(0)
                - s[::-1].rolling(GP, min_periods=1).max()[::-1].fillna(0)).clip(lower=0)
    return (fut_excl > 0).astype(int)

parts = []
for turb, g in df.groupby("turbine"):
    g = g.sort_values("ts").reset_index(drop=True)
    g["y_future_derate"] = future_label(g["derate_flag"])
    parts.append(g)
df = pd.concat(parts).sort_values(["turbine", "ts"]).reset_index(drop=True)

print("Episodios de derateo (flags 10-min) por turbina:")
print(df.groupby("turbine")["derate_flag"].sum())
print("\nPrevalencia etiqueta futura (positivos):", round(df["y_future_derate"].mean(), 4))

# COMMAND ----------

# features de salud para el clasificador
RISE = ["rise_" + c for c in CRIT_TEMPS]
RES  = ["res_" + c for c in CRIT_TEMPS]
FEATS = RISE + RES + ["health_index", "wind_speed_10min_avg_ms", "ambient_temp_C",
                      "active_power_power_kW", "potenciaproducible_kW"]

# entrenamos/evaluamos solo cuando produce y NO está ya en derateo (anticipación genuina)
model_df = df[(df["producing"] == 1) & (df["derate_flag"] == 0)].dropna(subset=["health_index"]).copy()

# split temporal 70/30
cut = model_df["ts"].quantile(0.70)
train = model_df[model_df["ts"] <= cut]
test  = model_df[model_df["ts"] >  cut]
print(f"train={len(train)}  test={len(test)}  cut={cut}")
print(f"positivos train={train.y_future_derate.sum()}  test={test.y_future_derate.sum()}")

# COMMAND ----------

# DBTITLE 1,Celda 8
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from sklearn.inspection import permutation_importance

# --- Definir candidatos ---
candidates = {
    "HistGradientBoosting": HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_depth=6,
        l2_regularization=1.0, class_weight="balanced", random_state=42),
    "RandomForest": RandomForestClassifier(
        n_estimators=300, max_depth=12, class_weight="balanced",
        n_jobs=-1, random_state=42),
    "LightGBM": LGBMClassifier(
        n_estimators=300, learning_rate=0.06, max_depth=6,
        reg_lambda=1.0, is_unbalance=True, random_state=42, verbose=-1),
    "XGBoost": XGBClassifier(
        n_estimators=300, learning_rate=0.06, max_depth=6,
        reg_lambda=1.0, scale_pos_weight=(train["y_future_derate"] == 0).sum() / max(train["y_future_derate"].sum(), 1),
        use_label_encoder=False, eval_metric="logloss", random_state=42, verbosity=0),
    "LogisticRegression": LogisticRegression(
        max_iter=1000, class_weight="balanced", random_state=42),
}

mlflow.set_experiment("/Shared/engie_peru_pdm")
results = []
models_trained = {}

for name, model in candidates.items():
    with mlflow.start_run(run_name=f"compare_{name}") as run:
        mlflow.log_params(dict(model_name=name, baseline_days=BASELINE_DAYS,
                               horizon_hours=HORIZON_HOURS, gap_hours=GAP_HOURS,
                               derate_ratio=DERATE_RATIO, n_features=len(FEATS)))
        model.fit(train[FEATS].fillna(train[FEATS].median()), train["y_future_derate"])
        proba = model.predict_proba(test[FEATS].fillna(train[FEATS].median()))[:, 1]
        yt = test["y_future_derate"].values

        auc = roc_auc_score(yt, proba) if yt.sum() else float("nan")
        ap  = average_precision_score(yt, proba) if yt.sum() else float("nan")
        thr = 0.5
        yhat = (proba >= thr).astype(int)
        prec = precision_score(yt, yhat, zero_division=0)
        rec  = recall_score(yt, yhat, zero_division=0)

        row = {"model": name, "ROC_AUC": round(auc, 4), "Avg_Precision": round(ap, 4),
               "Precision@0.5": round(prec, 4), "Recall@0.5": round(rec, 4),
               "run_id": run.info.run_id}
        results.append(row)
        models_trained[name] = model
        mlflow.log_metrics({"roc_auc": auc, "avg_precision": ap,
                            "precision_at_0_5": prec, "recall_at_0_5": rec})
        print(f"  {name:25s} AUC={auc:.4f}  AP={ap:.4f}  P={prec:.4f}  R={rec:.4f}")

# --- Tabla comparativa ---
results_df = pd.DataFrame(results).sort_values("ROC_AUC", ascending=False)
print("\n" + "="*80)
print("COMPARATIVA DE MODELOS (ordenado por ROC-AUC)")
print("="*80)
display(results_df)

# --- Mejor modelo: registrar en UC ---
best_name = results_df.iloc[0]["model"]
clf = models_trained[best_name]
print(f"\n★ Mejor modelo: {best_name}")

with mlflow.start_run(run_name=f"best_{best_name}") as run:
    mlflow.log_params({"best_model": best_name})
    mlflow.log_metrics({"roc_auc": results_df.iloc[0]["ROC_AUC"],
                        "avg_precision": results_df.iloc[0]["Avg_Precision"]})
    sig = mlflow.models.infer_signature(
        train[FEATS].fillna(train[FEATS].median()),
        clf.predict_proba(train[FEATS].fillna(train[FEATS].median()))[:, 1])
    mlflow.sklearn.log_model(clf, "model", signature=sig,
        registered_model_name=f"{CATALOG}.{SCHEMA}.derate_early_warning")
    run_id = run.info.run_id
    print(f"  Registrado en UC: {CATALOG}.{SCHEMA}.derate_early_warning (run_id={run_id})")

# --- Importancia del mejor modelo ---
sub = test.sample(min(5000, len(test)), random_state=1)
pi = permutation_importance(clf, sub[FEATS].fillna(train[FEATS].median()), sub["y_future_derate"],
                            n_repeats=3, random_state=1, scoring="roc_auc")
imp = pd.Series(pi.importances_mean, index=FEATS).sort_values(ascending=False).head(12)
print(f"\nTop drivers ({best_name}):")
print(imp.round(4))

metrics = {"roc_auc": results_df.iloc[0]["ROC_AUC"], "avg_precision": results_df.iloc[0]["Avg_Precision"],
           "precision_at_0_5": results_df.iloc[0]["Precision@0.5"], "recall_at_0_5": results_df.iloc[0]["Recall@0.5"],
           "test_positives": float(yt.sum()), "test_rows": float(len(yt))}

# COMMAND ----------

# MAGIC %md ### 5 · Tablas Gold para tablero / Genie / Power BI

# COMMAND ----------

# puntuamos toda la serie con el modelo para el timeline
df["alert_score"] = np.nan
score_mask = df["producing"] == 1
Xall = df.loc[score_mask, FEATS]
df.loc[score_mask, "alert_score"] = clf.predict_proba(Xall.fillna(Xall.median()))[:, 1]

gold_cols = (["turbine", "ts", "active_power_power_kW", "potenciaproducible_kW",
              "power_ratio", "power_deficit_kW", "producing", "ambient_temp_C",
              "wind_speed_10min_avg_ms", "health_index", "derate_flag",
              "y_future_derate", "alert_score"] + RES + RISE)
gold = df[gold_cols].copy()
(spark.createDataFrame(gold)
 .write.mode("overwrite").option("overwriteSchema", True)
 .partitionBy("turbine").saveAsTable("gold_health_timeline"))

# episodios de derateo agregados por día
from pyspark.sql import functions as F
events = (spark.table("gold_health_timeline")
          .filter("derate_flag = 1")
          .groupBy("turbine", F.to_date("ts").alias("dia"))
          .agg(F.count("*").alias("intervalos_derateo_10min"),
               F.round(F.avg("power_ratio"), 3).alias("power_ratio_medio"),
               F.round(F.sum("power_deficit_kW") / 6.0, 1).alias("energia_perdida_kWh_aprox"),
               F.round(F.avg("health_index"), 3).alias("health_index_medio")))
events.write.mode("overwrite").option("overwriteSchema", True).saveAsTable("gold_derate_events")

# métricas del modelo
mrows = [(k, float(v)) for k, v in metrics.items()]
(spark.createDataFrame(mrows, ["metrica", "valor"])
 .write.mode("overwrite").option("overwriteSchema", True).saveAsTable("gold_model_metrics"))

# drivers
(spark.createDataFrame(imp.reset_index().rename(columns={"index":"feature", 0:"importancia"}))
 .write.mode("overwrite").option("overwriteSchema", True).saveAsTable("gold_alert_drivers"))

print("Gold listo: gold_health_timeline, gold_derate_events, gold_model_metrics, gold_alert_drivers")
display(spark.table("gold_derate_events").orderBy(F.desc("energia_perdida_kWh_aprox")).limit(20))