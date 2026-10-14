# Assessment schedule count removal, 2026-10-14

The owner requested removing “Service schedule count” after the Barthel release.
The field is excluded from assessment creation/edit forms, and its row is removed from
new review and printable documents. Existing stored values and signed evidence are preserved.
There are no database migrations or static-asset changes.

- Application commit: `1f8f925d32bbb1aeb8341cda45cb0803927fa38d`.
- Previous application commit: `82ba0c7c4c1ac7cf0b38aacf0eeb9eed6a4eaea5`.
- Running image: `ssk-web:schedule-removal-20261014`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:5bfbeccaa54073ed51e4dbc1e3ea97e97214cbff0cc509dcdee3331a9cacb8ed`.
- Retained previous image: `ssk-web:before-schedule-removal-20261014`.

Only the form and review-template files changed in the runtime image. Dependencies and static
assets were retained. The code-only bundle was delivered without a GitHub push, and both
deployed runtime files match their committed checksums. The web container is healthy with
zero restarts and the remote checkout is clean.

Local targeted verification passed 87 tests with one PostgreSQL-only skip. The candidate image
passed all 88 targeted synthetic PostgreSQL tests. Ruff lint/format, Django system/deployment
checks, and migration consistency checks passed. Candidate and running images passed 145
bilingual assessment checks and 1,140 enrollment-option checks, plus removal assertions in
both forms and review documents. All 161 public HTTPS checks passed, and both language health
endpoints returned HTTP 200 from the desktop.

Web writes were stopped for the restricted database/private-file backup and image switch.
The database backup restored successfully in isolation, and all 2,800 original rows across
66 tables were reconciled unchanged. Authorized reads generated normal audit events.
No production case record or signature was fabricated or edited for verification, and the
temporary verification session was deleted. Original private files, private configuration,
and TLS contents and modes were verified unchanged.

Recovery backups, archive catalog, checksums, and verification evidence remain under
`/home/sskadmin/ssk-private-releases/schedule-removal-20261014/` on the VPS, with directory
mode 700 and file mode 600. Checksums were reverified after cleanup. The temporary synthetic
and restore databases, container/volume, internal network, test image, source export, and bundle
were removed. No production export was copied to the desktop. Credentials, roles, sudo rules,
and infrastructure settings were not changed. Application-only rollback uses the retained image
and does not require restoring the database.
