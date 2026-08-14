# Architecture

## System shape

SSK Case Management is one Django process with server-rendered templates. PostgreSQL is the system of record. A reverse proxy terminates TLS and forwards application requests to Gunicorn. WhiteNoise serves versioned static assets. Private files are stored in a dedicated non-public volume and can be read only through an authorized Django view.

```text
Browser
  |
TLS reverse proxy
  |
Gunicorn and Django
  |                 |
PostgreSQL     private file volume
```

There is no separate browser application, API gateway, worker requirement, Redis dependency, or custom authentication protocol.

## Django applications

| App | Responsibility |
|---|---|
| `accounts` | Custom User, Django Group roles, login throttling |
| `centers` | Center, Staff Profile, Specialist Profile, roster assignments |
| `casework` | Beneficiaries, visits, assessments, plans, summaries, private files |
| `audit` | Append-only application audit events and safe event writer |
| `core` | Authorization selectors, active-center context, dashboard, reports, shared UI |

## Request authorization flow

1. Django session authentication establishes the User.
2. Role helpers evaluate Django Groups.
3. `accessible_centers()` derives current center membership.
4. `active_center_for_request()` validates the session center every request.
5. A domain selector builds the authorized QuerySet.
6. Detail views fetch only from that QuerySet, returning 404 for out-of-scope identifiers.
7. Forms restrict relationship choices to authorized QuerySets.
8. Model validation checks center and assignment consistency independently of the view.
9. Reports, CSV exports, and downloads reuse the same selectors.

System Manager bypasses record scope. Coordinator access takes precedence when a user also holds Specialist. Specialist access requires a Specialist Profile and valid Specialist Center Assignment.

## Privacy boundary

Restricted beneficiary values are represented in the model because coordinators need them, but specialist pages and exports do not render them. Beneficiary forms remove those fields for specialists, so extra submitted field names are ignored. Specialist assignments are managed only in coordinator and System Manager workflows.

Private attachments have randomized stored names, parent type, parent UUID, center, original display name, content type, size, and SHA-256 digest. The storage backend rejects resolved paths outside its root. Nginx never maps the private volume.

## Business logic placement

- Models enforce invariant data relationships and dates.
- Forms enforce user-specific choices and inline child requirements.
- Authorization selectors define read scope once for lists, details, reports, and downloads.
- Services rebuild derived monthly summaries inside the visit transaction. PostgreSQL advisory locks serialize rebuilds for the same specialist, center, and month.
- Views coordinate transactions and record audit events.
- Templates contain presentation only.

## Performance

Major lists use `select_related()` and `prefetch_related()` for beneficiary, specialist, staff, user, center, and assignment relationships. Reporting columns have indexes for center, specialist, beneficiary, date, month, status, and type. Lists are paginated and report pages cap rendered rows at 500. CSV writes rows incrementally.

## Production topology

The provided production example has three services: PostgreSQL, the Django image running Gunicorn, and Nginx. A single-node design is appropriate for initial scale, provided encrypted off-host backups, TLS, monitoring, and restore tests are implemented. Horizontal Django scaling requires shared private object storage or a shared encrypted filesystem and careful download authorization preservation.
