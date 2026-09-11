"""The "to-Lakehouse" half of this repo's name: a load that clears the
gate (gate.py) is published into a small PySpark-built Parquet lakehouse,
partitioned by month, one table per source. No Databricks workspace
exists on this build machine (see README, "Honest framing", the same
disclosure `pharma-supply-kpi-lakehouse` makes); this is PySpark
`local[*]` writing partitioned Parquet, not a Delta Lake table or a
managed cluster.
"""
from __future__ import annotations

import os

import pandas as pd
from pyspark.sql import SparkSession


def build_spark(app_name: str = "reconcilegate-lakehouse") -> SparkSession:
    cores = max(1, (os.cpu_count() or 4) // 2)
    spark = (
        SparkSession.builder.appName(app_name)
        .master(f"local[{cores}]")
        .config("spark.driver.memory", "2g")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .getOrCreate()
    )
    return spark


def _flatten_excel_source(sheets: dict) -> pd.DataFrame:
    return pd.concat(sheets.values(), ignore_index=True)


def publish_load(spark: SparkSession, sources: dict, month: int, lakehouse_dir: str) -> None:
    for source in ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]:
        flat = _flatten_excel_source(sources[source])
        flat.columns = [str(c) for c in flat.columns]
        sdf = spark.createDataFrame(flat)
        dst = os.path.join(lakehouse_dir, source)
        sdf.write.mode("overwrite").option("partitionOverwriteMode", "dynamic").partitionBy("Month").parquet(dst)

    for source in ["erp_order_extract", "wms_shipment_extract"]:
        flat = sources[source]
        sdf = spark.createDataFrame(flat)
        dst = os.path.join(lakehouse_dir, source)
        sdf.write.mode("overwrite").option("partitionOverwriteMode", "dynamic").partitionBy("month").parquet(dst)
