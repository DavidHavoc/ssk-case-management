"""Import reviewed DOCX people and evidence without inferring service delivery."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Beneficiary
from .workbook_import import WorkbookImportError, WorkbookPlan, WorkbookRow

FORMAT = "early_intervention_docx_v1"
ROW_KEYS = {
    "number",
    "voucher_number",
    "first_name",
    "last_name",
    "personal_id",
    "birth_date",
    "guardian",
    "services",
}
SERVICE_KEYS = {"kind", "count", "location", "supervision"}
DOCX_LABELS = {
    "reporting_period": _("DOCX reporting period"),
    "source_heading": _("Original DOCX heading"),
    "status_confirmation": _("Status confirmed for this import"),
    "voucher_number": _("Voucher number recorded in DOCX"),
    "guardian": _("Guardian information recorded in DOCX"),
    "services": _("Service information recorded in DOCX"),
    "personal_id": _("Personal ID recorded in DOCX"),
    "birth_date": _("Birth date recorded in DOCX"),
}
DOCX_ISSUES = {
    "start_date": _("Historical enrollment date was not supplied and remains unset."),
    "status": _("Current active status needs confirmation."),
    "guardian": _("Guardian information was not supplied."),
    "personal_id": _("Personal ID needs verification. The website field was left blank."),
    "birth_date": _("Birth date needs verification. The website field was left blank."),
    "age_review": _("Recorded birth date indicates an adult. Service eligibility needs review."),
    "service_type_review": _(
        "Repeated service types need review. Original service lines were preserved."
    ),
}


def read_docx_register(
    path, *, reporting_period, snapshot_date, confirmed_active=False, today=None
):
    today = today or timezone.localdate()
    if not isinstance(reporting_period, str) or not re.fullmatch(
        r"[0-9]{4}-(0[1-9]|1[0-2])", reporting_period
    ):
        raise WorkbookImportError("Reporting period must use YYYY-MM.")
    try:
        period_start = date.fromisoformat(reporting_period + "-01")
        if not isinstance(snapshot_date, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", snapshot_date
        ):
            raise ValueError
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
        raise WorkbookImportError("Cannot read the reviewed DOCX register.") from None
    if not isinstance(document, dict) or set(document) != {
        "format",
        "source_sha256",
        "source_heading",
        "rows",
    }:
        raise WorkbookImportError("Reviewed DOCX register structure is invalid.")
    digest = document["source_sha256"]
    if (
        document["format"] != FORMAT
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise WorkbookImportError("Reviewed DOCX register format or digest is invalid.")
    heading = document["source_heading"]
    if not isinstance(heading, str) or not heading.strip() or len(heading) > 4000:
        raise WorkbookImportError("Original DOCX heading is missing or too long.")
    rows = document["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise WorkbookImportError("Expected 1 to 5,000 reviewed DOCX rows.")
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
        if any(
            not isinstance(raw[key], str) or len(raw[key]) > 4000
            for key in ROW_KEYS - {"number", "services"}
        ):
            raise WorkbookImportError(f"Row {number}: source text is invalid.")
        services = raw["services"]
        if not isinstance(services, list) or not 1 <= len(services) <= 20:
            raise WorkbookImportError(f"Row {number}: source service information is invalid.")
        for service in services:
            if (
                not isinstance(service, dict)
                or set(service) != SERVICE_KEYS
                or any(
                    not isinstance(value, str) or len(value) > 4000 for value in service.values()
                )
            ):
                raise WorkbookImportError(f"Row {number}: source service information is invalid.")
        full_name = " ".join((raw["first_name"].strip(), raw["last_name"].strip()))
        if not raw["first_name"].strip() or not raw["last_name"].strip() or len(full_name) > 180:
            raise WorkbookImportError(f"Row {number}: beneficiary name needs review.")
        voucher = "".join(raw["voucher_number"].split())
        if len(voucher) > 80:
            raise WorkbookImportError(f"Row {number}: voucher number needs review.")
        source = {key: str(value) for key, value in raw.items() if key != "services"}
        source.update(
            {
                "services": json.dumps(services, ensure_ascii=False),
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
        kinds = [re.sub(r"[\W_]+", "", service["kind"].casefold()) for service in services]
        # These observed spellings describe the same individual-service category.
        kinds = ["ინდივიდ" if kind == "ინდვიდ" else kind for kind in kinds]
        supplied_kinds = [kind for kind in kinds if kind]
        if len(supplied_kinds) != len(set(supplied_kinds)):
            issues.append("service_type_review")
        if not confirmed_active:
            issues.append("status")
        personal_id = "".join(raw["personal_id"].split())
        if personal_id:
            if personal_id in identities:
                raise WorkbookImportError(f"Row {number}: duplicate personal ID in source.")
            identities.add(personal_id)
        if not re.fullmatch(r"[0-9]{11}", personal_id):
            personal_id = ""
            issues.append("personal_id")
        birth_text = raw["birth_date"].strip()
        try:
            if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}\.?", birth_text):
                raise ValueError
            birth = datetime.strptime(birth_text.removesuffix("."), "%d.%m.%Y").date()
        except ValueError:
            birth = None
        if birth is None or birth > today or birth > snapshot:
            birth = None
            issues.append("birth_date")
        elif (
            snapshot.year - birth.year - ((snapshot.month, snapshot.day) < (birth.month, birth.day))
            >= 18
        ):
            issues.append("age_review")
        guardian = " ".join(raw["guardian"].replace("\u00ad", "-").split())
        # A representative ID remains solely in restricted source evidence.
        guardian_name = re.sub(
            r"\s*(?:პ\s*[/.]?|/)\s*ნ[.\s:\-]*[0-9][0-9\s]*$", "", guardian
        ).strip(" -")
        trailing_identifier = re.search(r"[0-9][0-9\s]*$", guardian_name)
        if trailing_identifier and len("".join(trailing_identifier.group().split())) == 11:
            guardian_name = guardian_name[: trailing_identifier.start()].rstrip(" .:/-")
        if not any(character.isalpha() for character in guardian_name):
            guardian_name = ""
        if not guardian_name:
            issues.append("guardian")
        if len(guardian_name) > 180:
            raise WorkbookImportError(f"Row {number}: guardian name needs review.")
        person = {
            "full_name": full_name,
            "personal_id": personal_id,
            "birth_date": birth,
            "guardian_parent": guardian_name,
            "service_type": Beneficiary.ServiceType.OTHER,
            "service_status": "active" if confirmed_active else "applied",
            "enrollment_date": None,
            "application_contract_number": voucher,
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
    return WorkbookPlan(
        digest,
        result,
        service_codes=("EARLY-INTERVENTION",),
        snapshot_on=snapshot,
        require_existing_center=True,
    )


def docx_source_details(record):
    values = []
    for key, label in DOCX_LABELS.items():
        value = record.source_values.get(key, "")
        if key == "services" and value:
            value = "\n".join(
                " | ".join(service[field] for field in ("kind", "count", "location", "supervision"))
                for service in json.loads(value)
            )
        if value != "":
            values.append({"label": label, "value": value})
    return {
        "row": record.source_row,
        "values": values,
        "issues": [DOCX_ISSUES[key] for key in record.review_issues if key in DOCX_ISSUES],
    }
