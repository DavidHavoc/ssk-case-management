# Permission Matrix

Authorization is checked on the server. Template visibility is only a usability aid.

Coordinator and specialist access also requires an active user and active staff profile. Marking the user or staff profile inactive revokes non-manager center, case, report, and file access.

| Area | System Manager | SSK Central HR | SSK Center Coordinator | SSK Specialist |
|---|---|---|---|---|
| Centers | All | No casework center access | Assigned centers | Assigned specialist centers |
| Center create | Yes | No | No | No |
| Center update | Yes | No | Assigned center | No |
| Specialist roster view | All | Organization-wide staff scope | Assigned center | Assigned center |
| Specialist roster manage | All | No case assignment management | Assigned center | No |
| Employee roster | All | Organization-wide | Staff assigned to an authorized center | No unless explicitly granted |
| HR fields and employee documents | All | Organization-wide | Authorized-center staff only with explicit `centers.view_staffprofile` | Organization-wide only with explicit `centers.view_staffprofile` |
| Employee profile and document change | All | Organization-wide | Authorized-center staff only with explicit `centers.change_staffprofile` | Organization-wide only with explicit `centers.change_staffprofile` |
| Employee temporary access-code reset | All except own account | Organization-wide except own account | Authorized-center staff only with explicit `centers.change_staffprofile`, except own account | Organization-wide only with explicit `centers.change_staffprofile`, except own account |
| Beneficiary list and detail | All | No | Enrollment owned by current assigned center | Current center and person-level lead/helper responsibility effective today |
| Beneficiary create | Yes | No | Current assigned center | No |
| Beneficiary unrestricted update | Yes | No | Current assigned center | No |
| Beneficiary allowed-field update | Yes | No | Current assigned center | Currently assigned enrollment only |
| Restricted beneficiary fields | Yes | No | Enrollment owned by current assigned center | Never |
| Service enrollments and lifecycle | Manage | No | Manage in current center | View currently assigned episodes only |
| Beneficiary lead/helper pair | Manage | No case assignment access | Manage in current center | View current names and roles only; never edit |
| Enrollment specialist assignment evidence | Read preserved history | No case assignment access | Read preserved history | Historical assignment rows remain restricted |
| Diagnosis and social status | All | No | Current-center beneficiary | Explicitly visible entries for a currently assigned enrollment only |
| Beneficiary delete | Yes, current center | No | No | No |
| Service Visit | All | No | Event-time center | Current assigned enrollment history; change also requires assignment on visit date |
| Monthly Service Schedule | All | No | Event-time placement center | Current assigned enrollment; change also requires assignment in schedule month |
| Assessment | All | No | Event-time center | Current assigned enrollment history; change also requires assignment on assessment date |
| Individual Plan | All | No | Event-time center | Current assigned enrollment history; change also requires assignment on plan start date |
| Plan goal, measurement, and review | Through authorized parent plan | No | Through authorized parent plan | Through authorized parent plan and record-date change scope |
| Enrollment activity timeline | Authorized selected enrollment | No | Authorized event-time center records | Approved continuity history of currently assigned enrollment |
| Visit, assessment, and plan delete | Yes, current center | No | No | No |
| Monthly summaries | All | No | Current center | Own specialist summary only |
| HTML reports | All | No | Authorized center scope | Same current enrollment and continuity selectors as lists |
| CSV export | All | No case export | Authorized center scope | Denied |
| In-application reminders | Authorized center records and contracts | No case reminders | Authorized center records and contracts | Assigned enrollment records and own contract only |
| Beneficiary attachment | All | No | Current center | Denied |
| Visit, assessment, plan attachment | Authorized parent | No | Authorized event-time parent | Read with authorized historical parent; change requires record-date assignment |
| Audit event view | All | No | No | No |

## Effective assignment policy

