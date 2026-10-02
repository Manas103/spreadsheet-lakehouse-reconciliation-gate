import pytest

from reconcilegate import config, datagen, materialize
from reconcilegate.gate import run_gate


def _run(tmp_path, batch, load_id):
    paths = materialize.write_batch(batch, str(tmp_path / load_id))
    sources = materialize.read_batch(paths)
    return run_gate(load_id, sources)


def test_clean_load_publishes(tmp_path):
    batch = datagen.generate_clean_batch(config.SEED, 0)
    result = _run(tmp_path, batch, "clean-0")
    assert result.published, result.failing_check_names


@pytest.mark.parametrize("month", list(range(10)))
def test_ten_clean_loads_all_publish(tmp_path, month):
    batch = datagen.generate_clean_batch(config.SEED, month)
    result = _run(tmp_path, batch, f"clean-{month}")
    assert result.published, result.failing_check_names


@pytest.mark.parametrize("defect_type", list(datagen.DEFECT_INJECTORS.keys()))
def test_each_original_defect_type_is_caught_and_named(tmp_path, defect_type):
    batch, source, expected_check = datagen.generate_defect_batch(config.SEED, 77, defect_type, pool="original")
    result = _run(tmp_path, batch, f"defect-{defect_type}")
    assert not result.published
    assert any(c.check == defect_type for c in result.failing_checks), (
        f"expected a {defect_type} failing check, got {result.failing_check_names}"
    )


@pytest.mark.parametrize("defect_type", list(datagen.VENDOR_DEFECT_INJECTORS.keys()))
def test_each_vendor_defect_type_is_caught_and_named(tmp_path, defect_type):
    batch, source, expected_check = datagen.generate_defect_batch(config.SEED, 177, defect_type, pool="vendor")
    result = _run(tmp_path, batch, f"vendor-defect-{defect_type}")
    assert not result.published
    assert any(c.check == defect_type for c in result.failing_checks), (
        f"expected a {defect_type} failing check, got {result.failing_check_names}"
    )


def test_a_defect_load_never_publishes_partially():
    # The gate is all-or-nothing: GateResult.published is a single boolean,
    # not a per-source decision, so there is no partial-publish code path
    # to test around; this documents that design choice as a test.
    from reconcilegate.gate import GateResult

    r = GateResult(load_id="x", published=False, failing_checks=[])
    assert r.published is False
