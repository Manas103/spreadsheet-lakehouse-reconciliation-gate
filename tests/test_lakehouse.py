import os

from reconcilegate import config, datagen
from reconcilegate.lakehouse import publish_load


def test_publish_load_writes_all_six_sources(tmp_path, spark):
    batch = datagen.generate_clean_batch(config.SEED, 0)
    lakehouse_dir = str(tmp_path / "lakehouse")
    publish_load(spark, batch, 0, lakehouse_dir)

    for source in config.ALL_SOURCES:
        dst = os.path.join(lakehouse_dir, source)
        assert os.path.isdir(dst)
        df = spark.read.parquet(dst)
        assert df.count() > 0


def test_publish_load_dynamic_partition_does_not_wipe_other_months(tmp_path, spark):
    lakehouse_dir = str(tmp_path / "lakehouse2")
    batch0 = datagen.generate_clean_batch(config.SEED, 0)
    publish_load(spark, batch0, 0, lakehouse_dir)
    batch1 = datagen.generate_clean_batch(config.SEED, 1)
    publish_load(spark, batch1, 1, lakehouse_dir)

    df = spark.read.parquet(os.path.join(lakehouse_dir, "wms_shipment_extract"))
    months = sorted(r["month"] for r in df.select("month").distinct().collect())
    assert months == [0, 1]
