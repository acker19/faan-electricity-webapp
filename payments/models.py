import uuid
from django.db import models
from audit.services import record_audit

class WebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signature_valid = models.BooleanField()
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    provider_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def mark_received(self):
        record_audit(
            "system",
            "payment.webhook_received",
            self.id,
            {"signature_valid": self.signature_valid},
        )
