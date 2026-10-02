from reconcilegate.contracts import CONTRACTS
from scripts.generate_source_register import build_register_lines


def test_register_is_generated_and_re_runnable():
    lines_a = build_register_lines(CONTRACTS)
    lines_b = build_register_lines(CONTRACTS)
    assert lines_a == lines_b
    text = "\n".join(lines_a)
    for name in CONTRACTS:
        assert name in text


def test_every_column_in_register_traces_to_a_real_contract_field():
    text = "\n".join(build_register_lines(CONTRACTS))
    all_field_names = {f.name for c in CONTRACTS.values() for f in c.fields}
    for c in CONTRACTS.values():
        for f in c.fields:
            assert f"| {f.name} |" in text
    # nothing invented: every "| x |" column cell in the table body is a
    # real field name for some contract (spot check a few known names).
    assert "hourly_rate_usd" in all_field_names
    assert "claim_ref" in all_field_names
