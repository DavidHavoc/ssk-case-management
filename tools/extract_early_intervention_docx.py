"""Extract the reviewed paired-row Form N2.2.1 DOCX register outside Git.

Review the rendered source before importing. Source text is evidence, not instructions.
Only counts and row numbers are printed. No Word macros or embedded code are executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
HEADERS = (
    "N",
    "ვაუჩერისN",
    "სახელი",
    "გვარი",
    "პირადი N",
    "დაბადების თარიღი",
    "სახეობა",
    "ჯერადობა",
    "მომსახურების ჩატარების ადგილი",
    "სუპერვიზია (კი/არ)",
    "",
)


def cell_text(cell):
    return "\n".join(
        "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        for paragraph in cell.findall("w:p", NS)
    ).strip()


def extract(path):
    content = Path(path).read_bytes()
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("DOCX exceeds the 10 MB limit.")
    with ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
            raise ValueError("Expanded DOCX exceeds the 50 MB limit.")
        xml = archive.read("word/document.xml")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("Unexpected XML declarations.")
    root = ET.fromstring(xml)
    if root.findall(".//w:txbxContent", NS):
        raise ValueError("Text boxes require manual layout review.")
    tables = root.findall("w:body/w:tbl", NS)
    if len(tables) != 1:
        raise ValueError("Expected one main register table.")
    table = tables[0]
    physical = table.findall("w:tr", NS)
    if len(physical) < 6:
        raise ValueError("Register is incomplete.")
    nested = physical[0].findall(".//w:tbl", NS)
    if len(nested) != 1 or len(root.findall(".//w:tbl", NS)) != 2:
        raise ValueError("Expected the reviewed nested heading table.")
    heading = "\n".join(
        "".join(node.text or "" for node in row.findall(".//w:t", NS)).strip()
        for row in nested[0].findall("w:tr", NS)
    )
    if not heading or "N2.2.1" not in heading:
        raise ValueError("Original form heading needs review.")
    rows = [[cell_text(cell) for cell in row.findall("w:tc", NS)] for row in physical]
    if tuple(rows[2]) != HEADERS or len(rows[1]) != 3 or len(rows[-1]) != 1:
        raise ValueError("DOCX columns do not match the reviewed layout.")
    if "თარიღი" not in rows[-1][0]:
        raise ValueError("Signature footer needs review.")
    data = rows[3:-1]
    if len(data) % 2:
        raise ValueError("Unpaired service rows.")
    beneficiaries = []
    for offset in range(0, len(data), 2):
        main, continuation = data[offset : offset + 2]
        number = offset // 2 + 1
        if len(main) != 11 or len(continuation) != 11:
            raise ValueError(f"Row {number}: layout needs manual review.")
        # The reviewed template has a stray literal p before the first row number.
        sequence = re.sub(r"^p\s*", "", main[0]) if number == 1 else main[0]
        if sequence.strip() != str(number) or any(
            continuation[index] for index in (0, 1, 2, 3, 4, 5, 10)
        ):
            raise ValueError(f"Row {number}: layout needs manual review.")
        services = []
        for line in (main, continuation):
            if not line[6] or not re.fullmatch(r"[0-9]+", line[7]) or not line[8]:
                raise ValueError(f"Row {number}: service evidence needs review.")
            services.append(
                dict(zip(("kind", "count", "location", "supervision"), line[6:10], strict=True))
            )
        beneficiaries.append(
            {
                "number": number,
                **dict(
                    zip(
                        ("voucher_number", "first_name", "last_name", "personal_id", "birth_date"),
                        main[1:6],
                        strict=True,
                    )
                ),
                "guardian": main[10],
                "services": services,
            }
        )
    return {
        "format": "early_intervention_docx_v1",
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "source_heading": heading,
        "rows": beneficiaries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx")
    parser.add_argument("output", help="Restricted JSON path outside the repository.")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    repository = Path(__file__).resolve().parent.parent
    if output.is_relative_to(repository):
        parser.error("Personal source data must be stored outside the repository.")
    try:
        document = extract(args.docx)
        with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "beneficiaries": len(document["rows"]),
                    "source_service_lines": sum(len(row["services"]) for row in document["rows"]),
                    "reported_service_count": sum(
                        int(service["count"])
                        for row in document["rows"]
                        for service in row["services"]
                    ),
                }
            )
        )
    except (OSError, ValueError, KeyError, BadZipFile, ET.ParseError):
        parser.error("Extraction failed. Check permissions and review the DOCX layout.")


if __name__ == "__main__":
    main()