- `valid_from` is inclusive and `valid_to` is exclusive. Access ends at the start of `valid_to`.
- A null `valid_to` means the assignment is open-ended.
- A null `valid_from` is preserved only as incomplete legacy history and does not establish current or record-date access.
- Current specialist card, list, report, timeline, and attachment access requires a person-level staffing period effective today, a current enrollment placement in the selected center, an active user, and an active staff profile.
- A future assignment grants no routine access before `valid_from`.
- An expired or removed assignment grants no routine access. Authorship does not preserve access.
- A currently assigned specialist may read the approved continuity history of that enrollment, including authorized records and their attachments from before the assignment started or from a prior center.
- Creating or changing a dated record requires the acting specialist's assignment and the enrollment placement to be effective on that record's business date. The selected record specialist must also have an assignment effective on that date.
- Every effective-date check binds the specialist and both interval boundaries to the same assignment row. Overlapping expired rows cannot combine with another row to produce access.

## Confirmed person-level staffing, 2026-10-08

A beneficiary has one Lead specialist / მთავარი სპეციალისტი and zero or one Helper specialist /
დამხმარე სპეციალისტი across services. Both receive ordinary assigned-specialist casework rights.
Each service still requires the specialist's active user and staff profile, active selected-center
membership, an appropriate enrollment placement, and the applicable business-date responsibility.
The pair grants no powers over other people, other centers, staffing management, restricted person
fields, or beneficiary documents. The current pair's names and role labels are visible on the
already authorized beneficiary page. Historical source assignments remain restricted.

`BeneficiaryStaffingPeriod` is the only operational staffing authority. Each complete pair uses
an inclusive start and exclusive end. Periods cannot overlap, even for future replacements.
Once a period starts, an expired period cannot revive enrollment-level compatibility access.
Before the first confirmed period, untouched dated enrollment evidence remains authoritative for
record dates before today; current and future work requires confirmed responsibility,
current eligibility, placement, and current case access. Authorship never independently grants continuity access.

The legacy bridge is an immutable migration snapshot of assignments that already granted current
access at the release date, restricted to the original enrollment, specialist, center, and placement. It
expires on the migration capture date itself, exclusively. The owner chose to end legacy access
at deployment on 2026-10-09. Unknown starts,
future appointments, inactive accounts, and new imported evidence cannot create bridge access.
New services receive no bridge grant. Managers get a staffing review flag and a reminder with the
deployment-day expiry. Confirm a complete pair for unresolved cases using an explicit lead/helper
choice before specialists resume work. Resolving joint leads changes only responsibility from the confirmation date; original
joint roles and source documents remain preserved. See [staffing handoff](BENEFICIARY_STAFFING_HANDOFF.md).

Casework and attachment changes recheck the acting account and scope under the same beneficiary
lock as staffing, transfers, and lifecycle changes. Deferred form saves carry the actor into the
model write. This closes the gap between form validation and saving after reassignment or
deactivation. A return transfer creates a new placement and never revives an old bridge grant.

## Restricted beneficiary fields

- personal ID;
- address;
- guardian/parent or supporter (stored in `guardian_parent`);
- optional emergency contact name and phone number;
- phone;
- email;
- application or contract number;
- historical specialist assignment evidence;
- attachments.

Emergency contacts use the same server-side role and center scope as the existing
restricted person fields. Currently assigned specialists cannot see these contacts
or submit changes to them, including through forged extra POST keys. Contact values
are excluded from report HTML, CSV exports, lists, timelines, and audit metadata.

## Bypass controls

