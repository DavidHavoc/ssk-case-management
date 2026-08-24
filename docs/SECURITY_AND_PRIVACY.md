# Security and Privacy Guide

This is technical guidance, not legal advice. The organization must determine lawful basis, notices, consent where applicable, retention, data-subject processes, incident obligations, and regulatory requirements.

## Implemented controls

### Identity and sessions

- Django authentication and password hashing
- Django session cookies with HttpOnly and SameSite controls
- Secure cookies, HSTS, and HTTPS redirect when debug is disabled
- administrator-issued high-entropy temporary access codes that are stored only as password hashes
- required private-password selection before a temporary-code user can access application pages
- administrator resets authorized through the server-side staff-directory change selector
- case-insensitive unique nonblank user email addresses
- database-backed login failure throttling keyed by HMAC values
- no custom password hashing or authentication cryptography

### Authorization

- System Manager, SSK Central HR, SSK Center Coordinator, and SSK Specialist Groups
- active-center selection revalidated on every request
- shared server-side QuerySet selectors for lists, records, reports, exports, and files
- coordinator enrollment-placement scope and specialist enrollment-assignment scope
- inclusive `valid_from` and exclusive `valid_to` checks for current and record-date access
- unknown legacy assignment starts retained for history but denied as evidence of effective access
- inactive staff profiles excluded from center, case, and assignment selectors
- restricted beneficiary fields removed from specialist forms and pages
- cross-center and unassigned object identifiers return 404
- beneficiary timelines are derived only from authorized selectors and expose presentation-only normalized values
- no public or generic JSON API in the MVP

### Private files

- storage outside static and public media paths
- randomized stored filenames
- original filename reduced to its basename
- allowed extension and maximum size validation
- PDF, PNG, JPEG, UTF-8 text, and DOCX content-structure checks
- resolved-path containment check
- SHA-256 digest and size metadata
- authorized download view with current parent authorization
- one explicit parent-policy registry for parent models, authorization adapters, center rules, form behavior, and detail routes
- beneficiary attachment identifiers constrained to the selected active center
- service-record attachments authorized through the current parent selector while retaining the parent's event-time center, including approved continuity reads after transfer
- staff attachment identifiers constrained by staff-directory view or change permissions
- private, no-store download cache controls on case and staff responses
- successful and denied direct downloads recorded without filenames or file contents
- beneficiary timeline attachments exclude staff documents, keep beneficiary attachments hidden from specialists, and link only to the authorized download view
- authorized deletion with file removal scheduled only after the database transaction commits
- failed upload transactions remove any file written before the database rollback
- Nginx has no private-volume mount

Content validation reduces obvious format spoofing. It is not antivirus or content-disarm scanning. Approve and integrate malware scanning before production if required by the threat model.

### Audit and logging

Audit Events cover sensitive detail reads, authorized report reads, record changes made through application views, report exports, downloads, and authentication outcomes. Denied direct record reads, record changes, report exports, uploads, deletions, and downloads are recorded where the application can safely identify the attempted target. Metadata is allowlisted and excludes beneficiary values, file contents, usernames from failed login attempts, and removed values.

Gunicorn and the included Nginx configuration log URL paths without query strings. Application logs use standard request and error context only. Operators must not add request bodies, form data, file content, beneficiary names, personal IDs, contact fields, filenames, query strings, or session values to logs.

### Export

- Specialist CSV export is denied.
- Coordinator and System Manager CSV uses authorized QuerySets.
- Exported columns exclude restricted beneficiary values.
- Cells that begin with spreadsheet formula control characters receive a leading apostrophe.
- Export actions record row count, report type, and format without content.

## Restricted beneficiary fields

- personal ID;
- address;
- guardian or parent information;
- phone;
- email;
- application or contract number;
- specialist assignments;
- attachments.

Free-text case notes remain part of the person record. Diagnosis and social-status classifications are separate effective-dated records. A specialist sees a classification only when it is explicitly marked visible and belongs to an enrollment currently assigned to that specialist. This boundary must be confirmed during the organizational privacy review.

The beneficiary timeline does not create a secondary copy of case or attachment data. Service visits, assessments, plans, goals, and attachments are read from current authorized sources for every request. Restricted beneficiary fields, private storage paths, stored filenames, hashes, content types, sizes, and uploader metadata are not included in normalized timeline entries. An original attachment filename is shown only as an authorized display label.

