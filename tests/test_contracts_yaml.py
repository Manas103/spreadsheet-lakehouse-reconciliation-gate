from reconcilegate.config import ALL_SOURCES
from reconcilegate.contracts import CONTRACTS, load_contract


def test_all_nine_sources_have_a_loaded_yaml_contract():
    assert set(CONTRACTS.keys()) == set(ALL_SOURCES)
    assert len(CONTRACTS) == 9


def test_every_contract_has_watermark_and_owner():
    for name, c in CONTRACTS.items():
        assert c.owner, name
        assert c.watermark_column, name
        assert c.kind in ("excel", "csv", "rest_api", "fixed_width", "drifting_csv")


def test_expected_columns_all_trace_to_a_declared_field():
    for name, c in CONTRACTS.items():
        field_names = {f.name for f in c.fields}
        assert set(c.expected_columns) <= field_names, name


def test_fixed_width_contract_record_length_matches_field_layout():
    c = CONTRACTS["vendor_claims_extract"]
    assert c.record_length == sum(f.length for f in c.fields)
    # no overlapping byte ranges
    spans = sorted((f.start, f.start + f.length) for f in c.fields)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 == s2, "fields must tile the record with no gap or overlap"
