# Versioned Assessment Engine

## Scope and evidence boundary

The assessment engine implements the SSK structural requirements without copying or inferring proprietary assessment questions. The seeded Barthel and AEPS examples contain only identifiers, domain names, response structure, and provisional neutral scoring bands already present in the approved repository requirements. They remain drafts and cannot be selected for a new assessment until an authorized owner supplies and approves the missing clinical meaning.

## Domain model

- `AssessmentInstrument` is the stable tool identity. Seeded identifiers are Barthel, old AEPS, new AEPS, ICF-based, and Other. `lineage_code` controls which records may share a chain.
- `AssessmentTemplateVersion` owns one immutable version, publication state, effective interval, service scope, scoring method, total range, comparison group, and publication evidence.
- `AssessmentTemplateSection` and `AssessmentTemplateField` define ordered structural content. A field is a label and response contract, not a licensed question.
- `AssessmentScoreBand` defines a derived classification with an inclusive lower and upper bound.
- `AssessmentResponse` stores a typed response and one of Assessed, Not Assessed, or Not Applicable.
- `Assessment` stores the selected version, event-time enrollment and center, chain identity, primary and additional responsible specialists, notes, recommendations, next-review date, calculation trace, and derived result.

Supported field response types are numeric score, percentage, assessed or not assessed, choice, text, and not applicable. Numeric and percentage fields may independently permit Not Assessed or Not Applicable. A response in either excluded state cannot carry a value.

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

The seeded structural draft uses an integer increment and neutral ranges 0 through 65, 66 through 75, 76 through 95, and 96 through 100. Both ends of every range are inclusive. Its labels are deliberately non-clinical, and the version remains Draft pending the owner approval identified by D-015. Tests verify every lower and upper boundary.

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

A completed assessment cannot be hard-deleted. `correct_assessment` applies the existing center and enrollment assignment authorization policy and creates a new completed revision with a required reason and actor. The prior revision becomes Superseded but retains its responses and results. Routine updates may change narrative review details, but cannot change the completed identity, template, chain, or calculation.

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