| Bypass path | Control |
|---|---|
| Direct URL | Object is fetched only from an authorized QuerySet |
| Cross-center form POST | Enrollment and relationship fields contain authorized choices only, followed by model validation |
| Report filter | Base report QuerySet is authorized before filters are applied |
| Planned versus delivered report | Schedule and visit sources are each authorized before aggregation |
| Plan outcome report | Authorized plan selector runs before category totals, status totals, review conclusions, and CSV rows are derived |
| Operational aggregation | Every aggregation receives an authorized QuerySet before filters, grouping, or exception derivation |
| Reminders | Due work and data-quality items are derived from authorized QuerySets and are displayed only inside the application |
| CSV export | Same report selector, coordinator or manager role gate, safe columns only |
| Case attachment identifier | Beneficiary files remain selected-center scoped. Event files recheck the authorized parent, its stored event-time center, and change scope |
| Staff attachment identifier | Staff parent scope is checked before HR-field or change capability. Cross-center identifiers return 404 |
| Staff access-code reset | POST only, staff change selector required, own-account reset rejected, plaintext code excluded from storage and audit metadata |
| Timeline entry or attachment | Entry sources begin with authorized selectors; attachment parent scopes are built by the centralized private attachment module |
| Public file URL | Private storage has no URL and is not mounted in the reverse proxy |
| Restricted extra POST keys | Fields are absent from the specialist ModelForm |
| Specialist assignment edit | Managers and coordinators replace one complete beneficiary pair. Specialists cannot submit staffing changes; enrollment assignment evidence is read-only |
| Center session manipulation | Active center UUID is revalidated against current memberships every request |

## Denial behavior

Out-of-scope record and file identifiers return 404 to limit existence disclosure. Role-level action denial returns the accessible 403 page. Authentication is required for every case, report, audit, and download view.

## Beneficiary intake, 2026-10-09

The owner expanded reported health and social support access for confirmed current leads/helpers.
`beneficiary_intake_capabilities` separates this permission from restricted person fields,
consent answers, and ordinary initial care planning. These sections belong to beneficiaries.
They do not appear on employee profiles.

| Intake area | System Manager | Center Coordinator | Specialist | Central HR |
|---|---|---|---|---|
| Health and social support | Authorized beneficiary in selected active center | Active staff membership and authorized beneficiary/enrollment | Active user/profile, selected-center membership, confirmed current lead/helper pair, and authorized current enrollment placement | Denied |
| Staff-recorded consent decisions | Authorized beneficiary in selected active center | Active staff membership and authorized beneficiary/enrollment | Denied | Denied |
| Initial care checklist | Authorized beneficiary/enrollment | Authorized beneficiary/enrollment | Existing current case-planning permission through an authorized active enrollment | Denied |
| Intake revision evidence | Restricted stored evidence; no new public history endpoint | Restricted stored evidence; no new public history endpoint | Not exposed | Denied |

An inactive account, inactive center, or inactive staff profile denies all new intake capabilities.
Manager accounts without a staff profile retain their existing manager role authority. For specialists,
lead/helper responsibility and placement must be effective today. The captured legacy bridge retains
ordinary care-planning rights where already authorized, but it does not receive the expanded health,
social, or consent grant. Out-of-scope beneficiary identifiers return 404; an accessible beneficiary
without an intake capability receives 403 on the dedicated intake editor.

Treating doctor details are part of the specifically authorized health information. This change does
not expose beneficiary phones, emails, addresses, personal IDs, guardian identity, emergency contacts,
source registers, or beneficiary documents to specialists. Forms and detail projections fetch only
authorized intake columns. Forged consent/person keys are absent from specialist forms and ignored;
the write service rejects forbidden field names if called directly. Writes reload the persisted
beneficiary, user, center, responsibility, and placement under the shared beneficiary lock.

See [intake handoff](BENEFICIARY_INTAKE_HANDOFF.md) for schema, verification, and signature boundaries.

## Handwritten consent signing, 2026-10-09

Only the existing active intake consent capability grants the signing review, unsigned paper
copy, signed-document view, or private HTML download. System Managers and authorized center
coordinators must still have the beneficiary in their selected active center. Inactive accounts,
inactive profiles or centers, missing center membership, Central HR alone, and every specialist
including a confirmed lead or helper are denied. Specialists retain their health/social capability.

Every signed record and both generated private attachments are bound to the signing center.
A transfer does not expose the prior center's signed evidence at the destination. Every route
uses an authorized selector; the final service reloads authority under the shared beneficiary lock.
The recorder is the authenticated staff account. Signer name, capacity, and stated relationship
are independently entered information and do not establish identity or legal authority.
