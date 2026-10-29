from django.db.models.signals import post_save
from django.dispatch import receiver

from audit.services import record_audit
from .models import WebhookEvent


@receiver(post_save, sender=WebhookEvent)
def audit_webhook_received(sender, instance, created, **kwargs):
    if created:
        record_audit(
            "system",
            "payment.webhook_received",
            instance.id,
            {"signature_valid": instance.signature_valid},
        )
