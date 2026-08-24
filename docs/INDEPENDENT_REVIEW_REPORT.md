# Independent Django and Security Review

Review date: 2026-08-14
Application: `ssk-case-management`
Legacy comparison source: `ASB-center`
Data used: synthetic demo and test records only

## Recommendation

**Ready for stakeholder demo.**

This recommendation is limited to a synthetic-data stakeholder demonstration. It is not a production-readiness statement. The company decisions, infrastructure integrations, and human UAT items later in this report remain required before any production use or real beneficiary migration.

No open Critical or High finding remained at the end of this review.

## Review scope and independence

The standalone implementation and the inspected legacy working tree were reviewed directly. No previous implementation summary was used as evidence.

Standalone sources inspected included all application modules, models, forms, selectors, middleware, views, templates, migrations, tests, settings, Docker files, static assets, translations, and project documents.

Legacy evidence inspected read-only included:

- `AGENTS.md`, `README.md`, privacy, roster, UAT, demo, and section documentation;
- `permissions.py`, `privacy.py`, and `roster.py`;
- Beneficiary, Service Visit, Assessment, Assessment Domain Score, Individual Plan, Individual Plan Goal, Center, Specialist Profile, and specialist-assignment DocType Python and JSON definitions;
- the legacy permission and roster tests.

The legacy repository was not modified. Its existing dirty working tree contained 30 entries when rechecked. The standalone repository still had no `HEAD` revision at handoff, so no commit was created.

## Prioritized findings

### Critical

No Critical defect was confirmed.

### High

| ID | Finding | Evidence | Resolution | Regression evidence |
|---|---|---|---|---|
| H-01 | Every valid private attachment upload failed with HTTP 500. | Manual browser upload produced `ValueError: 'PrivateAttachmentForm' has no field named 'parent_id'`. Model validation ran before the view populated parent, center, and uploader. | The upload view now binds the complete unsaved attachment instance before form validation. Canonical content type is set by validated extension. Storage cleanup remains transactional on later failure. | `test_attachment_upload_sets_parent_before_validation_and_audits`; `test_failed_attachment_audit_rolls_back_row_and_stored_file`; successful browser upload, authorized display, specialist direct-download 404, and authorized deletion. |
| H-02 | The production image returned HTTP 500 on login because the static manifest did not contain `css/app.css`. | An isolated `DEBUG=0` image request failed with `Missing staticfiles manifest entry for 'css/app.css'`. The image had collected static files under `DEBUG=1`. | The Docker build now runs `collectstatic` under fail-closed production-like settings. | Rebuilt production image returned login HTTP 200 with `/static/css/app.6252f9914a1f.css`; `check --deploy` passed. |
| H-03 | Production settings could start with unsafe development defaults. | Code inspection confirmed that a disabled-debug process could otherwise inherit a default secret or SQLite. | Startup requires an explicit long secret, explicit non-wildcard hosts, and PostgreSQL credentials. Email delivery requirements were later removed with the email-reset workflow. | `test_production_settings_fail_closed_for_missing_or_unsafe_values`; production container `check --deploy` reported no issues. |
| H-04 | Inactive coordinators and specialists retained authorization while their Django user remained active. | `accessible_centers()` and `specialist_profile_for_user()` did not test `StaffProfile.status`. | All non-manager center, case, summary, and specialist-choice selectors now require an active staff profile. | `test_inactive_staff_profile_revokes_center_and_case_access`. |
| H-05 | Monthly summary rebuilds had a lost-update race. | The prior signal-driven read-and-replace aggregation had no serialization for simultaneous visits in the same specialist, center, and month. | Rebuilds now use a deterministic PostgreSQL transaction advisory lock. Current and previous scopes are ordered consistently, and visit write plus summary rebuild is atomic. | `test_concurrent_visit_creation_keeps_monthly_summary_complete`; `test_visit_and_summary_write_roll_back_together`. |
| H-06 | Default proxy and application access logs could retain query strings containing report searches or filters. | The previous Nginx request log and default Gunicorn request-line format included the query component. | Nginx and Gunicorn now log method and path only. | `test_access_log_formats_omit_query_strings`; a live request containing `SYNTHETIC-SHOULD-NOT-LOG` produced path-only Nginx and Gunicorn entries. |
| H-07 | Secret and key files were not comprehensively excluded from Git and Docker build context. | `.env.production` and local TLS material were not covered by the initial patterns. | `.env*`, TLS material, backups, dumps, databases, logs, generated static, private files, caches, and virtual environments are excluded as applicable. `.env.example` remains trackable. | `test_secret_and_generated_file_patterns_are_ignored`; host `git check-ignore -v` confirmed `.env`, `.env.production`, both TLS files, private media, SQLite, caches, and virtual environments are ignored. |

