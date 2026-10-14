# Versioned Assessment Engine

## Scope and evidence boundary

The assessment engine uses immutable templates. On 2026-10-14 the owner supplied the Georgian Barthel activities and confirmed the five functional dependency and care need bands. Migration 0024 installs the published `ssk-20261014-1` template, shown to staff as `ბართელის სკალა` or `Barthel scale`. The earlier Barthel structural draft and the AEPS drafts remain unpublished.

## Domain model

- `AssessmentInstrument` is the stable tool identity. Seeded identifiers are Barthel, old AEPS, new AEPS, ICF-based, and Other. `lineage_code` controls which records may share a chain.
- `AssessmentTemplateVersion` owns one immutable version, publication state, effective interval, service scope, scoring method, total range, comparison group, and publication evidence.
- `AssessmentTemplateSection` and `AssessmentTemplateField` define ordered structural content. A field is a label and response contract, not a licensed question.
- `AssessmentScoreBand` defines a derived classification with an inclusive lower and upper bound.
- `AssessmentResponse` stores a typed response and one of Assessed, Not Assessed, or Not Applicable.
- `Assessment` stores the selected version, event-time enrollment and center, chain identity, primary and additional responsible specialists, notes, recommendations, next-review date, calculation trace, and derived result.

Supported field response types are numeric score, percentage, assessed or not assessed, choice, scored choice, text, and not applicable. Scored choices contain immutable bilingual descriptions and point values. The server validates the selected value and derives its points; a supplied numeric value must match. Numeric and percentage fields may independently permit Not Assessed or Not Applicable. A response in either excluded state cannot carry a value.

## Publication and immutability

Draft versions may be edited. Publication validates every field and the instrument-specific scoring configuration. Published versions and every version referenced by an assessment are locked. Model validation, deletion protection, and service-scope change protection cover the template, sections, fields, score bands, and applicable-service relationships.

A published version may be withdrawn from future selection. Withdrawal does not change historical rendering or calculation. It cannot return to draft. A scoring or structural change requires another version.

## Calculation rules

All new totals, classifications, and delayed-domain counts are calculated by `apps.casework.assessment_engine`. The assessment form does not accept a manual total.

- Sum adds only assessed numeric responses whose versioned field has `include_in_total` enabled.
- Average uses the same included response set and returns zero when that set is empty.
- No total returns zero while still validating and retaining responses.
- A delayed domain counts only when it is Assessed, has a numeric value, and matches its configured threshold and operator.
- Not Assessed and Not Applicable responses never enter totals or delayed-domain counts.
- The calculation trace stores field codes, response states, included values, the template version, the scoring method, classification, and delayed count. It contains no beneficiary narrative.

## Barthel boundary rules

Barthel templates must define an explicit minimum, maximum, and positive score increment. Every classification band uses inclusive bounds. The first lower bound must equal the template minimum. Each later lower bound must equal the prior upper bound plus the configured increment. The last upper bound must equal the template maximum.

Publication rejects:

- a missing band;
- a gap;
- an overlap or duplicate boundary;
- an upper bound below its lower bound;
- a first or last bound that does not cover the configured score range.

The approved template has ten required activities: feeding, bathing, personal hygiene, dressing, bowel control, bladder control, toilet use, bed/chair transfers, mobility, and stairs. Each offers the supplied scored choices, including explicit zero-point answers. No answer is preselected. The maximum total is 100, and reachable totals are multiples of five.

The owner confirmed these inclusive bands, superseding the incomplete screenshot categories:

| Barthel score | Functional dependency | Care need |
| --- | --- | --- |
| 0 to 20 | Total | Very high |
| 21 to 60 | Severe | High |
| 61 to 90 | Moderate | Moderate |
| 91 to 99 | Slight | Low |
| 100 | Independent | Minimal |

For example, 55/100 produces Severe dependency and High care need. The creation form previews the result after all ten answers; the server independently recalculates it. Both levels are saved as separate fields with the total and calculation trace. The old structural draft is retained unchanged.

The form, signing review, detail page, and retained document explain that Barthel alone does not determine home-care visit frequency or intensity. An additional care needs narrative records medication, meal preparation, shopping, housework, and social support needs. The application does not infer visits, schedules, or a service plan from the score.

## Creation and signature

The template selector shows the template name. The version identifier is retained internally for reproducibility and is absent from the creation UI. Enrollment choices show the beneficiary name, code, service, status, enrollment date, and completed age. The review records age on the assessment date; an unavailable birth date is shown as Age unknown.

