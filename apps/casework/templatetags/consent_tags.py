from django import template

from apps.casework.intake_schema import MEDIA_DECLARATION

register = template.Library()


@register.simple_tag
def consent_media_wording():
    return [str(text) for text in MEDIA_DECLARATION]
