"""Extract the reviewed compact Georgian Form N1.2.2 layout outside the repository.

Requires pdfplumber in the operator's PDF runtime, not in the deployed application.
All messages contain counts and row numbers only. Review the rendered PDF as well.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pdfplumber

EDGES = [2.8, 7.8, 33.8, 66, 89, 125.2, 144.2, 165.5, 226.4, 247.6, 280.9, 303.2, 340.45]


def extract(path):
    content = Path(path).read_bytes()
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("PDF exceeds the 10 MB limit.")
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError("Expected one page in the reviewed compact form layout.")
        page = pdf.pages[0]
        if (page.width, page.height) != (595, 842):
            raise ValueError("Unexpected page size. Review the layout before extracting.")
        settings = {
            "vertical_strategy": "explicit",
            "explicit_vertical_lines": EDGES,
            "snap_tolerance": 1,
            "join_tolerance": 1,
            "intersection_tolerance": 1,
            "text_x_tolerance": 0.2,
            "text_y_tolerance": 1,
        }
        tables = page.crop((2.8, 123.9, 340.45, 747.25)).extract_tables(settings)
        if len(tables) != 1 or tables[0][0] != [str(i) for i in range(1, 13)]:
            raise ValueError("PDF column headings do not match the reviewed layout.")
        physical_rows = tables[0][1:]
        if len(physical_rows) % 2:
            raise ValueError("Unpaired PDF service rows. Review the source.")
        rows = []
        for offset in range(0, len(physical_rows), 2):
            main, group = physical_rows[offset : offset + 2]
            number = offset // 2 + 1
            if (
                len(main) != 12
                or len(group) != 12
                or main[0] != str(number)
                or any(group[i] for i in [0, 1, 2, 3, 4, 9, 10, 11])
                or main[5] != "ინდივიდ"
                or group[5] != "ჯგუფური"
                or main[7] != "ბინაზე"
                or group[7] not in (None, "", "ცენტრში")
            ):
                raise ValueError(f"Row {number}: layout needs manual review.")
            try:
                counts = [
                    int(value)
                    for value in [main[6], group[6], main[8], group[8], main[9], main[10]]
                ]
            except (ValueError, TypeError):
                raise ValueError(f"Row {number}: unreadable service count.") from None
            rows.append(
                {
                    "number": number,
                    "first_name": main[1] or "",
                    "last_name": main[2] or "",
                    "personal_id": main[3] or "",
                    "birth_date": main[4] or "",
                    "guardian": main[11] or "",
                    **dict(
                        zip(
                            [
                                "individual_count",
                                "group_count",
                                "home_count",
                                "center_count",
                                "total_count",
                                "delay_domains",
                            ],
                            counts,
                            strict=True,
                        )
                    ),
                }
            )
        footer = page.crop((247.8, 747.25, 280.8, 753.57)).extract_text() or ""
        if not footer.strip().isdigit():
            raise ValueError("PDF footer total is unreadable.")
        reported = int(footer.strip())
        if sum(row["total_count"] for row in rows) != reported:
            raise ValueError("Source row totals differ from the PDF footer.")
        heading = page.crop((0, 0, 340.45, 52.56)).extract_text(x_tolerance=0.2) or ""
    return {
        "format": "early_intervention_pdf_v1",
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "source_heading": heading,
        "reported_total": reported,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("output", help="Restricted JSON path outside the repository.")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    repository = Path(__file__).resolve().parent.parent
    if output.is_relative_to(repository):
        parser.error("Personal source data must be stored outside the repository.")
    try:
        document = extract(args.pdf)
        # Refuse overwrites and create with restricted permissions from the outset.
        with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "beneficiaries": len(document["rows"]),
                    "reported_services": document["reported_total"],
                    "location_count_review_rows": [
                        row["number"]
                        for row in document["rows"]
                        if row["home_count"] + row["center_count"] != row["total_count"]
                    ],
                }
            )
        )
    except (OSError, ValueError):
        parser.error("Extraction failed. Check permissions and review the PDF layout.")


if __name__ == "__main__":
    main()