### Medium

| ID | Finding | Resolution and evidence |
|---|---|---|
| M-01 | Legacy System Manager deletion behavior was missing. | Added active-center-scoped, manager-only deletion for centers and case records, protected-reference handling, attachment cleanup, audit events, and manager-only UI controls. Coordinator and specialist attempts are denied. Covered by delete authorization and cross-center tests plus a browser create/delete visit exercise. |
| M-02 | The original email password-reset workflow created address ambiguity and mailbox-flood concerns. | The email reset route was later replaced by administrator-issued temporary access codes, mandatory first-login password changes, and server-authorized employee-record resets. User email remains unique case-insensitively. |
| M-03 | Several workflow invariants existed only in Python validation. | Added database constraints for cancelled visit units, first-of-month fields, assessment sequence consistency, review dates, plan dates, and summary months. Migration and constraint tests pass on PostgreSQL. |
| M-04 | File cleanup and audit failure could diverge from the attachment row. | Upload and audit creation are atomic, a stored file is removed if the transaction later fails, and deletion removes storage only on transaction commit. Covered by rollback and on-commit deletion tests. |
| M-05 | User-supplied Windows-style filenames and MIME headers were not handled canonically. | Both slash styles are reduced to a basename, the stored path remains randomized, and content type is derived from the validated extension rather than the request header. Covered by private-file validation and successful upload tests. |
| M-06 | Georgian application strings were materially incomplete. | All extracted MVP strings now have non-fuzzy Georgian entries and a compiled catalog. Automated catalog checks pass and browser review showed translated navigation, filters, statuses, and forms. Native-speaker UAT remains open. |
| M-07 | The sample production proxy did not implement the documented TLS boundary, and its health probe conflicted with secure redirect and host checks. | Added explicit HTTP-to-HTTPS redirect, TLS 1.2/1.3 configuration, secure forwarded-protocol handling, a host-aware health probe, and ignored certificate mounts. The isolated production stack became healthy and served HTTPS health and login pages. |

### Low

| ID | Finding | Resolution and evidence |
|---|---|---|
| L-01 | Phone and long-text normalization differed from legacy validation. | Added shared phone validation and trimming for beneficiary, center, visit, assessment, domain, plan, and goal text. Validation tests pass. |
| L-02 | Backup, release, proxy, logging, and secret instructions did not fully match the runnable configuration. | Updated the production, security, architecture, parity, permission, local setup, and backup guidance. The documented database and file restore flow was rehearsed with synthetic data. |
| L-03 | An N+1 regression risk existed on case lists. | Authorization selectors use `select_related` and `prefetch_related`; the visit list query-count test confirms row growth does not cause per-row query growth. Broader load testing remains a pre-production activity. |

## Legacy behavior comparison

The resulting permission boundary matches the inspected legacy behavior in the main MVP areas:

- System Manager has all-center access and is the only case-record delete role.
- Coordinator manages assigned centers, beneficiaries, workflows, reports, CSV, restricted beneficiary values, and roster membership.
- Specialist sees assigned beneficiaries and case records where the specialist is either the record specialist or an assigned beneficiary specialist.
- Specialist never receives personal ID, address, guardian, phone, email, contract number, beneficiary assignments, or beneficiary attachments.
- Specialist may access a visit, assessment, or plan attachment only through an authorized parent record.
- Cancelled visits normalize service units to zero.
- Repeated and final assessments require an earlier assessment for the same beneficiary and sequence after it.
- Assessments require domain rows. Active or completed plans require goals.
- Monthly summaries aggregate per specialist, center, and month.

