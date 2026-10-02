"""Fixed-width (column-positional, not delimited) read/write/validate for
``vendor_claims_extract``, the SFTP-dropped source. A fixed-width record
has no column delimiters at all; a field's identity is entirely its byte
offset and length, declared once per field in the contract (``start``,
``length``, and an optional ``pattern`` regex the sliced raw text must
fullmatch). This is the format's structural-integrity analog of
``excel_io.py``'s merged-header reconstruction: there, a column's name
can survive while its physical position drifts (``merged_header_misaligned``);
here, a record's *length* can be wrong, or (more subtly) its length can
be right while an insertion earlier in the line has shifted every field
after it out of its declared slice (``fixed_width_field_misaligned``
catches both, see ``validate_fixed_width_source``).
"""
from __future__ import annotations

import re

import pandas as pd

from reconcilegate.contracts import SourceContract
from reconcilegate.validate import FailingCheck, _duplicate_key_checks, _field_checks


def _format_field_value(fspec, value) -> str:
    if fspec.dtype == "int":
        s = str(int(value))
        if len(s) > fspec.length:
            raise ValueError(f"{fspec.name}={value!r} does not fit in {fspec.length} bytes")
        return s.zfill(fspec.length)
    s = str(value)
    if len(s) > fspec.length:
        raise ValueError(f"{fspec.name}={value!r} does not fit in {fspec.length} bytes")
    return s.ljust(fspec.length)


def format_record(contract: SourceContract, row: dict) -> str:
    line = [" "] * contract.record_length
    for fspec in contract.fields:
        s = _format_field_value(fspec, row[fspec.name])
        line[fspec.start : fspec.start + fspec.length] = list(s)
    return "".join(line)


def write_fixed_width(path: str, rows: list, contract: SourceContract, corrupt: dict | None = None) -> None:
    """``corrupt``, if given, is ``{row_index: "short" | "shifted"}`` used
    only to build the deliberately-broken ``fixed_width_field_misaligned``
    fixture:
      - "short": the record is truncated by a few bytes (record length wrong).
      - "shifted": a single space character is inserted in the middle of
        the record, so the line's total length is unchanged but every
        field after the insertion point is read out of its declared slice
        (byte offsets wrong, not record length).
    """
    corrupt = corrupt or {}
    with open(path, "w", newline="\n") as fh:
        for i, row in enumerate(rows):
            line = format_record(contract, row)
            flavor = corrupt.get(i)
            if flavor == "short":
                line = line[:-4]
            elif flavor == "shifted":
                mid = contract.record_length // 2
                line = line[:mid] + " " + line[mid:-1]
            fh.write(line + "\n")


def read_raw_lines(path: str) -> list:
    with open(path, "r") as fh:
        return [line.rstrip("\n") for line in fh if line.strip("\n") != ""]


def parse_record(contract: SourceContract, line: str) -> dict:
    """Best-effort slice-and-strip parse, used to build a canonical
    DataFrame even from a structurally broken line, so that downstream
    generic checks (null/type/range) can also fire on it, the same
    "two checks can legitimately co-fire" behavior documented for
    ``unexpected_unit_value`` in the README.
    """
    out = {}
    for fspec in contract.fields:
        end = fspec.start + fspec.length
        raw = line[fspec.start : end] if len(line) >= fspec.start else ""
        out[fspec.name] = raw.strip()
    return out


def to_canonical_dataframe(contract: SourceContract, lines: list) -> pd.DataFrame:
    rows = [parse_record(contract, line) for line in lines]
    df = pd.DataFrame(rows, columns=contract.expected_columns)
    for fspec in contract.fields:
        if fspec.dtype in ("int", "float") and fspec.name in df.columns:
            df[fspec.name] = pd.to_numeric(df[fspec.name], errors="coerce")
    return df


def validate_fixed_width_source(lines: list, contract: SourceContract) -> list:
    failing = []
    for idx, line in enumerate(lines):
        if len(line) != contract.record_length:
            failing.append(
                FailingCheck(
                    "fixed_width_field_misaligned",
                    contract.source_name,
                    f"row {idx}: record length {len(line)} != expected {contract.record_length}",
                )
            )
            continue  # byte offsets are unreliable past this point for this record
        for fspec in contract.fields:
            if fspec.pattern is None:
                continue
            raw = line[fspec.start : fspec.start + fspec.length]
            if not re.fullmatch(fspec.pattern, raw):
                failing.append(
                    FailingCheck(
                        "fixed_width_field_misaligned",
                        contract.source_name,
                        f"row {idx}: field {fspec.name!r} value {raw!r} does not match expected "
                        f"shape {fspec.pattern!r} (byte offsets likely misaligned)",
                    )
                )

    df = to_canonical_dataframe(contract, lines)
    failing.extend(_field_checks(df, contract))
    failing.extend(_duplicate_key_checks(df, contract))
    return failing
