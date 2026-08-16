# Permission Matrix

Authorization is checked on the server. Template visibility is only a usability aid.

Coordinator and specialist access also requires an active staff profile. Marking a staff profile inactive revokes all non-manager center and case access even if the Django account has not yet been disabled.

| Area | System Manager | SSK Center Coordinator | SSK Specialist |
|---|---|---|---|
| Centers | All | Assigned centers | Assigned specialist centers |
| Center create | Yes | No | No |
| Center update | Yes | Assigned center | No |
| Specialist roster view | All | Assigned center | Assigned center |
| Specialist roster manage | All | Assigned center | No |
| Employee directory and details | All | With `centers.view_staffprofile` permission | With `centers.view_staffprofile` permission |
| Employee profile edit and document management | All | With `centers.change_staffprofile` permission | With `centers.change_staffprofile` permission |
| Employee document download | All | With `centers.view_staffprofile` permission | With `centers.view_staffprofile` permission |
| Beneficiary list and detail | All | Current assigned center | Current center and assigned beneficiary |
| Beneficiary create | Yes | Current assigned center | No |
| Beneficiary unrestricted update | Yes | Current assigned center | No |
| Beneficiary allowed-field update | Yes | Yes | Assigned beneficiary only |
| Restricted beneficiary fields | Yes | Current assigned center | Never |
| Beneficiary specialist assignments | Manage | Manage in current center | Never visible or editable |
| Beneficiary delete | Yes, current center | No | No |
| Service Visit | All | Current center | Current center and record specialist or beneficiary assignment |
| Assessment | All | Current center | Current center and record specialist or beneficiary assignment |
| Individual Plan | All | Current center | Current center and record specialist or beneficiary assignment |
| Visit, assessment, and plan delete | Yes, current center | No | No |
| Monthly summaries | All | Current center | Own specialist summary only |
| HTML reports | All | Current center | Authorized record scope |
| CSV export | All | Current center | Denied |
| Beneficiary attachment | All | Current center | Denied |
| Visit, assessment, plan attachment | All | Current center | Authorized parent record |
| Authorized attachment delete | Yes | Yes | Yes, except beneficiary attachments |
| Audit event view | All | No | No |

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
| Cross-center form POST | Relationship fields contain authorized choices only, followed by model validation |
| Report filter | Base report QuerySet is authorized before filters are applied |
| CSV export | Same report selector, coordinator or manager role gate, safe columns only |
| Attachment identifier | Attachment center and current parent authorization are rechecked |
| Public file URL | Private storage has no URL and is not mounted in the reverse proxy |
| Restricted extra POST keys | Fields are absent from the specialist ModelForm |
| Specialist assignment edit | No specialist route accepts assignment child data |
| Center session manipulation | Active center UUID is revalidated against current memberships every request |

## Denial behavior

Out-of-scope record and file identifiers return 404 to limit existence disclosure. Role-level action denial returns the accessible 403 page. Authentication is required for every case, report, audit, and download view.
