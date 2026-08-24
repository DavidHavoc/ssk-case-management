# Service Visits and Schedules

## Delivered service record

Every service visit belongs to one service enrollment and retains the beneficiary, event-time center, and responsible specialist for indexed authorization and historical reporting. Activity, delivery location, and participation format are separate fields.

The governed activity catalog contains individual meeting, group meeting, parent or guardian consultation, hygiene care, psychosocial support, household help, medication monitoring, health checks, beneficiary transport, shopping support, food delivery, and other. The governed location catalog contains center, home, school, hospital, community, remote, and other. Catalog entries have stable codes, English and Georgian labels, effective dates, active state, and reporting order. Activities can optionally be limited to selected service definitions.

Participation format is either individual or group. Individual visits normalize to one participant. Group visits require at least two participants. The Other activity requires explanatory notes.

## Workflow and units

Visit states are planned, completed, no-show, and cancelled. Only completed visits produce delivered service units or delivered duration totals. Completed visits require positive units and positive duration. Planned, no-show, and cancelled visits normalize delivered units to zero. Cancelled visits require a cancellation reason.

Visit dates must fall inside an open enrollment period with an effective center placement and specialist assignment. The selected activity and location must also be effective on the visit date. Completed and no-show records cannot use an enrollment state that was not active on that date. A planned record may use a pending or active enrollment.

These units are service evidence for a later timesheet boundary. This implementation does not calculate payroll, rates, tax, deductions, or payment.

## Monthly schedules

An enrollment service schedule stores one monthly plan for a combination of enrollment, activity, location, and format. It records planned visits, planned units, expected participants, and notes. The month is stored as its first calendar day. Schedules require an open enrollment and a center placement in that month.

Schedules are not completed visits and never contribute delivered units. The planned versus delivered report combines authorized schedules and visits by beneficiary, enrollment, month, activity, location, and format. Schedule-only and delivery-only combinations remain visible. The report shows planned and delivered counts and units, variance, delivered duration, no-shows, and cancellations.

## Corrections and compatibility

Editing an existing visit requires a correction reason. Saving the correction appends an immutable record with the actor, reason, and before and after snapshots. The normal append-only audit log also records the update action.

Migration `0008_service_visit_delivery_expansion` renames the old `visit_type` column to `legacy_visit_type`, seeds the governed catalogs, and maps every existing visit to explicit dimensions. Location-style legacy values map to an individual meeting at the corresponding location. Group session maps to group meeting and group format. The original legacy value remains stored for reconciliation. Existing no-show and cancelled rows are normalized to zero delivered units.
