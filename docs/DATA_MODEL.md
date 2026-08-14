# Data Model

All domain records use UUID primary keys and created and updated timestamps unless stated otherwise.

## Identity and centers

| Entity | Important fields and relationships |
|---|---|
| User | Django username, email, password hash, preferred language, Group roles |
| Center | Unique code and name, active state, contact information |
| Staff Profile | One User, unique employee number, status, primary Center, many Center memberships |
| Specialist Profile | One Staff Profile and shared specialist description |
| Specialist Center Assignment | One Specialist Profile, one Center, optional primary flag |

Constraints prevent duplicate specialist and center pairs and more than one primary center per specialist.

## Case records

| Entity | Important fields and relationships |
|---|---|
| Beneficiary | Center, unique case code, demographic, contact, case, date, and restricted fields |
| Beneficiary Specialist Assignment | Beneficiary, Specialist Profile, assignment role, from and to dates |
| Service Visit | Beneficiary, Center, Specialist, visit date and month, type, status, units, duration |
| Assessment | Beneficiary, Center, Specialist, type, date, previous Assessment, cycle, tool, totals |
| Assessment Domain Score | Assessment, domain, baseline and current scores, notes |
| Individual Plan | Beneficiary, Center, Specialist, status, dates, review frequency |
| Individual Plan Goal | Individual Plan, goal, target date, status, progress notes |
| Specialist Monthly Service Summary | Specialist, Center, month, visit and service aggregates |

Assignment uniqueness prevents a specialist appearing twice on one beneficiary. Assignment dates and plan dates have database and model ordering checks where practical.

Service Visit derives Center from Beneficiary and derives Visit Month from Visit Date. Assessment and Individual Plan also derive Center from Beneficiary. Every selected specialist must be assigned to that beneficiary.

## Privacy records

| Entity | Important fields and relationships |
|---|---|
| Private Attachment | Parent type and UUID, Center, private file, original name, size, SHA-256, uploader |
| Audit Event | Actor, Center, event type, outcome, target type and UUID, safe metadata, timestamp |
| Login Throttle | HMAC key, failure count, window start, update timestamp |

Private Attachment intentionally uses a restricted parent-type map rather than accepting arbitrary models. Audit Event metadata accepts only a small allowlist and never stores beneficiary field values or file contents.

## Derived summary rules

A summary is unique by Specialist, Center, and calendar month. Rebuilds count:

- completed visits;
- completed service units;
- completed duration minutes;
- unique beneficiaries with completed visits;
- no-show visits;
- cancelled visits.

Updating a visit rebuilds both its new summary key and its previous key. Deleting the last visit removes the empty summary.

## Index strategy

- Center plus status for beneficiary and plan lists
- Center plus date and status or type for visits and assessments
- Specialist plus month or status for reporting
- Beneficiary plus date for case timelines
- Parent type plus UUID for attachment lookup
- Actor, Center, target, and timestamp for audit review
