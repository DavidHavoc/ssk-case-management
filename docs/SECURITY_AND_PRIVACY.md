# Security and Privacy Guide

This is technical guidance, not legal advice. The organization must determine lawful basis, notices, consent where applicable, retention, data-subject processes, incident obligations, and regulatory requirements.

## Implemented controls

### Identity and sessions

- Django authentication and password hashing
- Django session cookies with HttpOnly and SameSite controls
- Secure cookies, HSTS, and HTTPS redirect when debug is disabled
- Django password reset tokens and email workflow
- case-insensitive unique nonblank user email addresses for unambiguous password reset delivery
- database-backed login failure and password-reset request throttling keyed by HMAC values
- no custom password hashing or authentication cryptography

### Authorization

- System Manager, SSK Center Coordinator, and SSK Specialist Groups
- active-center selection revalidated on every request
- shared server-side QuerySet selectors for lists, records, reports, exports, and files
- coordinator center scope and specialist assignment scope
- inactive staff profiles excluded from center, case, and assignment selectors
- restricted beneficiary fields removed from specialist forms and pages
- cross-center and unassigned object identifiers return 404
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
- authorized deletion with file removal scheduled only after the database transaction commits
- Nginx has no private-volume mount

Content validation reduces obvious format spoofing. It is not antivirus or content-disarm scanning. Approve and integrate malware scanning before production if required by the threat model.

### Audit and logging

Audit Events cover sensitive detail reads, record changes made through application views, report exports, downloads, and authentication outcomes. Metadata is allowlisted and excludes beneficiary values, file contents, usernames from failed login attempts, and removed values.

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

Diagnosis and case notes are visible to an assigned specialist. This matches the inspected legacy boundary and must be confirmed during the organizational privacy review.

## Secrets

Store the Django secret, database password, SMTP credential, TLS keys, backup encryption keys, and infrastructure tokens in an approved secret manager or protected environment. Rotate on exposure or staff change according to policy. Never place them in source control, screenshots, tickets, chat, or demo data.

## Not implemented

- automated beneficiary data-subject export;
- identity-verification or privacy-request workflow;
- correction approval, anonymization, erasure, or retention jobs;
- automated processing of historical audit, sent email, or backup copies;
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
- [ ] Password reset email uses an approved service and TLS.
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
