# Integrated release handoff, 2026-10-09

The nine accepted company requirements are implemented and locally verified. No functional
requirement remains unresolved. The owner's October 9 decision is applied: legacy specialist
access ends at deployment. Unresolved imported teams retain their source evidence and review
flags, but require a confirmed lead/helper pair before specialist work resumes.

All preceding uncommitted work is preserved on `codex/center-beneficiary-codes`. This review
made scoped repairs only. Nothing was deployed, committed, pushed, or transferred to the VPS.
No SSH, production database/export, source workbook, credential, sudo rule, or firewall was used
or changed. All test people, accounts, signatures, databases, and downloaded evidence are synthetic.

## Verified behavior

| Requirement or risk | Evidence and resulting behavior |
|---|---|
| Guardian and emergency fields | Exact Georgian/English guardian label; optional emergency name/phone stay restricted. Specialists' forms, details, reports, and documents exclude these fields and consent evidence. |
| One operational code | Automatic person code is displayed across services. Legacy episode IDs remain unchanged, searchable, and read-only. Selectors and links use exact enrollment UUIDs. Migration fixtures preserve prior codes, aliases, counters, source values, histories, and relationships. PostgreSQL verifies serialized allocation. |
| Enrollment dates | Each service displays its own `start_date` as Enrollment date / ჩარიცხვის თარიღი. First service is separate. No historical date is fabricated. |
| One person-wide team | One lead and at most one distinct helper, with disjoint effective intervals. Both have assigned-specialist rights. Active account, staff status, membership, placement, event date, and current responsibility are checked server-side. PostgreSQL checks concurrent service/raw writes and shared person locking. |
| Imported ambiguity | Migration confirms only identical, unambiguous, eligible teams across every ongoing service. Joint, missing, conflicting, incomplete, future, or inactive assignments stay untouched and flagged. Frozen legacy snapshots expire on their capture date, exclusively, and grant no deployment-day access. |
| Full intake | Health, social, consent, and initial care sections precede documents. Lead/helper can edit health/social; manager/coordinator can edit consent. Checklist values are stable language-independent codes. No diagnoses, visits, catalog offerings, or formal active plans are created from intake selections. |
| Independent decisions | Three unanswered/yes/no choices plus independent unanswered/agree/decline media decision. Fresh forms default to unanswered. Refusal does not block casework or signing. Current answers are distinguishable from signed evidence. |
| Small signing flow | Handwritten canvas, clear/redraw, reviewed confirmation, printable keyboard alternative, signer role/relationship, private exact HTML snapshot and normalized PNG. CSRF, stale review rejection, idempotent retry, image limits, locked authorization, immutable evidence, and failed-file cleanup are covered. |
| Georgian and English | All 37 checkbox labels, single-choice options, conditional fields, supplied media declaration, guardian/date labels, validation, and empty states were checked against the original intake prompt and actual pages. Georgian signed artifacts embed their own font and full license. |

Actual browser walkthrough used a fresh temporary database with manager, coordinator, lead,
helper, and replacement specialist accounts. It created a person, added Food Delivery alongside
Home Care, edited health/social as both lead and helper, and scheduled a complete team replacement.
Today's pair stayed unchanged; the old period closes when tomorrow's replacement starts.

The browser saved a Georgian representative signature with `no`, `yes`, unanswered, and media
decline. It changed current decisions, verified the discrepancy notice, downloaded the original,
and saved a separate English beneficiary signature. The original Georgian HTML remained exactly
325,472 bytes with SHA-256
`b2229c0a2f0111b72045ab6966fbb7d40c2a1f1349099fd0d04b7cba79d085ca`.
The downloaded bytes equal the stored private file after the current decisions changed.

The Food Delivery enrollment transferred to another center using its exact UUID. Home Care then
exited prospectively and re-enrolled with a new UUID and a link to its prior episode. All three
episodes retained person code `TST-0001_B001`; no second operational code was generated. The
original lead could still access today's Home Care, while direct access to the transferred service,
future episode, and signed consent was denied. The coordinator could access all four intake sections.

Creation/intake forms, signing, and both language artifacts were checked at 320, 768, 1024,
and 1440 pixels. Page widths did not overflow. Georgian labels wrap visibly. Keyboard Tab,
checkbox Space, signature Clear with Enter, review confirmation, and mobile drawer Escape/focus
return were exercised. Embedded signature images decoded and displayed; the Georgian font loaded.
No browser JavaScript errors or warnings were recorded in these checks.

## Review repairs and files

- `apps/core/authorization.py`, `apps/casework/views.py`, `apps/casework/forms.py`, and
  `apps/audit/services.py`: malformed enrollment/session IDs now fail safely. Denial logging
  discards malformed UUID targets instead of causing another exception. Invalid legacy POST
  person IDs produce form errors. Existing person saves write only the actor's editable fields,
  preserving newer restricted contacts and other excluded values.
