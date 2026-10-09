"""Small assisted handwritten signing workflow. No mutable document regeneration."""

import base64
import binascii
import hashlib
import io
import json
import uuid
import warnings
from functools import lru_cache

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from PIL import Image, ImageChops, UnidentifiedImageError

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.centers.models import Center
from apps.core.authorization import (
    beneficiaries_for_user,
    beneficiary_intake_capabilities,
    get_authorized_object,
)
from apps.core.forms import StyledForm

from .intake_schema import CONSENT_FIELDS, MEDIA_DECLARATION
from .models import AttachmentParentType, Beneficiary, BeneficiaryIntake, SignedConsent
from .private_attachments import signed_consent_attachments

TEMPLATE_VERSION = "SSK-CONSENT-1"
TOKEN_SALT = "casework.assisted-consent.v1"
TOKEN_MAX_AGE = 3600
MAX_SIGNATURE_BYTES = 128 * 1024
MAX_SIGNATURE_CHARACTERS = 4 * ((MAX_SIGNATURE_BYTES + 2) // 3) + 22
ROLE_CHOICES = (
    ("", gettext_lazy("Select signer role")),
    ("beneficiary", gettext_lazy("Beneficiary")),
    ("guardian", gettext_lazy("Guardian")),
    ("parent", gettext_lazy("Parent")),
    ("supporter", gettext_lazy("Supporter")),
    ("representative", gettext_lazy("Representative")),
)
DOCUMENT_CSP = (
    "default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox allow-same-origin"
)


class StaleConsent(ValidationError):
    def __init__(self):
        super().__init__(
            _(
                "The consent review has changed or expired. Review the updated document and "
                "draw a fresh signature."
            )
        )


def validate_signature(value):
    """Bound before decoding, verify PNG, flatten transparency, strip all metadata."""
    invalid = _("Draw a visible signature using the pad. Only a valid, non-empty PNG is accepted.")
    if not isinstance(value, str) or len(value) > MAX_SIGNATURE_CHARACTERS:
        raise ValidationError(_("The signature image is too large."))
    if not value.startswith("data:image/png;base64,"):
        raise ValidationError(invalid)
    try:
        raw = base64.b64decode(value.split(",", 1)[1], validate=True)
        if len(raw) > MAX_SIGNATURE_BYTES:
            raise ValidationError(_("The signature image is too large."))
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=["PNG"]) as image:
                width, height = image.size
                if not (200 <= width <= 1400 and 80 <= height <= 600) or image.is_animated:
                    raise ValidationError(_("The signature image dimensions are not allowed."))
                image.verify()
            with Image.open(io.BytesIO(raw), formats=["PNG"]) as image:
                image.load()
                rgba = image.convert("RGBA")
                flattened = Image.new("RGBA", rgba.size, "white")
                flattened.alpha_composite(rgba)
                rgb = flattened.convert("RGB")
        ink = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert("L")
        mask = ink.point(lambda pixel: 255 if pixel > 40 else 0)
        bounds = mask.getbbox()
        count = mask.histogram()[255]
        if (
            not bounds
            or count < 20
            or count > width * height // 2
            or bounds[2] - bounds[0] < 10
            or bounds[3] - bounds[1] < 5
        ):
            raise ValidationError(invalid)
        normalized = io.BytesIO()
        rgb.save(normalized, format="PNG")
        if normalized.tell() > MAX_SIGNATURE_BYTES:
            raise ValidationError(_("The signature image is too large."))
        return normalized.getvalue()
    except (
        ValueError,
        binascii.Error,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError(invalid) from exc


class ConsentSigningForm(StyledForm):
    review_token = forms.CharField(
        label=gettext_lazy("Consent review"), max_length=1024, widget=forms.HiddenInput
    )
    signer_name = forms.CharField(label=gettext_lazy("Signer full name"), max_length=240)
    signer_role = forms.ChoiceField(label=gettext_lazy("Signer role"), choices=ROLE_CHOICES)
    relationship = forms.CharField(
        label=gettext_lazy("Stated relationship to the beneficiary"),
        max_length=240,
        required=False,
        help_text=gettext_lazy(
            "Required for a guardian, parent, supporter, or representative. This records a "
            "stated relationship and does not verify legal authority."
        ),
    )
    signature_data = forms.CharField(
        label=gettext_lazy("Handwritten signature"),
        widget=forms.HiddenInput,
        max_length=MAX_SIGNATURE_CHARACTERS,
    )
    reviewed = forms.BooleanField(
        label=gettext_lazy(
            "The signer has reviewed these recorded decisions and requests that this "
            "signature be saved."
        ),
        required=True,
    )

    def clean_signature_data(self):
        return validate_signature(self.cleaned_data["signature_data"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("signer_role") == "beneficiary":
            cleaned["relationship"] = ""
        elif cleaned.get("signer_role") and not cleaned.get("relationship"):
            self.add_error("relationship", _("Please record the signer's stated relationship."))
        return cleaned


def authorized_consent_beneficiary(pk, user, center):
    person = get_authorized_object(beneficiaries_for_user(user, center), pk)
    if not beneficiary_intake_capabilities(user, center, person)["consent"]:
        raise Http404
    return person


def authorized_signed_consent(pk, user, center):
    record = get_authorized_object(SignedConsent.objects.filter(center=center), pk)
    authorized_consent_beneficiary(record.beneficiary_id, user, center)
    return record


def consent_review(person, language):
    """Every displayed term and decision is serialized in the language being reviewed."""
    if language not in {"en", "ka"}:
        language = "en"
    values = (
        BeneficiaryIntake.objects.filter(beneficiary=person).values(*CONSENT_FIELDS).first() or {}
    )
    with translation.override(language):
        decisions = []
        for name in CONSENT_FIELDS:
            field = BeneficiaryIntake._meta.get_field(name)
            value = values.get(name, "")
            label = str(dict(field.choices).get(value)) if value else _("Not recorded")
            decisions.append(
                {"field": name, "wording": str(field.verbose_name), "value": value, "answer": label}
            )
        return {
            "template_version": TEMPLATE_VERSION,
            "language": language,
            "beneficiary": {"name": person.full_name, "code": person.beneficiary_code},
            "decisions": decisions,
            "media": [str(text) for text in MEDIA_DECLARATION],
            "notice": _(
                "A handwritten signature records the decisions shown, including refusals "
                "and items not recorded. The staff recorder is separate from the signer."
            ),
            "authority_notice": _(
                "The signer role and relationship are stated information. They do not "
                "verify identity or legal authority."
            ),
            "labels": {
                "title": _("SSK consent form"),
                "beneficiary": _("Beneficiary"),
                "code": _("Beneficiary code"),
                "version": _("Document version"),
                "language": _("Language"),
                "media": _("Media declaration"),
                "signer": _("Signer full name"),
                "role": _("Signer role"),
                "relationship": _("Stated relationship to the beneficiary"),
                "timestamp": _("Signed at (UTC)"),
                "recorder": _("Recorded by staff"),
                "signature": _("Handwritten signature"),
                "unsigned": _("Unsigned printable copy. Printing does not create a signed record."),
                "paper": _(
                    "For paper signing, write the signer name, role, relationship, date, "
                    "and signature below. An authorized staff member can upload the "
                    "completed paper form as a beneficiary document."
                ),
                "font_license": _("Embedded font: Noto Sans Georgian, SIL Open Font License 1.1."),
            },
        }


def review_fingerprint(person, review):
    # A conservative revision marker detects even an answer changed and then restored.
    intake = BeneficiaryIntake.objects.filter(beneficiary=person).values("updated_at").first()
    state = {"review": review, "intake_updated": str(intake["updated_at"]) if intake else None}
    return hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def issue_review_token(person, actor, center, review):
    return signing.dumps(
        {
            "beneficiary": str(person.pk),
            "actor": str(actor.pk),
            "center": str(center.pk),
            "language": review["language"],
            "fingerprint": review_fingerprint(person, review),
            "submission": str(uuid.uuid4()),
        },
        salt=TOKEN_SALT,
    )


def check_review_token(token, person, actor, center, language):
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        if (data["beneficiary"], data["actor"], data["center"], data["language"]) != (
            str(person.pk),
            str(actor.pk),
            str(center.pk),
            language,
        ):
            raise StaleConsent
        uuid.UUID(data["submission"])
        return data
    except (signing.BadSignature, KeyError, ValueError, TypeError) as exc:
        raise StaleConsent from exc


@lru_cache(maxsize=1)
def embedded_font():
    return base64.b64encode(
        (settings.BASE_DIR / "static/fonts/NotoSansGeorgian.ttf").read_bytes()
    ).decode("ascii")


def document_html(snapshot, signature=None):
    # Only the trusted local font and normalized PNG become data URLs. Text is autoescaped.
    return render_to_string(
        "casework/consent_artifact.html",
        {
            "document": snapshot,
            "font_data": embedded_font(),
            "signature": base64.b64encode(signature).decode("ascii") if signature else "",
            "csp": DOCUMENT_CSP,
            "font_license": (settings.BASE_DIR / "static/fonts/OFL-NotoSansGeorgian.txt").read_text(
                encoding="utf-8"
            ),
        },
    )


def finalize_consent(*, person, actor, center, language, values):
    files = signed_consent_attachments(actor, center)
    # The upload context owns rollback cleanup, including failures after both file writes.
    with files.atomic_uploads() as uploader:
        person = Beneficiary.objects.select_for_update().get(pk=person.pk)
        actor = get_user_model().objects.get(pk=actor.pk)
        center = Center.objects.get(pk=center.pk)
        person = authorized_consent_beneficiary(person.pk, actor, center)
        data = check_review_token(values["review_token"], person, actor, center, language)
        existing = SignedConsent.objects.filter(submission_id=data["submission"]).first()
        if existing:
            return authorized_signed_consent(existing.pk, actor, center)
        review = consent_review(person, language)
        if review_fingerprint(person, review) != data["fingerprint"]:
            raise StaleConsent
        signature = (
            validate_signature(values["signature_data"])
            if isinstance(values["signature_data"], str)
            else values["signature_data"]
        )
        # Callers use the form, but the write boundary also validates signer fields and PNG.
        signature = validate_signature(
            "data:image/png;base64," + base64.b64encode(signature).decode("ascii")
        )
        form = ConsentSigningForm(
            {
                **values,
                "signature_data": "data:image/png;base64,"
                + base64.b64encode(signature).decode("ascii"),
            }
        )
        if not form.is_valid():
            raise ValidationError(form.errors)
        signed_at = timezone.now()
        with translation.override(language):
            role_label = str(dict(ROLE_CHOICES)[form.cleaned_data["signer_role"]])
        review["execution"] = {
            "signer_name": form.cleaned_data["signer_name"],
            "role": form.cleaned_data["signer_role"],
            "role_label": role_label,
            "relationship": form.cleaned_data["relationship"],
            "timestamp": signed_at.isoformat(),
            "recorder": actor.get_full_name() or actor.username,
            "recorder_id": str(actor.pk),
        }
        record = SignedConsent.objects.create(
            beneficiary=person,
            center=center,
            recorded_by=actor,
            signed_at=signed_at,
            language=language,
            template_version=TEMPLATE_VERSION,
            submission_id=data["submission"],
            snapshot=review,
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_CONSENT,
            parent=record,
            upload=ContentFile(signature, name="signature.png"),
        )
        uploader.create(
            parent_type=AttachmentParentType.SIGNED_CONSENT,
            parent=record,
            upload=ContentFile(
                document_html(review, signature).encode("utf-8"), name="signed-consent.txt"
            ),
        )
        record_event(
            actor=actor,
            center=center,
            event_type=AuditEvent.EventType.CREATE,
            target_type="SignedConsent",
            target_id=record.pk,
        )
        return record


def signed_consent_status(person, actor, center):
    if not beneficiary_intake_capabilities(actor, center, person)["consent"]:
        return {}
    records = SignedConsent.objects.filter(beneficiary=person, center=center)
    latest = records.first()
    current = consent_review(person, latest.language if latest else "en")
    return {
        "can_sign_consent": True,
        "signed_consents": records,
        "consent_decisions_differ": bool(
            latest and latest.snapshot["decisions"] != current["decisions"]
        ),
    }
