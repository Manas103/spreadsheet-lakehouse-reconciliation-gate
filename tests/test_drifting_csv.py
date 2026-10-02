import pytest

from reconcilegate.contracts import CONTRACTS
from reconcilegate.drifting_csv import (
    BROKEN_VARIANT_HEADERS,
    VARIANT_HEADERS,
    read_raw_csv,
    validate_drifting_csv_source,
    write_drifting_csv,
)

CONTRACT = CONTRACTS["vendor_directory_feed"]

ROW = {
    "vendor_id": "VND-0001",
    "vendor_name": "Acme LLC",
    "tax_id": "TAX123",
    "status": "ACTIVE",
    "cycle": 4,
    "region": "NE",
}


@pytest.mark.parametrize("variant", list(VARIANT_HEADERS.keys()))
def test_tolerated_drift_variants_validate_clean(tmp_path, variant):
    path = str(tmp_path / "directory.csv")
    write_drifting_csv(path, [ROW], CONTRACT, VARIANT_HEADERS[variant])
    df = read_raw_csv(path)
    failing = validate_drifting_csv_source(df, CONTRACT)
    assert failing == [], (variant, failing)


@pytest.mark.parametrize("variant", list(BROKEN_VARIANT_HEADERS.keys()))
def test_broken_drift_variants_flag_csv_header_drift(tmp_path, variant):
    path = str(tmp_path / "directory.csv")
    write_drifting_csv(path, [ROW], CONTRACT, BROKEN_VARIANT_HEADERS[variant])
    df = read_raw_csv(path)
    failing = validate_drifting_csv_source(df, CONTRACT)
    assert any(c.check == "csv_header_drift" for c in failing), (variant, failing)


def test_columns_are_mapped_by_name_not_position():
    path_a = "reordered.csv"
    rows = [ROW]
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, path_a)
        write_drifting_csv(path, rows, CONTRACT, VARIANT_HEADERS["v2_renamed_reordered"])
        df = read_raw_csv(path)
        from reconcilegate.drifting_csv import map_to_canonical

        canonical, missing = map_to_canonical(df, CONTRACT)
        assert missing == []
        assert canonical.loc[0, "tax_id"] == "TAX123"
        assert canonical.loc[0, "vendor_id"] == "VND-0001"