- `apps/core/forms.py` and `apps/casework/views.py`: enrollment workflows map model/service
  validation errors onto actual form fields or the nonfield summary. A duplicate service submission
  now renders a reviewable error and creates no partial episode.
- `apps/core/views.py`: malformed report object filters return 404 on pages and exports.
- `apps/casework/services.py`, `templates/casework/beneficiary_detail.html`, and Georgian PO/MO:
  enrollment/lifecycle errors and history states use the current language.
- Migration `0017` and `tests/test_staffing_migration.py`: deployment-day legacy expiry, source
  preservation, safe team backfill, access denial, guarded rollback, and replay.
- `tests/test_integrated_review.py`: 29 regressions for malformed IDs, duplicate-service atomicity,
  bilingual errors, and stale restricted-field preservation. Its language context is isolated so
  Georgian requests do not alter later English tests.
- Staffing/signing handoffs, permission/security/data/domain docs, frontend design system, and VPS
  runbook: current policy and implementation are aligned. The runbook's September 4 staging record
  is explicitly historical and superseded by the owner-confirmed records in `AGENTS.md`.

The complete combined release file list is in
[INTEGRATED_RELEASE_MANIFEST.txt](INTEGRATED_RELEASE_MANIFEST.txt), including preceding work.
No prior changed file was removed. Diff review found no unrelated implementation changes, real
beneficiary data, private keys/tokens, production exports, or newly added em dashes. A pattern scan
supports that review; it is not a general dependency or security audit.

