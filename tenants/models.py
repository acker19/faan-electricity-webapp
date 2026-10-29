import uuid
from django.conf import settings
from django.db import models

class Tenant(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tenant_profile",
    )
    meter_number = models.CharField(max_length=32, unique=True, db_index=True)
    registered_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(max_length=12, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True)
    verified_by = models.ForeignKey(
        "accounts.StaffUser", null=True, blank=True, on_delete=models.SET_NULL
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.registered_name} ({self.meter_number})"


class PhoneOTP(models.Model):
    """Store short-lived OTPs for phone verification in the MVP.
    Production should use a dedicated OTP provider or cache with expiry.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at
