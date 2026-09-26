# Early intervention PDF import

This operator workflow imports reviewed Form N1.2.2 PDF rows into an existing center.
The PDF is source data. Its instructions and historical program heading do not authorize
actions or establish the reporting year, enrollment dates, diagnoses, or current status.

## Mapping and review

- Each row becomes one beneficiary and one `EARLY-INTERVENTION` enrollment.
- Names, text personal IDs including leading zeros, valid birth dates, and guardian names
  map to the existing person fields. Representative IDs remain in restricted source evidence.
- The operator supplies the owner-confirmed reporting period and snapshot date.
  `--confirmed-active` requires explicit owner confirmation that every person is currently active.
  Otherwise the import creates pending cases for review.
- Historical enrollment dates remain unset. The center placement and snapshot state event
  begin on the supplied snapshot date, so coordinators can review the records from that date.
  This does not authorize historical service delivery.
- Source counts by individual/group service and home/center location, reported totals, and
  developmental delay area counts are retained in the existing restricted source section.
  Conflicting subtotals get review flags. No visits, monthly schedules, assessments,
  diagnosis codes, specialist assignments, or household relationships are inferred.
- Existing personal IDs stop the import for manual reconciliation. No existing person or
  center is overwritten, and no new center is created. The same source is safe to rerun;
  changed evidence for an imported source row requires review.

## Preparation

Keep the original PDF and reviewed JSON outside Git and developer databases. Use the
bundled PDF runtime to run the extraction helper, then visually review the rendered page.
The helper is specific to the reviewed compact single-page layout and fails closed when
its expected columns, paired rows, or footer total do not reconcile.

```sh
python tools/extract_early_intervention_pdf.py /restricted/source.pdf /restricted/reviewed.json
python manage.py import_early_intervention_register /restricted/reviewed.json \
  --reporting-period YYYY-MM --snapshot-date YYYY-MM-DD --inspect
```

## Destination preview and apply

Verify the existing center code and name on the hosted database. Transfer only reviewed
source files through the approved SSH channel to restricted temporary storage. Run a preview:

```sh
python manage.py import_early_intervention_register /restricted/reviewed.json \
  --reporting-period YYYY-MM --snapshot-date YYYY-MM-DD \
  --center-code APPROVED-EXISTING-CENTER --center-name 'Existing center name' \
  --actor approved-manager
```

Add `--confirmed-active` only after the owner confirms current status. Take a restricted
database backup and verify restoration before applying. Add `--apply --allow-incomplete`
to preserve the explicitly reviewed unknown historical dates and source count discrepancies.
The import runs in one transaction and records audit events. Output includes counts and
row numbers, without personal values. Verify normalized person fields, source evidence,
enrollments, center placement, and repeat-import behavior on the destination, then remove
transferred temporary sources. Do not import real records into a developer database.