Intentional security tightening: an inactive standalone `StaffProfile` now revokes non-manager access. The legacy Employee fallback was less explicit.

Two legacy semantics remain business decisions rather than silent changes:

- beneficiary assignment date ranges do not currently alter authorization;
- diagnosis and case notes remain visible to an assigned specialist, matching the inspected legacy restricted-field boundary.

## Verification evidence

### Docker and PostgreSQL

- Docker Desktop was started and both development and isolated production Compose projects were built.
- Development ran against `postgres:16-alpine`, not SQLite.
- All migrations, including the new constraints and unique email migration, applied successfully.
- `seed_demo_data` created six synthetic users across all three roles, two centers, three beneficiaries, multi-center specialist membership, visits, assessments, plans, and summaries.
- The development health endpoint returned HTTP 200 and `{"status": "ok"}`.
- The isolated production database and web health checks reached healthy state.
- HTTPS `/en/health/` and `/en/accounts/login/` returned 200. HTTP health redirected 301 to HTTPS.
- Production responses included CSP, HSTS, secure cookies, clickjacking protection, content-type protection, referrer policy, permissions policy, and cross-origin policies.

### Automated checks

- The final full `pytest` run used PostgreSQL and passed 53 tests.
- Ruff lint and format verification passed.
- `manage.py check` passed.
- Production-container `manage.py check --deploy` passed with zero issues.
- `manage.py makemigrations --check --dry-run` reported no changes.
- `msgfmt --check --check-format` passed; the Georgian catalog had zero fuzzy and zero untranslated extracted application messages.
- The PostgreSQL-only concurrency test passed and worker connections were closed cleanly.

### Manual role and authorization exercise

- System Manager selected Alpha and Beta centers, saw center-specific dashboard counts, opened restricted fields, reports, CSV controls, and manager deletion controls.
- Alpha Coordinator saw only the Alpha roster and Alpha beneficiary records, including restricted values and attachment controls.
- Alpha Specialist saw only the assigned Alpha beneficiary. Personal ID, address, email, specialist assignment details, and beneficiary attachments were absent.
- Multi-center Specialist was required to select a center. Beta showed no case records for that user; switching to Alpha showed the assigned record.
- A same-center unassigned beneficiary URL returned 404 for the specialist.
- A cross-center beneficiary URL returned 404 for the specialist.
- Direct beneficiary attachment upload returned 404 for the specialist.
- Direct beneficiary attachment download returned 404 for the specialist after a real synthetic attachment was uploaded by a manager.
- Specialist CSV export returned 403. The specialist HTML visit report contained only the authorized record and no export control.
- A manager created a synthetic service visit through the browser, opened its detail page, then deleted it through the confirmation UI. The record disappeared and the success message was shown.
- A manager uploaded a synthetic text file through the browser, saw it on the parent page, and deleted it through the authorized form. No real or beneficiary data was used.

### File, export, and audit controls

- Private storage exposes no `.url` and is not mounted in Nginx.
- Stored names are randomized and constrained under the resolved private root.
- PDF, PNG, JPEG, UTF-8 text, DOCX, extension, size, forged-content, basename, and canonical MIME behaviors have automated coverage.
- Report exports authorize the base QuerySet before filtering, exclude restricted beneficiary fields, and prefix spreadsheet formula leaders.
- Sensitive audit metadata is allowlisted. Tests cover successful and denied downloads, reads, writes, deletion, export, and authentication outcomes without record values.
- Application and proxy live logs were inspected after a query-bearing request; the query marker was absent.

### Backup and restore rehearsal

