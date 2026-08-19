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
| `casework` | Beneficiaries, visits, assessments, plans, summaries, the derived timeline, and the private attachment module |
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
9. Reports and CSV exports reuse the same selectors. The private attachment module applies those selectors through explicit parent-policy adapters.

The beneficiary detail timeline follows the same flow. `apps/casework/timeline.py` starts with the authorized visit, assessment, and plan selectors, narrows them to the already authorized beneficiary, and reaches goals only through the authorized plan scope. The private attachment workflow supplies a beneficiary-timeline QuerySet whose parent IDs come from the same selectors. Templates receive frozen presentation-only timeline entries rather than model instances.

System Manager bypasses record scope. Coordinator access takes precedence when a user also holds Specialist. Specialist access requires a Specialist Profile and valid Specialist Center Assignment.

## Privacy boundary

Restricted beneficiary values are represented in the model because coordinators need them, but specialist pages and exports do not render them. Beneficiary forms remove those fields for specialists, so extra submitted field names are ignored. Specialist assignments are managed only in coordinator and System Manager workflows.

Private attachments have randomized stored names, parent type, parent UUID, center, original display name, content type, size, and SHA-256 digest. The storage backend rejects resolved paths outside its root. Nginx never maps the private volume.

`apps/casework/private_attachments.py` owns the complete private attachment lifecycle behind two public factories: `case_attachments(actor, center)` and `staff_attachments(actor)`. The returned workflow exposes lifecycle-level list, upload, create-time upload, download, and delete operations. Policy lookup, forms, authorization, transaction helpers, response construction, cleanup, and route selection remain internal. Its parent-policy registry is the single map from parent type to model, authorization adapter, center rule, form behavior, and detail route. Beneficiary, visit, assessment, and plan policies adapt the existing case selectors and require the selected active center. The staff policy adapts staff-directory view and change permissions and intentionally remains organization-wide. Casework and centers views only supply request context, messages, and templates.

The attachment module constructs metadata, coordinates database transactions and rollback cleanup, records audit events, authorizes every selection, builds download responses, resolves redirects, and schedules deleted files for post-commit removal. Low-level upload validation and private storage remain in `validators.py` and `storage.py` so existing model field and migration import paths stay stable. `PrivateAttachment.clean()` uses the same registry for parent and center validation as a defense-in-depth control.

## Business logic placement

- Models enforce invariant data relationships and dates.
- Forms enforce user-specific choices and inline child requirements.
- Authorization selectors define domain read scope once for lists, details, reports, and attachment policy adapters.
- The timeline module owns authorized heterogeneous indexing, normalization, deterministic ordering, and pagination for beneficiary activity.
- The private attachment module owns parent resolution, forms, upload transactions, auditing, download responses, deletion, cleanup, and navigation.
- Services rebuild derived monthly summaries inside the visit transaction. PostgreSQL advisory locks serialize rebuilds for the same specialist, center, and month.
- Other views coordinate domain record transactions and record domain audit events.
- Templates contain presentation only.

## Performance

Major lists use `select_related()` and `prefetch_related()` for beneficiary, specialist, staff, user, center, and assignment relationships. Reporting columns have indexes for center, specialist, beneficiary, date, month, status, and type. Lists are paginated and report pages cap rendered rows at 500. CSV writes rows incrementally.

The timeline builds a database `UNION ALL` of presentation-safe index columns, orders that union deterministically, and applies offset pagination before normalization. Only IDs on the requested 20-entry page are loaded, in bounded per-type `values()` queries. Query count therefore does not grow per rendered entry. Deep offset pages still require the database to count and seek through earlier authorized rows, which is acceptable for the initial scale but should be monitored if individual histories become very large.

## Production topology

The provided production example has three services: PostgreSQL, the Django image running Gunicorn, and Nginx. A single-node design is appropriate for initial scale, provided encrypted off-host backups, TLS, monitoring, and restore tests are implemented. Horizontal Django scaling requires shared private object storage or a shared encrypted filesystem and careful download authorization preservation.
