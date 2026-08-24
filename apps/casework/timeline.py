from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.core.paginator import Page, Paginator
from django.db.models import (
    CharField,
    DateField,
    F,
    IntegerField,
    QuerySet,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from apps.core.authorization import assessments_for_user, plans_for_user, visits_for_user

from .models import (
    Assessment,
    AttachmentParentType,
    Beneficiary,
    IndividualPlan,
    IndividualPlanGoal,
    ServiceEnrollment,
    ServiceVisit,
)
from .private_attachments import case_attachments

TIMELINE_PAGE_SIZE = 20

SERVICE_VISIT = "service_visit"
ASSESSMENT = "assessment"
INDIVIDUAL_PLAN = "individual_plan"
PLAN_GOAL = "plan_goal"
ATTACHMENT = "attachment"

_TYPE_RANK = {
    SERVICE_VISIT: 10,
    ASSESSMENT: 20,
    INDIVIDUAL_PLAN: 30,
    PLAN_GOAL: 40,
    ATTACHMENT: 50,
}


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    entry_type: str
    type_label: str
    display_date: date | datetime
    title: str
    summary: str
    status: str
    status_key: str
    detail_url: str
    download_url: str | None
    stable_identifier: str


@dataclass(frozen=True, slots=True)
class _TimelineScopes:
    visits: QuerySet
    assessments: QuerySet
    plans: QuerySet
    goals: QuerySet
    attachments: QuerySet


def _choice_label(choices, value: str) -> str:
    return force_str(dict(choices).get(value, value))


def _short_text(value: str, limit: int = 180) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _index_values(
    queryset: QuerySet,
    *,
    entry_type: str,
    activity_date,
    record_id="pk",
    created_at="created_at",
):
    return (
        queryset.order_by()
        .annotate(
            timeline_type=Value(entry_type, output_field=CharField()),
            timeline_rank=Value(_TYPE_RANK[entry_type], output_field=IntegerField()),
            timeline_id=F(record_id),
            timeline_date=activity_date,
            timeline_created_at=F(created_at),
        )
        .values(
            "timeline_type",
            "timeline_rank",
            "timeline_id",
            "timeline_date",
            "timeline_created_at",
        )
    )


def _timeline_scopes(
    *, user, center, beneficiary: Beneficiary, enrollment: ServiceEnrollment
) -> _TimelineScopes:
    visits = visits_for_user(user, center).filter(beneficiary=beneficiary, enrollment=enrollment)
    assessments = assessments_for_user(user, center).filter(
        beneficiary=beneficiary, enrollment=enrollment
    )
    plans = plans_for_user(user, center).filter(beneficiary=beneficiary, enrollment=enrollment)
    goals = IndividualPlanGoal.objects.filter(plan__in=plans.order_by())
    attachments = case_attachments(user, center).timeline_for_beneficiary(beneficiary, enrollment)
    return _TimelineScopes(
        visits=visits,
        assessments=assessments,
        plans=plans,
        goals=goals,
        attachments=attachments,
    )


def _timeline_index(scopes: _TimelineScopes):

    sources = (
        _index_values(
            scopes.visits,
            entry_type=SERVICE_VISIT,
            activity_date=F("visit_date"),
        ),
        _index_values(
            scopes.assessments,
            entry_type=ASSESSMENT,
            activity_date=F("assessment_date"),
        ),
        _index_values(
            scopes.plans,
            entry_type=INDIVIDUAL_PLAN,
            activity_date=F("plan_start_date"),
        ),
        _index_values(
            scopes.goals,
            entry_type=PLAN_GOAL,
            activity_date=Coalesce(
                "target_date",
                "plan__plan_start_date",
                output_field=DateField(),
            ),
        ),
        _index_values(
            scopes.attachments,
            entry_type=ATTACHMENT,
            activity_date=TruncDate("created_at"),
        ),
    )
    return (
        sources[0]
        .union(*sources[1:], all=True)
        .order_by(
            "-timeline_date",
            "-timeline_created_at",
            "timeline_rank",
            "timeline_id",
        )
    )


def _visit_entries(queryset: QuerySet, ids) -> dict[str, TimelineEntry]:
    entries = {}
    rows = queryset.filter(pk__in=ids).values(
        "pk",
        "visit_date",
        "activity__name_en",
        "activity__name_ka",
        "status",
        "duration_minutes",
    )
    for row in rows:
        language = (get_language() or "en").split("-", maxsplit=1)[0]
        activity = row["activity__name_ka"] if language == "ka" else row["activity__name_en"]
        entries[str(row["pk"])] = TimelineEntry(
            entry_type=SERVICE_VISIT,
            type_label=force_str(_("Service Visit")),
            display_date=row["visit_date"],
            title=activity,
            summary=force_str(_("%(minutes)s minutes")) % {"minutes": row["duration_minutes"]},
            status=_choice_label(ServiceVisit.Status.choices, row["status"]),
            status_key=row["status"],
            detail_url=reverse("visit_detail", kwargs={"pk": row["pk"]}),
            download_url=None,
            stable_identifier=f"{SERVICE_VISIT}:{row['pk']}",
        )
    return entries


def _assessment_entries(queryset: QuerySet, ids) -> dict[str, TimelineEntry]:
    entries = {}
    rows = queryset.filter(pk__in=ids).values(
        "pk",
        "assessment_date",
        "assessment_type",
        "template_version__instrument__name",
        "template_version__version",
    )
    for row in rows:
        entries[str(row["pk"])] = TimelineEntry(
            entry_type=ASSESSMENT,
            type_label=force_str(_("Assessment")),
            display_date=row["assessment_date"],
            title=_choice_label(Assessment.AssessmentType.choices, row["assessment_type"]),
            summary=force_str(_("Instrument: %(instrument)s, version %(version)s"))
            % {
                "instrument": row["template_version__instrument__name"],
                "version": row["template_version__version"],
            },
            status="",
            status_key="",
            detail_url=reverse("assessment_detail", kwargs={"pk": row["pk"]}),
            download_url=None,
            stable_identifier=f"{ASSESSMENT}:{row['pk']}",
        )
    return entries


def _plan_entries(queryset: QuerySet, ids) -> dict[str, TimelineEntry]:
    entries = {}
    rows = queryset.filter(pk__in=ids).values("pk", "plan_start_date", "status", "review_frequency")
    for row in rows:
        review = _choice_label(IndividualPlan.ReviewFrequency.choices, row["review_frequency"])
        summary = (
            force_str(_("Review frequency: %(frequency)s")) % {"frequency": review}
            if review
            else force_str(_("Review frequency not set"))
        )
        entries[str(row["pk"])] = TimelineEntry(
            entry_type=INDIVIDUAL_PLAN,
            type_label=force_str(_("Individual Plan")),
            display_date=row["plan_start_date"],
            title=force_str(_("Individual plan")),
            summary=summary,
            status=_choice_label(IndividualPlan.Status.choices, row["status"]),
            status_key=row["status"],
            detail_url=reverse("plan_detail", kwargs={"pk": row["pk"]}),
            download_url=None,
            stable_identifier=f"{INDIVIDUAL_PLAN}:{row['pk']}",
        )
    return entries


def _goal_entries(queryset: QuerySet, ids) -> dict[str, TimelineEntry]:
    entries = {}
    rows = queryset.filter(pk__in=ids).values(
        "pk", "plan_id", "target_date", "plan__plan_start_date", "goal", "status"
    )
    for row in rows:
        entries[str(row["pk"])] = TimelineEntry(
            entry_type=PLAN_GOAL,
            type_label=force_str(_("Plan Goal")),
            display_date=row["target_date"] or row["plan__plan_start_date"],
            title=force_str(_("Plan goal")),
            summary=_short_text(row["goal"]),
            status=_choice_label(IndividualPlanGoal.Status.choices, row["status"]),
            status_key=row["status"],
            detail_url=(reverse("plan_detail", kwargs={"pk": row["plan_id"]}) + "#goals-heading"),
            download_url=None,
            stable_identifier=f"{PLAN_GOAL}:{row['pk']}",
        )
    return entries


def _attachment_parent_label(parent_type: str) -> str:
    labels = {
        AttachmentParentType.BENEFICIARY: _("Beneficiary"),
        AttachmentParentType.SERVICE_VISIT: _("Service Visit"),
        AttachmentParentType.ASSESSMENT: _("Assessment"),
        AttachmentParentType.INDIVIDUAL_PLAN: _("Individual Plan"),
    }
    return force_str(labels[parent_type])


def _attachment_detail_url(parent_type: str, parent_id) -> str:
    route = {
        AttachmentParentType.BENEFICIARY: "beneficiary_detail",
        AttachmentParentType.SERVICE_VISIT: "visit_detail",
        AttachmentParentType.ASSESSMENT: "assessment_detail",
        AttachmentParentType.INDIVIDUAL_PLAN: "plan_detail",
    }[parent_type]
    return reverse(route, kwargs={"pk": parent_id})


def _attachment_entries(queryset: QuerySet, ids) -> dict[str, TimelineEntry]:
    entries = {}
    rows = queryset.filter(pk__in=ids).values(
        "pk", "parent_type", "parent_id", "created_at", "original_filename"
    )
    for row in rows:
        entries[str(row["pk"])] = TimelineEntry(
            entry_type=ATTACHMENT,
            type_label=force_str(_("Attachment")),
            display_date=row["created_at"],
            title=row["original_filename"],
            summary=force_str(_("Attached to %(record_type)s"))
            % {"record_type": _attachment_parent_label(row["parent_type"])},
            status="",
            status_key="",
            detail_url=_attachment_detail_url(row["parent_type"], row["parent_id"]),
            download_url=reverse("attachment_download", kwargs={"pk": row["pk"]}),
            stable_identifier=f"{ATTACHMENT}:{row['pk']}",
        )
    return entries


def _normalize_page(rows, scopes: _TimelineScopes) -> list[TimelineEntry]:
    ids_by_type = {entry_type: [] for entry_type in _TYPE_RANK}
    for row in rows:
        ids_by_type[row["timeline_type"]].append(row["timeline_id"])

    loaders = {
        SERVICE_VISIT: (_visit_entries, scopes.visits),
        ASSESSMENT: (_assessment_entries, scopes.assessments),
        INDIVIDUAL_PLAN: (_plan_entries, scopes.plans),
        PLAN_GOAL: (_goal_entries, scopes.goals),
        ATTACHMENT: (_attachment_entries, scopes.attachments),
    }
    entries_by_type = {
        entry_type: loaders[entry_type][0](loaders[entry_type][1], ids)
        for entry_type, ids in ids_by_type.items()
        if ids
    }
    return [entries_by_type[row["timeline_type"]][str(row["timeline_id"])] for row in rows]


def beneficiary_timeline_page(
    *,
    user,
    center,
    beneficiary: Beneficiary,
    enrollment: ServiceEnrollment,
    page_number,
    per_page: int = TIMELINE_PAGE_SIZE,
) -> Page:
    scopes = _timeline_scopes(
        user=user,
        center=center,
        beneficiary=beneficiary,
        enrollment=enrollment,
    )
    paginator = Paginator(
        _timeline_index(scopes),
        per_page,
    )
    page_obj = paginator.get_page(page_number)
    page_obj.object_list = _normalize_page(list(page_obj.object_list), scopes)
    return page_obj
