# Beneficiary workbook import

The `import_beneficiary_workbook` management command accepts the Georgian beneficiary
register with the 17 named columns defined in `apps/casework/workbook_import.py`.
It is a server-side operator command requiring an active System Manager actor.
Do not put source workbooks, personal values, or database backups in the repository.

## Mapping

- Each source row creates one person. Home care and food delivery create separate
  enrollment episodes for that same person.
- The operator explicitly supplies the center code and name. An absent center is created
  with only the requested service offerings. Existing conflicting center configurations
  require manual review.
- Existing service and offering start dates may be extended earlier to accommodate
  the register's actual historical start dates. These changes are audited.
- Dates stored as Excel dates and US-style slash dates are read as dates. Age is derived
  from the valid birth date. The original reported age is retained separately.
- Personal IDs stay text. Unexpected lengths are flagged without padding or truncation.
- Future birth dates, malformed phone numbers, application numbers stored as Excel dates,
  missing enrollment dates, and missing or inconsistent exit dates remain unset in their
  operational fields. Original values are retained for restricted review.
- An exit date or exit reason establishes an exited snapshot. An unknown exit date is
  never replaced by the import date. Such an enrollment cannot authorize service delivery.
- Source status, household descriptions, Barthel categories, specialist names, and notes
  are preserved as source evidence. They do not manufacture coded diagnoses, marital
  status, exact Barthel scores, assessments, schedules, or delivered visits.
- `--link-specialists` matches normalized full names only against unique active staff
  already assigned to the selected center. No accounts or center memberships are created.
  Comma-separated names are matched individually and linked as jointly responsible
  specialists. Cell order does not establish a lead. Duplicate names create one link.
  Current assignments begin on the import date or future enrollment start, whichever is
  later. Closed or undated episodes retain a link with unknown historical assignment dates
  and grant no current specialist access. Missing or ambiguous matches are flagged.

## Preview

Read-only source inspection does not query or write the database:

```sh
python manage.py import_beneficiary_workbook /restricted/register.xlsx --inspect
```

Preview against the destination without changing it:

```sh
python manage.py import_beneficiary_workbook /restricted/register.xlsx \
  --center-code APPROVED-CENTER --center-name 'Approved center name' \
  --actor approved-manager --link-specialists
```

Output contains counts, row numbers, and field keys, without personal values. The file
must have one worksheet. Unknown services, duplicate source IDs, formulas, error cells,
and populated undated visit columns stop the import for review.

## Apply and reconcile

Complete the applicable hosting readiness requirements and take a restricted database
backup before applying migrations or importing real records. Transfer the source only
through the approved encrypted channel to a restricted temporary directory on the target.
Do not import real records into a developer or test database.

Add `--apply` to the preview command to commit the entire import in one database
transaction. Add `--allow-incomplete` only when the owner has approved importing all rows
with original uncertain values preserved for review. Any validation or database conflict
rolls back the whole import, including center, catalog, and audit changes.

The source SHA-256 and row number identify completed imports. Repeating the same file
skips completed rows and never overwrites later edits. A different workbook containing
existing personal IDs requires manual reconciliation. This command is not a recurring
sync or an update mechanism.

Reconcile people, service episodes, lifecycle statuses, staff assignment matches, and
flagged rows against the preview. Verify the Georgian detail page as a manager or
coordinator, then verify an assigned specialist cannot see the source evidence. Original
values and flags describe the import snapshot and remain preserved after operational
fields are corrected. Remove the transferred temporary workbook after verification.

The source record is available only through the existing authorized beneficiary detail
view to managers and authorized coordinators. It is excluded from ordinary case exports,
specialist page context, and audit metadata. Audit events retain actor and target IDs only.
