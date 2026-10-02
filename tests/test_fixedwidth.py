import os

from reconcilegate.contracts import CONTRACTS
from reconcilegate.fixedwidth import read_raw_lines, to_canonical_dataframe, validate_fixed_width_source, write_fixed_width

CONTRACT = CONTRACTS["vendor_claims_extract"]

ROW = {
    "claim_ref": "CLM-000001",
    "vendor_code": "V00001",
    "plant": "IT",
    "amount_cents": 12345,
    "status_code": "AP",
    "cycle": 3,
}


def test_clean_record_round_trips_and_validates(tmp_path):
    path = str(tmp_path / "claims.txt")
    write_fixed_width(path, [ROW], CONTRACT)
    lines = read_raw_lines(path)
    assert len(lines[0]) == CONTRACT.record_length
    failing = validate_fixed_width_source(lines, CONTRACT)
    assert failing == []
    df = to_canonical_dataframe(CONTRACT, lines)
    assert df.loc[0, "amount_cents"] == 12345


def test_short_record_flags_fixed_width_field_misaligned(tmp_path):
    path = str(tmp_path / "claims.txt")
    write_fixed_width(path, [ROW], CONTRACT, corrupt={0: "short"})
    lines = read_raw_lines(path)
    failing = validate_fixed_width_source(lines, CONTRACT)
    assert any(c.check == "fixed_width_field_misaligned" for c in failing)


def test_shifted_record_flags_fixed_width_field_misaligned(tmp_path):
    path = str(tmp_path / "claims.txt")
    write_fixed_width(path, [ROW, dict(ROW, claim_ref="CLM-000002")], CONTRACT, corrupt={1: "shifted"})
    lines = read_raw_lines(path)
    failing = validate_fixed_width_source(lines, CONTRACT)
    assert any(c.check == "fixed_width_field_misaligned" for c in failing)