## Staff records and contracts

System Managers and members of the `SSK Central HR` Group have organization-wide staff-profile, HR-field, contract, and staff-document access. Central HR has no beneficiary, enrollment, case-record, timeline, report, export, or case-attachment access through that role.

Center coordinators can view a roster containing staff assigned to their authorized centers. The roster omits contact details, contract dates, internal staff notes, descriptions, and staff documents. Search does not use hidden email or contact fields. A coordinator needs an explicit `centers.view_staffprofile` permission to view HR fields and staff documents, and the authorized-center boundary still applies. Changing profiles or documents also requires `centers.change_staffprofile` and remains center-scoped.

Specialists have no staff-directory or HR access by default. An explicit `centers.view_staffprofile` permission grants organization-wide staff and HR read access; `centers.change_staffprofile` grants the corresponding change access. These exceptional grants must be reviewed as HR privileges. A user holding Central HR and another role receives the scopes of both roles; Central HR alone never creates case access.

Project agreements and employee contracts must be PDF files. Additional staff documentation uses the approved private attachment types. All staff files use randomized private storage paths, staff-directory parent authorization, audited downloads, and no-store response headers. Staff document access follows the applicable organization-wide or authorized-center staff scope and does not depend on the casework active-center session. Staff notes, contact details, and contracts must not be copied into logs or audit metadata.

## Effective-dated specialist access

The approved assignment rule uses a half-open interval. `valid_from` is the first authorized date and `valid_to` is the first unauthorized date. A null `valid_to` is open-ended. A null `valid_from` is an incomplete legacy date, not proof of current authority.

Routine specialist access requires an active user, active staff profile, accessible selected center, current enrollment placement, and an enrollment assignment effective today. Future assignments do not grant early access. Expired and removed assignments do not grant continuing access, even when the specialist authored the record.

A currently assigned specialist can read the approved continuity history of the assigned enrollment. That includes authorized visits, assessments, plans, timeline entries, reports, and parent-authorized event attachments created before the current assignment or at a prior center. It does not include unrelated enrollments, beneficiary attachments, hidden classifications, HR content, or another beneficiary's records.

Creating or changing a dated visit, assessment, plan, or monthly schedule also checks the assignment and center placement on the record's business date. Form choices, model validation, update selectors, attachment changes, and direct URLs repeat the same policy. Specialist identity and both date boundaries must match one assignment row so separate expired or overlapping rows cannot accidentally combine into indefinite access.

## Secrets

Store the Django secret, database password, TLS keys, backup encryption keys, and infrastructure tokens in an approved secret manager or protected environment. Rotate on exposure or staff change according to policy. Never place them in source control, screenshots, tickets, chat, or demo data.

## Not implemented

- automated beneficiary data-subject export;
- identity-verification or privacy-request workflow;
- correction approval, anonymization, erasure, or retention jobs;
- automated processing of historical audit or backup copies;
- malware scanning or content disarm;
- external access alerting and SIEM integration;
- automated audit review or policy retention;
- immutable external audit storage.

These items remain future work until business, legal, security, and operational decisions are approved. Do not describe them as current controls.

## Production review checklist

- [ ] Every user has only approved Groups and center memberships.
- [ ] Specialist assignments reflect current work.
- [ ] Cross-center and unassigned direct URLs fail.
- [ ] Restricted values do not appear in specialist HTML, validation errors, CSV, or logs.
- [ ] Private-file storage is not mounted or routed publicly.
- [ ] Temporary access codes are delivered directly through an approved secure channel and are never placed in logs or tickets.
- [ ] Login-throttle proxy address configuration is verified.
- [ ] TLS, HSTS, cookie, host, and CSRF origin settings pass `check --deploy`.
- [ ] Database and private-file backups are encrypted and restore-tested.
- [ ] Dependency and container vulnerability scanning is active.
- [ ] Incident, account lifecycle, audit review, retention, and disposal owners are approved.
- [ ] Synthetic-only staging UAT has passed.

## Incident baseline

1. Restrict affected access and preserve authorized evidence.
2. Revoke exposed sessions, credentials, and keys when indicated.
3. Identify affected records, files, users, integrations, backups, and time range.
4. Keep sensitive values out of general tickets and chat.
5. Record containment, investigation, remediation, recovery, and approval decisions.
6. Route notification and legal decisions to approved organizational owners.
