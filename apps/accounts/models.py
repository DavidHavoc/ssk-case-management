from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Language(models.TextChoices):
        ENGLISH = "en", _("English")
        GEORGIAN = "ka", _("Georgian")

    preferred_language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.ENGLISH
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="unique_nonblank_user_email_ci",
            )
        ]


class LoginThrottle(models.Model):
    key_hash = models.CharField(max_length=64, unique=True)
    failure_count = models.PositiveSmallIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def hash_key(cls, category: str, value: str) -> str:
        message = f"{category}:{value.strip().lower()}".encode()
        return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()

    @classmethod
    def is_blocked(cls, keys: list[str]) -> bool:
        cutoff = timezone.now() - timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        return cls.objects.filter(
            key_hash__in=keys,
            window_started__gte=cutoff,
            failure_count__gte=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        ).exists()

    @classmethod
    def register_failure(cls, keys: list[str]) -> None:
        now = timezone.now()
        cutoff = now - timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        with transaction.atomic():
            for key in keys:
                row, _ = cls.objects.select_for_update().get_or_create(key_hash=key)
                if row.window_started < cutoff:
                    row.window_started = now
                    row.failure_count = 1
                else:
                    row.failure_count += 1
                row.save(update_fields=["window_started", "failure_count", "updated_at"])

    @classmethod
    def clear(cls, keys: list[str]) -> None:
        cls.objects.filter(key_hash__in=keys).delete()
