# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Wrapper de probabilidad para el endpoint de alerta
# MAGIC Envuelve el clasificador para que el endpoint devuelva la **probabilidad de derateo (0-1)**
# MAGIC en lugar de la clase, y registra una nueva versión del modelo en Unity Catalog.

# COMMAND ----------

import mlflow, pandas as pd
import mlflow.pyfunc
mlflow.set_registry_uri("databricks-uc")
MODEL = "serverless_stable_cvpomp_catalog.engie_peru_pdm.derate_early_warning"

# cargar el sklearn original (v1)
sk = mlflow.sklearn.load_model(f"models:/{MODEL}/1")
FEATS = list(sk.feature_names_in_)
print("features:", len(FEATS))

class ProbaWrapper(mlflow.pyfunc.PythonModel):
    def __init__(self, model, feats):
        self.model = model; self.feats = feats
    def predict(self, context, model_input):
        X = pd.DataFrame(model_input)[self.feats]
        return self.model.predict_proba(X)[:, 1]

# COMMAND ----------

# ejemplo para firma
sample = pd.DataFrame(sk.feature_names_in_).T
sample = pd.DataFrame([[0.0] * len(FEATS)], columns=FEATS)
wrapper = ProbaWrapper(sk, FEATS)
out = wrapper.predict(None, sample)
sig = mlflow.models.infer_signature(sample, out)

with mlflow.start_run(run_name="derate_proba_wrapper") as run:
    info = mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=wrapper,
        signature=sig,
        input_example=sample,
        registered_model_name=MODEL,
    )
    print("logged. run:", run.info.run_id)

# versión nueva registrada
from mlflow import MlflowClient
c = MlflowClient()
vers = sorted([int(v.version) for v in c.search_model_versions(f"name='{MODEL}'")])
print("VERSION_NUEVA:", vers[-1])
