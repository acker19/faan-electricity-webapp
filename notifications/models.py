import uuid
from django.db import models


class NotificationDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recharge = models.ForeignKey("recharge.RechargeRequest", on_delete=models.PROTECT)
    channel = models.CharField(max_length=20, default="sms")
    destination = models.CharField(max_length=32)
    provider_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)
