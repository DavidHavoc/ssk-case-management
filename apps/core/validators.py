from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

phone_number_validator = RegexValidator(
    regex=r"^\+?[0-9][0-9() .-]{4,39}$",
    message=_("Enter a valid phone number."),
)
