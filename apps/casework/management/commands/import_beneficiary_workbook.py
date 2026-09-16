import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.casework.workbook_import import (
    WorkbookImportError,
    apply_workbook,
    read_workbook,
    validate_destination,
)


class Command(BaseCommand):
    help = "Validate or import a Georgian beneficiary register, reporting no personal values."

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--center-code")
        parser.add_argument("--center-name")
        parser.add_argument(
            "--actor", help="Username of the active System Manager responsible for this import."
        )
        parser.add_argument(
            "--inspect",
            action="store_true",
            help="Inspect the source without querying or writing the database.",
        )
        parser.add_argument(
            "--apply", action="store_true", help="Commit one atomic import after validation."
        )
        parser.add_argument(
            "--allow-incomplete",
            action="store_true",
            help="Preserve unclear values for restricted review, leaving operational fields unset.",
        )
        parser.add_argument(
            "--link-specialists",
            action="store_true",
            help="Link only unique active staff names already assigned to this center.",
        )

    def handle(self, *args, **options):
        if options["inspect"] and options["apply"]:
            raise CommandError("--inspect cannot be combined with --apply.")
        try:
            plan = read_workbook(options["workbook"])
            if options["inspect"]:
                self.stdout.write(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
                return
            if not all(options[key] for key in ("actor", "center_code", "center_name")):
                raise CommandError(
                    "Supply --actor, --center-code, and --center-name, or use --inspect."
                )
            actor = get_user_model().objects.filter(username=options["actor"]).first()
            destination = {
                "actor": actor,
                "center_code": options["center_code"].strip().upper(),
                "center_name": options["center_name"].strip(),
                "link_specialists": options["link_specialists"],
            }
            _, _, _, matches, existing = validate_destination(plan, **destination)
            report = plan.summary()
            report["already_imported"] = len(existing)
            report["matched_specialist_rows"] = sum(value is not None for value in matches.values())
            report["mode"] = "apply" if options["apply"] else "preview"
            if options["apply"]:
                report["result"] = apply_workbook(
                    plan, **destination, allow_incomplete=options["allow_incomplete"]
                )
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        except (WorkbookImportError, PermissionDenied) as exc:
            raise CommandError(str(exc)) from None
        except OSError:
            raise CommandError(
                "Workbook could not be read. Check file access permissions."
            ) from None
        except IntegrityError:
            raise CommandError(
                "Database conflict. All changes rolled back; review duplicates before retrying."
            ) from None
