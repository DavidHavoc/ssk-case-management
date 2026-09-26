from django.core.management.base import CommandError

from apps.casework.early_intervention_import import read_pdf_register
from apps.casework.management.commands.import_beneficiary_workbook import Command as WorkbookCommand


class Command(WorkbookCommand):
    help = "Import reviewed early-intervention PDF rows into an existing center."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--reporting-period", required=True, help="Confirmed YYYY-MM period.")
        parser.add_argument("--snapshot-date", required=True, help="Confirmed YYYY-MM-DD snapshot.")
        parser.add_argument(
            "--confirmed-active",
            action="store_true",
            help="The owner explicitly confirmed every listed person is currently active.",
        )

    def read_plan(self, options):
        if options["link_specialists"]:
            raise CommandError(
                "The PDF has no specialist identities. Supply assignments separately."
            )
        return read_pdf_register(
            options["workbook"],
            reporting_period=options["reporting_period"],
            snapshot_date=options["snapshot_date"],
            confirmed_active=options["confirmed_active"],
        )