Only the preceding signing feature adds a runtime dependency: `Pillow>=12.1,<13` for PNG decoding
and normalization. This review adds none. Installed verification used Pillow 12.3.0. The local
Noto Sans Georgian v2.005 font is 231,988 bytes, licensed under SIL Open Font License 1.1, with
original copyright/license and upstream metadata in `static/fonts/`. Its provenance and SHA-256
are documented in [static/fonts/README.md](../static/fonts/README.md), with
[Google Fonts source](https://github.com/google/fonts/tree/main/ofl/notosansgeorgian) and
[Pillow's licensing information](https://pillow.readthedocs.io/en/stable/about.html).
No signing SDK, PDF renderer, remote font, external signing service, or additional application
platform is introduced.

## Verification results

Environment: Python 3.12.14, Django 5.2.17, Pillow 12.3.0, psycopg 3.3.4, disposable PostgreSQL
16.15. The PostgreSQL container binds only localhost and stores its database on temporary memory
storage. It contains no production backup or export.

| Check | Final result |
|---|---|
| Complete local suite, `SSK_USE_SQLITE=1 .venv/bin/pytest -q --tb=short` | 584 passed, 9 skipped, 243.13 seconds |
| Complete disposable PostgreSQL suite, same pytest command with synthetic `DATABASE_URL` | 593 passed, no skips, 408.67 seconds |
| Ruff lint and format | Passed; 152 Python files already formatted under repository configuration |
| Django `check` | No issues |
| `makemigrations --check --dry-run` | No changes detected |
| Synthetic production `check --deploy --fail-level WARNING` | No issues |
| Production-settings `migrate --check` | No pending migrations on the isolated synthetic database |
| Production `collectstatic` | Passed, including hashed signing JS, CSS, and bundled font |
| Georgian catalog | `msgfmt --check --check-format` passed; fresh compilation equals checked-in MO |
| Migration graph/empty database rehearsal | Forward through 0022, reverse to 0013, and full replay passed on SQLite and PostgreSQL |
| Preservation/rollback/concurrency fixtures | Passed in the complete PostgreSQL suite |
| Diff checks | `git diff --check`, added-content typography, secret-pattern/export scans passed |

The nine SQLite skips concern center row locking, intake/staffing locking, staffing service/raw
writer concurrency and exclusion constraints, shared casework/staffing locking, PostgreSQL
history deletion guards, consent retry/intake concurrency, and summary advisory locking. They
are exercised on PostgreSQL; SQLite success alone is not concurrency evidence.

Actual finger/stylus hardware, formal screen-reader/axe audit, and native physical printing were
not exercised. The handwritten flow is assisted recording, with stated signer identity/relationship;
it does not verify legal authority. The deliverable is immutable HTML, not a generated PDF.
The browser/A4 document layout was inspected. Device/printer review remains a release smoke check.
No live VPS, provider controls, backup system, TLS renewal, or production database was reverified.
The preview server/database/private files, disposable PostgreSQL container/databases, and the
matching temporary Downloads file were removed. Synthetic screenshot/HTML proof and final test
logs remain in this chat's visualization directory, outside Git.

## Migration and rollback approach

The casework graph has one release leaf, `0022_signed_consent_guards`, with this order after
the deployed foundation `0013`:

| Migration | Purpose |
|---|---|
| 0014 | Optional restricted emergency contacts |
| 0015 | Nullable read-only legacy episode IDs and explicit enrollment date label |
| 0016 | Person staffing periods and frozen snapshot schema |
| 0017 | Conservative team backfill; evidence snapshots expire on capture date |
| 0018 | Staffing intervals, immutable history, eligibility and frozen-grant database guards |
| 0019 | Optional intake and restricted before/after revisions; no inferred historical intake |
| 0020 | Additive signed-consent snapshots and private attachment type |
| 0021 | Unique signed evidence filenames per signed record |
| 0022 | Immutable signed snapshot/attachment database guards |

PostgreSQL requires permission to install `btree_gist`, which succeeded in the disposable
rehearsal. Existing base schema/data migrations are unchanged. New migration fixtures compare
all original rows, including automatic relationship tables and restricted source evidence.
Emergency/intake/signing additions do not rewrite existing data or invent consent.

Before new application writes, full reversal to 0013 and replay succeeded in isolated databases.
After writes, rollback needs the following decisions, not an automatic `migrate 0013`:

- 0015 refuses reversal if any enrollment has no legacy ID. Do not invent identifiers for rollback.
- 0018/0017 refuse removal after staffing confirmation or changes. The database guard remains
  installed when reversal is refused; preserve team and source history.
- 0022 refuses reversal when signed consent exists. Preserve snapshots, original HTML, and PNG
  files together. Do not remove guards to force rollback.
- Reversing 0019 would discard newly recorded intake/revisions. Do not reverse it after such writes.
- Prefer a forward repair with the current schema. An old image may assume required episode IDs,
  enrollment-level teams, or lack signed-evidence protections; retaining schema does not alone
  establish old-image compatibility. Verify any code-only rollback first in an isolated restore.
- A full pre-release restore is only for a separately approved recovery decision, with writes
  stopped and an explicit plan for preserving or reconciling every post-backup record and file.

## Future production checklist, not executed

Follow [VPS runbook sections 10, 13, and 18](VPS_OPERATIONS_RUNBOOK.md) and
[backup/restore guidance](BACKUP_AND_RESTORE.md). The checklist requires a separate deployment
request; this local review is not that authorization.

1. Record the reviewed committed revision, current live revision/image digest, deployed migration
   state, maintenance owner, rollback owner, and expected interruption. Confirm 0014 through 0022
   are unapplied. If 0017 was already applied elsewhere, stop and review a corrective migration;
   do not silently rely on changing an already applied migration to revoke access.
2. Explain deployment-day legacy expiry to managers/coordinators. Prepare a restricted unresolved
   staffing review list on the destination. Preserve joint source roles and unknown dates; confirm
   one explicit lead and optional helper for ongoing cases. No choice may be inferred from name
   order. Do not extend/regenerate frozen grants or alter staff memberships to avoid review.
3. Take restricted database and private-file backups, including existing imported evidence and
   any signed artifacts. Record checksums and restore both into an isolated destination container.
   Verify restoration, original file readability, counts/relationships, and a recoverable old image.
   Keep backups and any reconciliation exports on the destination, outside Git and developer databases.
4. Deliver only reviewed code through the existing code-only Git bundle approach or the owner's
   approved code delivery process. Include all new migrations, translations, font/license/metadata,
   templates, signing script, and Pillow. Preserve `.env.production`, backups, and private-media
   permissions. Make only reviewed code files readable if needed. No credential, account, SSH,
   firewall, or sudo-rule changes are part of this release.
5. Build the candidate image with the required runtime dependencies and collect static assets.
   Run candidate `check --deploy --fail-level WARNING`, `makemigrations --check --dry-run`, and
   `showmigrations --plan`. Confirm `btree_gist` availability and the expected migration order.
   Use existing authorized deployment access; do not recreate a passwordless sudo rule.
6. Stop web writes, take the final restricted consistent database/private-file backup, and capture
   destination-only reconciliation snapshots. Apply `migrate --noinput` in the candidate image,
   then `migrate --check` and deployment checks. Do not run `seed_demo_data` or supplied imports.
7. Reconcile every original row and relationship against the stopped-write snapshot, excluding
   only expected system additions and deliberate new staffing periods/snapshots. Verify existing
   beneficiary codes, aliases, counters, episode IDs, dates, source evidence, histories, and center
   memberships unchanged. Verify ambiguous teams flagged, all legacy grants expired, safe teams
   consistent across services, and no fabricated intake, consent, visits, or formal plans.
8. Restart the reviewed application image; verify private-file readability and public HTTPS health
   using the configured hostname. Smoke-test both languages, manager/coordinator and confirmed
   specialist scope, exact episode links, malformed/cross-center denial, reports/reminders, and
   private original consent download. Check logs without exporting sensitive content. Use only
   owner-approved smoke records; never create a real person's signature as a deployment test.
9. Keep the backup and previous image until owner acceptance. Record reconciliation/check results
   and the deployed revision. Remove temporary code bundles, restore/test containers, sessions,
   and destination reconciliation exports according to the restricted retention process. Complete
   intended-device Georgian typography, finger/stylus, and printer review without changing signed
   evidence. Keep unresolved staffing review work visible to managers.
