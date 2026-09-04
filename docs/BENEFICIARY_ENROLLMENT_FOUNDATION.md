# Beneficiary and Service Enrollment Foundation

## Record boundaries

`Beneficiary` is the durable person record. A person can have any number of `ServiceEnrollment` episodes, including concurrent episodes for different services. Transaction records belong to one enrollment and also retain their beneficiary and event-time center for indexed authorization and historical reporting.

The original beneficiary center, service type, case status, application number, contract number, diagnosis narrative, and geography text remain available as legacy compatibility fields. New workflows do not reinterpret those values. Controlled geography and coded classifications use separate nullable relationships.

## Service configuration

`ServiceDefinition` is the organization-wide catalog. It supports home care, food delivery, early intervention, future services, and legacy migration entries. `CenterServiceOffering` explicitly enables a service at a center and sets whether overlapping episodes of the same service are permitted.

An enrollment can reference only an enabled offering for its center. Transfers require an enabled destination offering for the same service. Center ownership is represented by effective-dated `EnrollmentCenterPlacement` rows, so a transfer does not overwrite history.

New centers intentionally start without offerings. A System Manager configures them explicitly
from the active center's detail page because different centers provide different services. New
offerings may use active non-legacy service definitions only. Existing offerings remain available
for validity-date and active-status updates and are not deleted through this workflow. Creation
and update actions are audited.

## Enrollment lifecycle

The supported states are pending, active, suspended, completed, exited, and cancelled. Lifecycle changes are written through the service layer and recorded as append-only `EnrollmentStateEvent` rows. Supported events include creation, admission, suspension, resumption, transfer, completion, exit, cancellation, and re-enrollment.

Re-enrollment creates a new episode linked through `prior_enrollment`; it never reopens or overwrites the previous episode. Dates use half-open intervals: `valid_from` is included and `valid_to` is excluded. A terminal transition date is the first date on which the terminal state applies, so the prior active or suspended state ends before that date.

## Geography and classifications

`Region` and `Municipality` provide controlled Georgian administrative data. Every municipality belongs to exactly one region, and model and form validation reject a municipality paired with another region. The initial catalog contains 11 operational reporting regions and the 64 municipalities listed by the [National Statistics Office of Georgia municipality comparison](https://regions.geostat.ge/regions/comparison/municipalComp.php?lang=en), verified on 2026-08-20. The matching [Georgian catalog](https://regions.geostat.ge/regions/comparison/municipalComp.php?lang=ka) supplies the Georgian spellings.

Governed service, region, municipality, diagnosis, and social-status labels render from `name_en` or `name_ka` according to the active interface language. Preserved legacy service categories also have explicit Georgian compatibility labels.

Diagnosis definitions, social-status definitions, and free-text case notes are separate concepts. `BeneficiaryDiagnosis` and `BeneficiarySocialStatus` support multiple effective-dated entries. Specialist visibility is explicit per classification and is additionally limited to an enrollment the specialist is currently assigned to.

## Age calculation

Age is calculated from date of birth for a supplied reference date as completed years and months. A birth on the last day of a month reaches each monthly anniversary on the last day of a shorter month. A 29 February birth therefore reaches the annual anniversary on 28 February in a non-leap year.

SSK age bands use completed months and are unambiguous:

- `0-3`: birth through 35 completed months
- `3-5`: 36 through 59 completed months
- `5-7`: 60 through 83 completed months
- 84 completed months and older: outside these SSK bands

## Migration and compatibility

Migration `0006_seed_catalogs_and_backfill_enrollments` creates one legacy enrollment for each existing beneficiary and links every existing visit, assessment, plan, and specialist assignment to it. Existing source values are copied to `legacy_service_value` and `legacy_status_value`. Legacy free-text geography and diagnosis remain unchanged and are not automatically mapped to controlled codes.

Existing records with missing dates remain missing. Exact legacy assignment intervals are marked as preserved legacy intervals instead of being discarded. New records use validated effective intervals.

Enrollment create and update forms display one optional extra specialist-assignment row. The
specialist choices are restricted to active specialists assigned to the selected center. Blank
extra rows are ignored, while completed rows retain the effective-date and authorization
validation applied by the server.

Legacy transaction callers that omit an enrollment remain compatible only when the beneficiary has exactly one enrollment. Ambiguous multi-enrollment writes are rejected. The user interface and new code always select an enrollment explicitly.

## Authorization

Center authorization follows the enrollment placement that applies at the record date. Coordinators receive only enrollment episodes owned by their active center. Specialists receive only current, effective enrollment assignments. Restricted person fields remain unavailable to specialists.

Diagnosis and social-status selectors enforce both enrollment assignment and the explicit specialist visibility flag. Transaction relationship choices are built from authorized enrollment selectors and are validated again on the server.

Identity-level attachments retain an explicit center scope. A transferred enrollment does not make an old-center identity document visible at the destination. A newly uploaded identity document is owned by the active authorized center. Transaction attachments continue to follow the event-time center and enrollment-authorized parent record.

## Remaining owner decisions

The implementation is operationally complete for the approved foundation, but these policy choices still require formal owner confirmation:

- whether same-service overlap should be enabled for any canonical service;
- whether future service catalogs need additional family values or service-specific metadata;
- whether diagnosis or social-status visibility should ever default to visible for specialists;
- which role may correct append-only lifecycle events and under what approval process;
- the care-history and attachment boundary the destination receives after transfer;
- whether completed or exited enrollments remain visible to coordinators after a later transfer;
- the publication, retirement, and correction workflow for governed master data;
- formal acceptance of the implemented lifecycle states, completed-month age bands, and 29 February rule;
- the authoritative process and owner for future Geostat catalog updates.
