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
| Beneficiary list and detail | All | No | Enrollment owned by current assigned center | Current center and enrollment assignment effective today |
| Beneficiary create | Yes | No | Current assigned center | No |
| Beneficiary unrestricted update | Yes | No | Current assigned center | No |
| Beneficiary allowed-field update | Yes | No | Current assigned center | Currently assigned enrollment only |
| Restricted beneficiary fields | Yes | No | Enrollment owned by current assigned center | Never |
| Service enrollments and lifecycle | Manage | No | Manage in current center | View currently assigned episodes only |
| Enrollment specialist assignments | Manage | No case assignment access | Manage in current center | Never visible or editable |
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
| Beneficiary attachment | All | No | Current center | Denied |
| Visit, assessment, plan attachment | Authorized parent | No | Authorized event-time parent | Read with authorized historical parent; change requires record-date assignment |
| Audit event view | All | No | No | No |

## Effective assignment policy

- `valid_from` is inclusive and `valid_to` is exclusive. Access ends at the start of `valid_to`.
- A null `valid_to` means the assignment is open-ended.
- A null `valid_from` is preserved only as incomplete legacy history and does not establish current or record-date access.
- Current specialist card, list, report, timeline, and attachment access requires an assignment effective today, a current enrollment placement in the selected center, an active user, and an active staff profile.
- A future assignment grants no routine access before `valid_from`.
- An expired or removed assignment grants no routine access. Authorship does not preserve access.
- A currently assigned specialist may read the approved continuity history of that enrollment, including authorized records and their attachments from before the assignment started or from a prior center.
- Creating or changing a dated record requires the acting specialist's assignment and the enrollment placement to be effective on that record's business date. The selected record specialist must also have an assignment effective on that date.
- Every effective-date check binds the specialist and both interval boundaries to the same assignment row. Overlapping expired rows cannot combine with another row to produce access.

## Restricted beneficiary fields

- personal ID;
- address;
- guardian or parent;
- phone;
- email;
- application or contract number;
- specialist assignments;
- attachments.

## Bypass controls

| Bypass path | Control |
|---|---|
| Direct URL | Object is fetched only from an authorized QuerySet |
| Cross-center form POST | Enrollment and relationship fields contain authorized choices only, followed by model validation |
| Report filter | Base report QuerySet is authorized before filters are applied |
| Planned versus delivered report | Schedule and visit sources are each authorized before aggregation |
| Plan outcome report | Authorized plan selector runs before category totals, status totals, review conclusions, and CSV rows are derived |
| CSV export | Same report selector, coordinator or manager role gate, safe columns only |
| Case attachment identifier | Beneficiary files remain selected-center scoped. Event files recheck the authorized parent, its stored event-time center, and change scope |
| Staff attachment identifier | Staff parent scope is checked before HR-field or change capability. Cross-center identifiers return 404 |
| Staff access-code reset | POST only, staff change selector required, own-account reset rejected, plaintext code excluded from storage and audit metadata |
| Timeline entry or attachment | Entry sources begin with authorized selectors; attachment parent scopes are built by the centralized private attachment module |
| Public file URL | Private storage has no URL and is not mounted in the reverse proxy |
| Restricted extra POST keys | Fields are absent from the specialist ModelForm |
| Specialist assignment edit | No specialist route accepts assignment child data. Coordinator forms expose dated assignment fields with explicit boundary help |
| Center session manipulation | Active center UUID is revalidated against current memberships every request |

## Denial behavior

Out-of-scope record and file identifiers return 404 to limit existence disclosure. Role-level action denial returns the accessible 403 page. Authentication is required for every case, report, audit, and download view.