New assessments created through the application save as drafts and continue to a review-and-sign page. A beneficiary or representative must review the responses, result, and narratives before signing. Staff recorder and signer are separate. Representatives must state their relationship. The same PNG validation and signature pad used for beneficiary consent are reused. A printable assessment and signed PDF upload provide a paper and keyboard alternative.

Signed tokens bind the reviewed content to the assessment, recorder, center, language, and a one-hour expiry. Changed reviews need fresh signatures. Duplicate submissions retain the existing execution record. Completion checks the stored signature snapshot against the current assessment review before saving the derived result.

`SignedAssessment` and its generated files are private and append-only, with model and database guards. Authorized assessment selectors control review, signing, printing, and downloads. Generated evidence is excluded from ordinary attachment upload/delete routes. File writes and completion share rollback cleanup. Stored HTML embeds the local Georgian font and the normalized drawing, escapes text, and uses a restrictive content security policy. Paper evidence is retained with its hash.

Existing completed assessments remain unchanged and are not marked signed. A signed assessment's narratives and identity cannot be edited in place. An audited correction receives a new draft and requires a fresh signature before superseding the prior completed revision.

## AEPS and early-intervention structure

Old AEPS and new AEPS have separate stable identifiers and separate draft versions. They are not comparable by default. Both draft structures contain only the supplied early-intervention domains:

- gross motor;
- fine motor;
- adaptive;
- cognitive;
- social communication;
- social-emotional;
- school readiness;
- literacy;
- mathematics.

The drafts permit percentage, Not Assessed, and Not Applicable states. No delay threshold, formula, proprietary question, or clinical classification is published because SSK has not supplied that approved meaning. An owner must configure those rules before publication.

## Chains, backdating, and comparisons

Chains are separate per enrollment and instrument lineage. An Initial record starts sequence 1. A Repeated or Final record must identify the prior compatible record and receives the next sequence. A Final record closes the chain. Another Initial record may start a new numbered chain only after closure.

The predecessor date cannot be later than the new record. Chain order comes from explicit links and sequence values, so creation timestamps do not silently reorder a backdated assessment. A predecessor may have only one ordinary successor.

Records under the same template version are comparable. Different versions are comparable only when their instrument lineage and nonblank `comparison_group` match. Old AEPS and new AEPS do not receive a shared comparison group. Comparisons show derived total change, delayed-domain change, and changes for matching assessed numeric field codes.

## Completion, correction, and deletion

Responses remain editable while an assessment is Draft. Completion validates the whole response set, adds the primary specialist to the responsible-specialist set, calculates every result, and locks responses and assessment identity.

A completed assessment cannot be hard-deleted. `correct_assessment` applies the existing center and enrollment assignment authorization policy and requires a reason and actor. A signed correction remains a draft until its fresh signature is recorded; unsigned historical corrections retain the existing completion path. The prior revision becomes Superseded only when the correction completes and retains its responses and results. Routine updates to unsigned historical records may change narrative review details, but cannot change completed identity, template, chain, or calculation. Signed records require a new signed correction.

## Authorization

Assessment lists, detail views, forms, corrections, reports, exports, timelines, and attachments begin with the existing authorized enrollment and assessment selectors. Creation and change validation repeat event-date center placement and specialist assignment checks. Template selection is limited to a published version that is effective on the assessment date and enabled for the enrollment service. Additional responsible specialists use the same event-date assignment queryset.

## Legacy migration

Migration `0009_versioned_assessment_engine` provides the compatibility path:

1. Create stable instrument identifiers and one locked migration-only legacy version per old scoring tool.
2. Link every existing `Assessment` to the matching legacy version without changing its UUID, enrollment, dates, predecessor, narrative, or stored total.
3. Copy the historical total into a typed `LEGACY_TOTAL` response so historical reporting derives the preserved value from a response.
4. Mark the record Completed, retain its calculation trace, and add its existing specialist as responsible.
5. Keep every `AssessmentDomainScore` row and value unchanged. Mark it Review Required rather than guessing a semantic mapping.
6. Make the version foreign key required only after every record is linked.

The reverse migration first makes the version link nullable, removes only the generated response and responsibility rows, and clears the new link before dropping the engine tables. Migration tests verify exact preservation of the assessment total and free-text domain values.
