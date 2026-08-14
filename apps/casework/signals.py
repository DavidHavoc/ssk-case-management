from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import PrivateAttachment, ServiceVisit
from .services import rebuild_monthly_summary


@receiver(pre_save, sender=ServiceVisit)
def remember_previous_visit_scope(sender, instance, **kwargs) -> None:
    instance._previous_summary_scope = None
    if instance.pk:
        instance._previous_summary_scope = (
            sender.objects.filter(pk=instance.pk)
            .values_list("specialist_id", "center_id", "visit_month")
            .first()
        )


@receiver(post_save, sender=ServiceVisit)
def rebuild_visit_summaries(sender, instance, **kwargs) -> None:
    current = (instance.specialist_id, instance.center_id, instance.visit_month)
    previous = getattr(instance, "_previous_summary_scope", None)
    scopes = {current}
    if previous:
        scopes.add(previous)
    for scope in sorted(scopes, key=lambda item: tuple(str(value) for value in item)):
        rebuild_monthly_summary(*scope)


@receiver(post_delete, sender=ServiceVisit)
def rebuild_deleted_visit_summary(sender, instance, **kwargs) -> None:
    rebuild_monthly_summary(instance.specialist_id, instance.center_id, instance.visit_month)


@receiver(post_delete, sender=PrivateAttachment)
def remove_private_file(sender, instance, **kwargs) -> None:
    if instance.file:
        storage = instance.file.storage
        name = instance.file.name
        transaction.on_commit(lambda: storage.delete(name))
