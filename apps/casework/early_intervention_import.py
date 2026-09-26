"""Import reviewed PDF rows as people and source evidence, without inventing visits."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Beneficiary
from .workbook_import import WorkbookImportError, WorkbookPlan, WorkbookRow

FORMAT = "early_intervention_pdf_v1"
ROW_KEYS = {
    "number",
    "first_name",
    "last_name",
    "personal_id",
    "birth_date",
    "guardian",
    "individual_count",
    "group_count",
    "home_count",
    "center_count",
    "total_count",
    "delay_domains",
}
COUNT_KEYS = (
    "individual_count",
    "group_count",
    "home_count",
    "center_count",
    "total_count",
    "delay_domains",
)
PDF_LABELS = {
    "reporting_period": _("PDF reporting period"),
    "source_heading": _("Original PDF heading"),
    "status_confirmation": _("Status confirmed for this import"),
    "guardian": _("Guardian information recorded in PDF"),
    "individual_count": _("Individual services reported in PDF"),
    "group_count": _("Group services reported in PDF"),
    "home_count": _("Services at home reported in PDF"),
    "center_count": _("Services at center reported in PDF"),
    "total_count": _("Total services reported in PDF"),
    "delay_domains": _("Developmental delay areas recorded in PDF"),
    "personal_id": _("Personal ID recorded in PDF"),
    "birth_date": _("Birth date recorded in PDF"),
}
PDF_ISSUES = {
    "start_date": _("Historical enrollment date was not supplied and remains unset."),
    "status": _("Current active status needs confirmation."),
    "guardian": _("Guardian information was not supplied."),
    "personal_id": _("Personal ID needs verification. The website field was left blank."),
    "birth_date": _("Birth date needs verification. The website field was left blank."),
    "service_totals": _("Service type counts do not equal the reported total."),
    "location_totals": _("Location counts do not equal the reported service total."),
}


def read_pdf_register(path, *, reporting_period, snapshot_date, confirmed_active=False, today=None):
    today = today or timezone.localdate()
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", reporting_period):
        raise WorkbookImportError("Reporting period must use YYYY-MM.")
    try:
        period_start = date.fromisoformat(reporting_period + "-01")
        snapshot = date.fromisoformat(snapshot_date)
    except (ValueError, TypeError):
        raise WorkbookImportError("Snapshot date must use YYYY-MM-DD.") from None
    if snapshot > today or period_start > snapshot:
        raise WorkbookImportError("Reporting period and snapshot date cannot be in the future.")
    if Path(path).stat().st_size > 10 * 1024 * 1024:
        raise WorkbookImportError("Reviewed register exceeds the 10 MB limit.")
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise WorkbookImportError("Cannot read the reviewed PDF register.") from None
    if not isinstance(document, dict) or set(document) != {
        "format",
        "source_sha256",
        "source_heading",
        "reported_total",
        "rows",
    }:
        raise WorkbookImportError("Reviewed PDF register structure is invalid.")
    digest = document["source_sha256"]
    if (
        document["format"] != FORMAT
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise WorkbookImportError("Reviewed PDF register format or digest is invalid.")
    heading = document["source_heading"]
    if not isinstance(heading, str) or not heading or len(heading) > 4000:
        raise WorkbookImportError("Original PDF heading is missing or too long.")
    rows = document["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise WorkbookImportError("Expected 1 to 5,000 reviewed PDF rows.")
    identities = set()
    result = []
    for number, raw in enumerate(rows, start=1):
        if (
            not isinstance(raw, dict)
            or set(raw) != ROW_KEYS
            or type(raw["number"]) is not int
            or raw["number"] != number
        ):
            raise WorkbookImportError(f"Row {number}: structure or sequence is invalid.")
        if any(type(raw[key]) is not int or not 0 <= raw[key] <= 10000 for key in COUNT_KEYS):
            raise WorkbookImportError(f"Row {number}: source counts are invalid.")
        if any(
            not isinstance(raw[key], str) or len(raw[key]) > 4000
            for key in ROW_KEYS - set(COUNT_KEYS) - {"number"}
        ):
            raise WorkbookImportError(f"Row {number}: source text is invalid.")
        full_name = " ".join((raw["first_name"].strip(), raw["last_name"].strip()))
        if not raw["first_name"].strip() or not raw["last_name"].strip() or len(full_name) > 180:
            raise WorkbookImportError(f"Row {number}: beneficiary name needs review.")
        source = {key: str(value) for key, value in raw.items()}
        source.update(
            {
                "source_format": FORMAT,
                "source_heading": heading,
                "reporting_period": reporting_period,
                "status_confirmation": (
                    f"Active confirmed as of {snapshot.isoformat()}"
                    if confirmed_active
                    else f"Awaiting active-status review as of {snapshot.isoformat()}"
                ),
                "specialist": "",
                "exit_reason": "",
            }
        )
        issues = ["start_date"]
        if not confirmed_active:
            issues.append("status")
        personal_id = raw["personal_id"].strip()
        if personal_id:
            if personal_id in identities:
                raise WorkbookImportError(f"Row {number}: duplicate personal ID in source.")
            identities.add(personal_id)
        if not re.fullmatch(r"[0-9]{11}", personal_id):
            personal_id = ""
            issues.append("personal_id")
        try:
            birth = datetime.strptime(raw["birth_date"], "%d.%m.%Y").date()
        except ValueError:
            birth = None
        if birth is None or birth > today or birth > snapshot:
            birth = None
            issues.append("birth_date")
        guardian = " ".join(raw["guardian"].replace("\u00ad", "-").split())
        # Keep the representative's ID solely in restricted source evidence.
        guardian_name = re.sub(r"^[0-9]+\s*-?\s*", "", guardian).strip(" -")
        if not guardian_name:
            issues.append("guardian")
        if len(guardian_name) > 180:
            raise WorkbookImportError(f"Row {number}: guardian name needs review.")
        if raw["individual_count"] + raw["group_count"] != raw["total_count"]:
            issues.append("service_totals")
        if raw["home_count"] + raw["center_count"] != raw["total_count"]:
            issues.append("location_totals")
        person = {
            "full_name": full_name,
            "personal_id": personal_id,
            "birth_date": birth,
            "guardian_parent": guardian_name,
            "service_type": Beneficiary.ServiceType.OTHER,
            "service_status": "active" if confirmed_active else "applied",
            "enrollment_date": None,
            "application_contract_number": "",
        }
        result.append(
            WorkbookRow(
                number,
                source,
                person,
                ("EARLY-INTERVENTION",),
                None,
                None,
                "active" if confirmed_active else "pending",
                issues,
            )
        )
    reported = document["reported_total"]
    if type(reported) is not int or reported != sum(row["total_count"] for row in rows):
        raise WorkbookImportError("PDF footer total does not reconcile with the source rows.")
    return WorkbookPlan(
        digest,
        result,
        service_codes=("EARLY-INTERVENTION",),
        snapshot_on=snapshot,
        require_existing_center=True,
    )


def pdf_source_details(record):
    return {
        "row": record.source_row,
        "values": [
            {"label": label, "value": record.source_values.get(key, "")}
            for key, label in PDF_LABELS.items()
            if record.source_values.get(key, "") != ""
        ],
        "issues": [PDF_ISSUES[key] for key in record.review_issues if key in PDF_ISSUES],
    }