- A custom-format logical dump of the synthetic development database was restored to a new isolated database.
- Source and restore counts matched: 23 migrations, 6 users, 2 centers, and 3 beneficiaries.
- The restored authorization graph contained 6 role memberships, 6 staff-center memberships, 4 specialist-center assignments, and 3 beneficiary-specialist assignments.
- The restored audit table contained 7 events at backup time.
- A private-file archive was extracted to an isolated directory. Source and restored files had the same SHA-256 value: `93e26ebe171ed6153d8b803b9e73cbd66866c01958d00731117d58cfae640894`.
- The isolated restore database, dump, extracted directory, archive, and synthetic application attachment were removed after verification.

### Git and artifact hygiene

- `git rev-parse --verify HEAD` confirmed that the standalone repository has no commit. No commit was created.
- `.env`, `.env.production`, local TLS keys and certificates, private media, SQLite files, caches, virtual environments, package metadata, logs, dumps, and generated static output are ignored.
- `.env.example` contains development placeholders only and remains trackable.
- The Docker build context excludes secret and generated paths.
- No production export, real beneficiary record, or production credential was created or imported.

### Usability, translation, and accessibility

- Desktop and a 390 by 844 mobile viewport were inspected in the browser.
- Forms collapse to one column at mobile width; navigation and wide tables remain operable with horizontal scrolling.
- A skip link, semantic navigation, labels, headings, tables, focus styles, and accessible names are present.
- English and Georgian language switching worked and persisted through localized routes.
- Automated inspection cannot replace keyboard-only, screen-reader, native-speaker, or physical-device UAT.

## New or expanded regression coverage

Security or permission fixes have direct tests for:

- inactive staff revocation;
- manager-only and active-center-scoped deletion;
- attachment upload validation order;
- attachment parent authorization, direct download denial, deletion, and rollback cleanup;
- specialist export denial and CSV formula neutralization;
- temporary access-code issuance, mandatory password change, and administrator reset authorization;
- production fail-closed environment validation;
- query-free access-log formats;
- secret and artifact ignore patterns;
- PostgreSQL monthly-summary concurrency and transaction rollback;
- database workflow constraints;
- Georgian catalog completeness;
- list query-count stability.

## Human UAT and company decisions

The following items require people, policy, or infrastructure and were not treated as implemented controls:

1. Native Georgian review of terminology, dates, formal tone, truncation, and error messages.
2. Keyboard-only and screen-reader UAT, browser zoom review, and testing on supported physical mobile devices.
3. Confirmation that diagnosis and case notes should remain visible to assigned specialists.
4. Decision whether assignment `from_date` and `to_date` should affect current and historical access.
5. Staff account provisioning, deprovisioning, periodic role review, separation-of-duty, and emergency-access procedures.
6. Retention, correction, erasure, privacy-request, legal-basis, consent, incident, breach-notification, and backup-reconciliation rules.
7. Deletion policy, including whether hard deletion should become soft deletion and which roles may delete case attachments.
8. Approved secure temporary-code delivery, account recovery support, and optional SSO or MFA requirements.
9. Approved production hostnames, trusted proxy chain, certificate issuance and renewal, HSTS preload decision, and client-IP forwarding configuration.
10. Malware scanning or content disarm, quarantine behavior, object storage, and file-retention policy.
11. Immutable external audit retention, audit review ownership, monitoring, alerting, SIEM forwarding, and incident evidence handling.
12. Backup frequency, encryption, off-host and immutable storage, key custody, RPO, RTO, and an operator-observed restore drill.
13. Dependency, image, and infrastructure vulnerability scanning and patch ownership.
14. Employee contract attachment interface and HR access policy.
15. Synthetic migration rehearsal, reconciliation rules, business sign-off, and a separate decision before any real-data migration.
16. Load, capacity, failure, and longer-running concurrency tests under representative infrastructure.

## Final boundary

The application is suitable for a controlled stakeholder demonstration using synthetic data. It must not be described as production-ready, exposed as a production service, or populated with real beneficiary data until the open decisions and operational controls above are completed and approved.
