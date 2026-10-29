import uuid
from django.db import models
from tenants.models import Tenant

class RechargeRequest(models.Model):
    class PaymentStatus(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    class TokenStatus(models.TextChoices):
        NOT_APPLICABLE = "n_a", "N/A"
        AWAITING_GENERATION = "awaiting_generation", "Awaiting generation"
        FULFILLED = "fulfilled", "Fulfilled"
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="recharge_requests")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=100, unique=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.AWAITING_PAYMENT)
    paid_at = models.DateTimeField(null=True, blank=True)
    remita_rrr = models.CharField(max_length=32, blank=True)
    token_status = models.CharField(max_length=24, choices=TokenStatus.choices, default=TokenStatus.NOT_APPLICABLE)
    token_source = models.CharField(max_length=10, blank=True)
    token_value_encrypted = models.BinaryField(null=True, blank=True)
    token_generated_by = models.ForeignKey(
        "accounts.StaffUser", null=True, blank=True, on_delete=models.SET_NULL
    )
    token_generated_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["payment_status", "token_status"])]

    def mark_paid(self):
        if self.payment_status != self.PaymentStatus.AWAITING_PAYMENT:
            raise ValueError("Only awaiting-payment requests can be marked paid.")
        self.payment_status = self.PaymentStatus.PAID
        self.token_status = self.TokenStatus.AWAITING_GENERATION
        from django.utils import timezone
        self.paid_at = timezone.now()

    def attach_token(self, encrypted_token: bytes, source: str):
        if self.payment_status != self.PaymentStatus.PAID:
            raise ValueError("Only paid requests can receive a token.")
        if self.token_status != self.TokenStatus.AWAITING_GENERATION:
            raise ValueError("This request is not awaiting token generation.")
        self.token_value_encrypted = encrypted_token
        self.token_source = source
        self.token_status = self.TokenStatus.FULFILLED

    def attach_token(self, encrypted_token: bytes, source: str):
        if self.payment_status != self.PaymentStatus.PAID:
            raise ValueError("Only paid requests can receive a token.")
        if self.token_status != self.TokenStatus.AWAITING_GENERATION:
            raise ValueError("This request is not awaiting token generation.")
        self.token_value_encrypted = encrypted_token
        self.token_source = source
        self.token_status = self.TokenStatus.FULFILLED
