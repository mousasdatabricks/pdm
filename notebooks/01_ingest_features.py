# Databricks notebook source
# MAGIC %md
# MAGIC # Engie Perú · Mantenimiento Predictivo Aerogeneradores
# MAGIC ## 01 · Ingesta (Bronze) + Features (Silver)
# MAGIC
# MAGIC Lee la data SCADA real (AEG_51, AEG_52 · jul-2025 → jun-2026 · cadencia 1 min),
# MAGIC la materializa en Delta, remuestrea a 10 min y deriva las señales de
# MAGIC sub-desempeño (derateo) y de sobre-temperatura de componentes críticos.

# COMMAND ----------

CATALOG = "serverless_stable_cvpomp_catalog"
SCHEMA  = "engie_peru_pdm"
RAW     = f"/Volumes/{CATALOG}/{SCHEMA}/raw/DataScada_MLAeros_runinng.csv.gz"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md ### Bronze · carga cruda tipada

# COMMAND ----------

from pyspark.sql import functions as F, types as T

raw = (spark.read
       .option("header", True)
       .option("inferSchema", False)
       .csv(RAW))

num_cols = [c for c in raw.columns if c not in ("Aero", "Date")]
bronze = raw.withColumn("ts", F.to_timestamp("Date", "yyyy-MM-dd HH:mm:ss"))
for c in num_cols:
    bronze = bronze.withColumn(c, F.col(c).cast("double"))
bronze = (bronze
          .withColumnRenamed("Aero", "turbine")
          .drop("Date"))

(bronze.write.mode("overwrite").option("overwriteSchema", True)
 .saveAsTable("bronze_scada"))

print("bronze_scada rows:", spark.table("bronze_scada").count())
display(spark.sql("SELECT turbine, count(*) n, min(ts) desde, max(ts) hasta FROM bronze_scada GROUP BY turbine"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Silver · remuestreo a 10 min + features
# MAGIC - **Componentes críticos** monitoreados: rodamientos eje principal, rodamientos/bobinados generador, rodamiento multiplicadora (gearbox), bobinados transformador.
# MAGIC - **`power_ratio`** = potencia activa / potencia producible → utilización de capacidad (proxy directo de derateo).
# MAGIC - **`temp_rise_*`** = temperatura del componente − ambiente → aísla el calor generado por la máquina del clima.
# MAGIC - **`producing`** = la turbina está generando con viento suficiente.

# COMMAND ----------

CRIT_TEMPS = [
    "main_shaft_front_bearing_temp_C", "main_shaft_rear_bearing_temp_C",
    "generator_bearing_temp_coupling_C", "generator_bearing_temp_non_coupling_C",
    "generator_winding_1_temp_C", "generator_winding_2_temp_high_C", "generator_winding_3_temp_high_C",
    "gearbox_bearing_temp_C",
    "transformer_winding_1_temp_C", "transformer_winding_2_temp_C", "transformer_winding_3_temp_C",
]
OPS = ["ambient_temp_C", "active_power_power_kW", "active_power_setpoint_kW",
       "active_power_setpoint_pct", "wind_speed_ms", "wind_speed_10min_avg_ms",
       "Pitch_angle_deg", "potenciaproducible_kW"]

b = spark.table("bronze_scada")
# ventana de 10 minutos
b = b.withColumn("ts10", (F.floor(F.col("ts").cast("long") / 600) * 600).cast("timestamp"))

agg = [F.avg(c).alias(c) for c in CRIT_TEMPS + OPS]
silver = (b.groupBy("turbine", "ts10").agg(*agg)
          .withColumnRenamed("ts10", "ts")
          .orderBy("turbine", "ts"))

# señales derivadas
silver = (silver
    .withColumn("power_ratio",
                F.when(F.col("potenciaproducible_kW") > 50,
                       F.col("active_power_power_kW") / F.col("potenciaproducible_kW")))
    .withColumn("power_deficit_kW",
                F.greatest(F.lit(0.0), F.col("potenciaproducible_kW") - F.col("active_power_power_kW")))
    .withColumn("producing",
                ((F.col("wind_speed_10min_avg_ms") > 4.0) & (F.col("potenciaproducible_kW") > 100)).cast("int")))

for c in CRIT_TEMPS:
    silver = silver.withColumn("rise_" + c, F.col(c) - F.col("ambient_temp_C"))

silver = silver.na.drop(subset=["active_power_power_kW", "wind_speed_10min_avg_ms", "ambient_temp_C"])

(silver.write.mode("overwrite").option("overwriteSchema", True)
 .partitionBy("turbine").saveAsTable("silver_scada_10min"))

n = spark.table("silver_scada_10min").count()
print("silver_scada_10min rows:", n)
display(spark.sql("""
  SELECT turbine, count(*) n,
         round(avg(power_ratio),3) avg_power_ratio,
         round(avg(CASE WHEN producing=1 THEN power_ratio END),3) avg_ratio_producing
  FROM silver_scada_10min GROUP BY turbine"""))