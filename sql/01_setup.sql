-- Mantenimiento Predictivo Aerogeneradores
-- Script inicial: catálogo, schema y volumen para datos SCADA crudos.
--
-- Ajusta los nombres según tu entorno antes de ejecutar.

-- CREATE CATALOG IF NOT EXISTS <tu_catalogo>;
-- USE CATALOG <tu_catalogo>;

CREATE SCHEMA IF NOT EXISTS engie_peru_pdm
  COMMENT 'POC Mantenimiento Predictivo — Aerogeneradores';

USE SCHEMA engie_peru_pdm;

CREATE VOLUME IF NOT EXISTS raw
  COMMENT 'Datos SCADA crudos (CSV comprimido)';

-- Después de crear el volumen, sube el archivo:
--   /Volumes/<catalog>/<schema>/raw/DataScada_MLAeros_runinng.csv.gz
--
-- Las tablas bronze/silver/gold se crean automáticamente al ejecutar los notebooks.
