# Plan picker and category outlines on 2026-10-23

The owner's follow-up to the authorized plan release is live at
`https://0ufkrzj.cserverhost.cloud`.

- Application commit: `81cdaa9c921bceead079d8696e6e204cf877e9dd`.
- Running image: `ssk-web:plan-picker-20261023`, also tagged `ssk-web:latest`.
- Image ID: `sha256:957dea2562db7fe0622fa7d64758d13e4851d8fe6491917065a2b7ed2abdfac6`.
- Retained previous image: `ssk-web:before-plan-picker-20261023`.
- Previous application commit: `dc3480753470cac2e66e0d480f35bcce9ed30f18`.
- No migrations or runtime dependency changes.

Individual and early intervention plan beneficiary options now show the latest authorized
completed Barthel score available today, including zero. An intake-only value is explicitly
labeled as a recorded intake index. Missing values are omitted, and draft or future
assessments do not supply scores. The query stays scoped through the existing authorization
selectors and fetches scores with enrollment choices instead of querying each option.
The plan-date assessment preview and signed snapshots keep their existing date rules.

Care activities are grouped under one bold category label with a dark outline around each
category. The same grouping appears in review and newly generated printable or signed copies.
Existing signed documents remain unchanged.

Verification passed:

- Full local SQLite suite: 669 passed, ten PostgreSQL-only checks skipped.
- Actual candidate image: all 121 focused PostgreSQL tests passed, covering plans, Barthel,
  legacy plans, views, assignment authorization, permissions, and deployment checks.
- Local and candidate Ruff lint/format checks, Django system and deployment checks,
  migration drift and pending-migration checks, and Git whitespace checks.
- Synthetic browser checks in English and Georgian for scored beneficiary selection,
  live details, category outlines, and saving a grouped plan.
- Candidate and running-image verification: 266 bilingual plan/beneficiary/authorization
  checks and 760 enrollment options each.
- Public HTTPS verification: 294 plan/beneficiary/authorization/asset checks and 760 options,
  plus 161 assessment checks and 1,140 assessment options. Both desktop health checks passed.

Web writes were stopped for a restricted database/private-file backup and isolated restore.
The restored backup reconciled every original field of all 2,884 rows across 67 tables.
The same reconciliation passed against production before reopening writes. Only normal
audit events from authorized reads were added. No production casework or signature was
fabricated for verification, and temporary verification sessions were deleted.

All tracked runtime file hashes match the application commit. The running container is
healthy with zero restarts. Original private files, private configuration, Nginx configuration,
and TLS contents and modes were verified unchanged. Credentials, roles, SSH, sudo, and
firewall settings were unchanged.

Restricted recovery artifacts remain under
`/home/sskadmin/ssk-private-releases/plan-picker-20261023/`, with directory mode 700 and
file mode 600. The backup checksums and archive catalog passed. Temporary test/restore
databases, their container and volume, internal network, test image, source export, and
transferred bundle were removed. No production export was copied to the desktop.

GitHub main and `codex/plan-overhaul-20261023` received the update through an atomic
fast-forward push. The VPS received a code-only bundle. Recovery must preserve subsequent
casework and signed evidence; do not restore the pre-release database over later records.
