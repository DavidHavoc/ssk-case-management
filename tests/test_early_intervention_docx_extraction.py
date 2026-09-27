"""Synthetic OOXML fixtures for the reviewed paired-row register extractor."""

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tools import extract_early_intervention_docx as extractor

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SCRIPT = Path(extractor.__file__).resolve()


def cell(row, value):
    result = ET.SubElement(row, W + "tc")
    for line in value.split("\n"):
        paragraph = ET.SubElement(result, W + "p")
        ET.SubElement(ET.SubElement(paragraph, W + "r"), W + "t").text = line
    return result


def register(*, heading="ფორმა N2.2.1\n2026 ივნისი", records=1):
    document = ET.Element(W + "document")
    table = ET.SubElement(ET.SubElement(document, W + "body"), W + "tbl")
    heading_cell = cell(ET.SubElement(table, W + "tr"), "")
    nested = ET.SubElement(heading_cell, W + "tbl")
    for text in heading.split("\n"):
        cell(ET.SubElement(nested, W + "tr"), text)
    for values in (("center", "month", "year"), extractor.HEADERS):
        row = ET.SubElement(table, W + "tr")
        for value in values:
            cell(row, value)
    for number in range(1, records + 1):
        values = (
            "p 1" if number == 1 else str(number),
            f"V-{number}",
            "Synthetic",
            f"Person{number}",
            f"000 0000{number:04}",
            "15.06.2020.",
            "ინდივიდუალური",
            "7",
            "ბინაზე",
            "არა",
            "Synthetic Guardian",
        )
        for service_values in (
            values,
            ("", "", "", "", "", "", "ინდივიდუალური", "1", "ცენტრში", "კი", ""),
        ):
            row = ET.SubElement(table, W + "tr")
            for value in service_values:
                cell(row, value)
    cell(ET.SubElement(table, W + "tr"), "თარიღი: __________________")
    return document


def write_docx(tmp_path, document, *, extra=None):
    path = tmp_path / "synthetic-register.docx"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", ET.tostring(document, encoding="utf-8"))
        if extra is not None:
            archive.writestr("synthetic-extra.txt", extra)
    return path


def physical_rows(document):
    return document.findall("w:body/w:tbl/w:tr", extractor.NS)


def replace_cell(row, index, value):
    target = row.findall("w:tc", extractor.NS)[index]
    target.find("w:p/w:r/w:t", extractor.NS).text = value


def test_extract_preserves_nested_heading_and_paired_source_evidence(tmp_path):
    path = write_docx(tmp_path, register(records=2))

    result = extractor.extract(path)

    assert result["format"] == "early_intervention_docx_v1"
    assert result["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["source_heading"] == "ფორმა N2.2.1\n2026 ივნისი"
    assert [row["number"] for row in result["rows"]] == [1, 2]
    first = result["rows"][0]
    assert first["personal_id"] == "000 00000001"
    assert first["birth_date"] == "15.06.2020."
    assert first["guardian"] == "Synthetic Guardian"
    assert first["services"] == [
        {"kind": "ინდივიდუალური", "count": "7", "location": "ბინაზე", "supervision": "არა"},
        {"kind": "ინდივიდუალური", "count": "1", "location": "ცენტრში", "supervision": "კი"},
    ]


@pytest.mark.parametrize("heading", ("", "Unrecognized form"))
def test_unreviewed_heading_fails_closed(tmp_path, heading):
    with pytest.raises(ValueError, match="heading"):
        extractor.extract(write_docx(tmp_path, register(heading=heading)))


@pytest.mark.parametrize("row_index", (1, 2, 3, 4, 5))
def test_missing_columns_fail_closed(tmp_path, row_index):
    document = register()
    row = physical_rows(document)[row_index]
    row.remove(row.findall("w:tc", extractor.NS)[-1])

    with pytest.raises(ValueError):
        extractor.extract(write_docx(tmp_path, document))


def test_empty_main_row_fails_with_review_error(tmp_path):
    document = register()
    physical_rows(document)[3].clear()

    with pytest.raises(ValueError, match="Row 1: layout"):
        extractor.extract(write_docx(tmp_path, document))


@pytest.mark.parametrize("sequence", ("0", "2", "p 2", "1.0", "1 2"))
def test_wrong_first_sequence_fails_closed(tmp_path, sequence):
    document = register()
    replace_cell(physical_rows(document)[3], 0, sequence)

    with pytest.raises(ValueError, match="Row 1: layout"):
        extractor.extract(write_docx(tmp_path, document))


def test_stray_prefix_is_not_allowed_after_first_row(tmp_path):
    document = register(records=2)
    replace_cell(physical_rows(document)[5], 0, "p 2")

    with pytest.raises(ValueError, match="Row 2: layout"):
        extractor.extract(write_docx(tmp_path, document))


@pytest.mark.parametrize("column", (0, 1, 2, 3, 4, 5, 10))
def test_continuation_cannot_contain_another_identity(tmp_path, column):
    document = register()
    replace_cell(physical_rows(document)[4], column, "unexpected identity")

    with pytest.raises(ValueError, match="Row 1: layout"):
        extractor.extract(write_docx(tmp_path, document))


def test_unpaired_service_rows_fail_closed(tmp_path):
    document = register(records=2)
    table = document.find("w:body/w:tbl", extractor.NS)
    table.remove(physical_rows(document)[6])

    with pytest.raises(ValueError, match="Unpaired"):
        extractor.extract(write_docx(tmp_path, document))


@pytest.mark.parametrize("column,value", ((6, ""), (7, "-1"), (7, "1.5"), (8, "")))
def test_invalid_service_evidence_fails_closed(tmp_path, column, value):
    document = register()
    replace_cell(physical_rows(document)[4], column, value)

    with pytest.raises(ValueError, match="service evidence"):
        extractor.extract(write_docx(tmp_path, document))


def test_expanded_archive_limit_is_checked_before_xml_extraction(tmp_path):
    path = write_docx(tmp_path, register(), extra=b"x" * (50 * 1024 * 1024))
    assert path.stat().st_size < 10 * 1024 * 1024

    with pytest.raises(ValueError, match="Expanded DOCX"):
        extractor.extract(path)


def run_cli(path, output):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_writes_restricted_output_and_only_aggregate_stdout(tmp_path):
    path = write_docx(tmp_path, register())
    output = tmp_path / "restricted-output.json"

    result = run_cli(path, output)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "beneficiaries": 1,
        "source_service_lines": 2,
        "reported_service_count": 8,
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text())["rows"][0]["first_name"] == "Synthetic"


def test_cli_never_overwrites_existing_output(tmp_path):
    path = write_docx(tmp_path, register())
    output = tmp_path / "existing-output.json"
    output.write_text("keep existing file")

    result = run_cli(path, output)

    assert result.returncode != 0
    assert result.stdout == ""
    assert output.read_text() == "keep existing file"


def test_cli_rejects_output_inside_repository(tmp_path):
    path = write_docx(tmp_path, register())
    output = SCRIPT.parent.parent / "synthetic-extraction-output.json"

    result = run_cli(path, output)

    assert result.returncode != 0
    assert "outside the repository" in result.stderr
    assert not output.exists()
