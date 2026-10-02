from reconcilegate import config, datagen


def test_clean_batch_has_all_six_sources():
    batch = datagen.generate_clean_batch(config.SEED, 0)
    assert set(batch.keys()) == set(config.ALL_SOURCES)


def test_clean_batch_excel_sources_have_all_country_tabs():
    batch = datagen.generate_clean_batch(config.SEED, 0)
    for source in ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]:
        assert set(batch[source].keys()) == set(config.COUNTRIES)


def test_clean_batch_is_deterministic():
    a = datagen.generate_clean_batch(config.SEED, 3)
    b = datagen.generate_clean_batch(config.SEED, 3)
    for source in ["shipment_log", "returns_register", "downtime_log", "complaint_tracker"]:
        for country in config.COUNTRIES:
            assert a[source][country].equals(b[source][country])
    assert a["erp_order_extract"].equals(b["erp_order_extract"])
    assert a["wms_shipment_extract"].equals(b["wms_shipment_extract"])


def test_clean_batch_shipment_totals_reconcile_exactly_in_canonical_units():
    batch = datagen.generate_clean_batch(config.SEED, 5)
    factors = config.UNIT_CONVERSION["shipment_log"]["factors"]
    wms = batch["wms_shipment_extract"].set_index("plant")["shipped_kg_total"]
    for country, df in batch["shipment_log"].items():
        canonical_total = sum(q * factors[u] for q, u in zip(df["Quantity"], df["Unit"]))
        # Rows are rounded to 3 decimals on write (realistic: a human types a
        # rounded number into Excel), so this reconciles to that precision,
        # not to floating-point precision; the gate's own 1% tolerance
        # (config.RECONCILIATION_TOLERANCE_PCT) comfortably absorbs it.
        assert abs(canonical_total - wms[country]) < 0.01


def test_all_original_eight_defect_types_generate_without_error():
    for defect_type in datagen.DEFECT_INJECTORS:
        batch, source, check = datagen.generate_defect_batch(config.SEED, 50, defect_type, pool="original")
        assert check.startswith(defect_type)
        assert source in config.ALL_SOURCES


def test_all_vendor_defect_types_generate_without_error():
    for defect_type in datagen.VENDOR_DEFECT_INJECTORS:
        batch, source, check = datagen.generate_defect_batch(config.SEED, 150, defect_type, pool="vendor")
        assert check.startswith(defect_type)
        assert source in config.ALL_SOURCES
