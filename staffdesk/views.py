from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Max, Q, Sum, ExpressionWrapper, DurationField

from tenants.models import Tenant
from recharge.models import RechargeRequest
from accounts.models import StaffUser
from audit.models import AuditLogEntry
from notifications.models import NotificationDelivery
from notifications.providers import get_token_provider as get_notification_token_provider
from tokens.crypto import encrypt_token
from tokens.providers import get_token_provider as get_token_generator
from audit.services import record_audit


def staff_required(user):
    return user.is_authenticated and user.is_staff


staff_only = user_passes_test(staff_required, login_url="/admin/login/")


@staff_only
def staff_dashboard(request):
    context = {
        "pending_approvals": Tenant.objects.filter(
            verification_status=Tenant.VerificationStatus.PENDING,
            phone_verified_at__isnull=False,
        ).count(),
        "awaiting_fulfilment": RechargeRequest.objects.filter(
            payment_status=RechargeRequest.PaymentStatus.PAID,
            token_status=RechargeRequest.TokenStatus.AWAITING_GENERATION,
        ).count(),
        "exceptions": RechargeRequest.objects.filter(
            payment_status__in=[
                RechargeRequest.PaymentStatus.FAILED,
                RechargeRequest.PaymentStatus.EXPIRED,
            ],
        ).count() + RechargeRequest.objects.filter(
            token_status=RechargeRequest.TokenStatus.DELIVERY_FAILED,
        ).count(),
        "approved_tenants": Tenant.objects.filter(
            verification_status=Tenant.VerificationStatus.APPROVED,
        ).count(),
        "recent_approvals": Tenant.objects.select_related("user").filter(
            verification_status=Tenant.VerificationStatus.PENDING,
            phone_verified_at__isnull=False,
        ).order_by("created_at")[:5],
        "recent_fulfilment": RechargeRequest.objects.select_related("tenant").filter(
            payment_status=RechargeRequest.PaymentStatus.PAID,
            token_status=RechargeRequest.TokenStatus.AWAITING_GENERATION,
        ).order_by("created_at")[:5],
    }
    return render(request, "staff-home.html", context)


@staff_only
def approval_queue(request):
    tenants = Tenant.objects.filter(
        verification_status=Tenant.VerificationStatus.PENDING,
        phone_verified_at__isnull=False,
    ).order_by("created_at")
    return render(request, "staff-dashboard.html", {"pending_tenants": tenants})


@staff_only
def approval_detail(request, tenant_id):
    tenant = get_object_or_404(Tenant.objects.select_related("user", "verified_by"), id=tenant_id)
    audit_history = AuditLogEntry.objects.filter(target=str(tenant.id))[:20]
    return render(request, "staff-approval-detail.html", {
        "tenant": tenant,
        "audit_history": audit_history,
    })


@staff_only
def approve_tenant(request, tenant_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Approval actions must use POST.")
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.verification_status = Tenant.VerificationStatus.APPROVED
    tenant.verified_at = timezone.now()
    tenant.verified_by = getattr(request.user, "staff_profile", None)
    tenant.save(update_fields=["verification_status", "verified_at", "verified_by", "updated_at"])
    record_audit(
        request.user,
        "tenant.approved",
        tenant.id,
        {"meter_number": tenant.meter_number},
    )
    return redirect("staff-approval-queue")


@staff_only
def reject_tenant(request, tenant_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Rejection actions must use POST.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A rejection reason is required.")
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.verification_status = Tenant.VerificationStatus.REJECTED
    tenant.rejection_reason = reason[:255]
    tenant.verified_by = getattr(request.user, "staff_profile", None)
    tenant.verified_at = timezone.now()
    tenant.save(update_fields=["verification_status", "rejection_reason", "verified_by", "verified_at", "updated_at"])
    record_audit(
        request.user,
        "tenant.rejected",
        tenant.id,
        {"reason": tenant.rejection_reason},
    )
    return redirect("staff-approval-queue")


@staff_only
def fulfilment_queue(request):
    requests = RechargeRequest.objects.select_related("tenant").filter(
        payment_status=RechargeRequest.PaymentStatus.PAID,
        token_status=RechargeRequest.TokenStatus.AWAITING_GENERATION,
    ).order_by("created_at")
    return render(request, "staff-transactions.html", {"recharge_requests": requests})


@staff_only
def exceptions_queue(request):
    requests = RechargeRequest.objects.select_related("tenant").filter(
        payment_status__in=[
            RechargeRequest.PaymentStatus.FAILED,
            RechargeRequest.PaymentStatus.EXPIRED,
        ],
    ).order_by("-updated_at")
    delivery_failures = RechargeRequest.objects.select_related("tenant").filter(
        token_status=RechargeRequest.TokenStatus.DELIVERY_FAILED,
    ).order_by("-updated_at")
    return render(request, "staff-exceptions.html", {
        "payment_exceptions": requests,
        "delivery_failures": delivery_failures,
    })


@staff_only
def transaction_detail(request, recharge_id):
    recharge = get_object_or_404(
        RechargeRequest.objects.select_related("tenant", "token_generated_by__user"),
        id=recharge_id,
    )
    return render(request, "staff-transaction-detail.html", {"recharge": recharge})


@staff_only
def staff_management(request):
    staff = StaffUser.objects.select_related("user").order_by("user__first_name", "user__username")
    return render(request, "admin-staff.html", {"staff_users": staff})


@staff_only
def audit_logs(request):
    logs = AuditLogEntry.objects.all()[:100]
    return render(request, "admin-audit.html", {"audit_logs": logs})


@staff_only
def reports(request):
    queryset = RechargeRequest.objects.all()
    payment_status = request.GET.get("payment_status", "").strip()
    token_status = request.GET.get("token_status", "").strip()
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    if token_status:
        queryset = queryset.filter(token_status=token_status)
    fulfilled = queryset.filter(token_generated_at__isnull=False, paid_at__isnull=False)
    delivery = queryset.filter(delivered_at__isnull=False, paid_at__isnull=False)
    fulfilment_duration = ExpressionWrapper(F("token_generated_at") - F("paid_at"), output_field=DurationField())
    delivery_duration = ExpressionWrapper(F("delivered_at") - F("paid_at"), output_field=DurationField())
    customer_summary = (
        queryset.filter(payment_status=RechargeRequest.PaymentStatus.PAID)
        .values(
            "tenant_id",
            "tenant__registered_name",
            "tenant__meter_number",
            "tenant__user__first_name",
            "tenant__user__email",
        )
        .annotate(
            purchase_count=Count("id"),
            total_amount=Sum("amount"),
            latest_purchase=Max("created_at"),
        )
        .order_by("-total_amount", "tenant__registered_name")
    )
    context = {
        "payment_status": payment_status,
        "token_status": token_status,
        "total_count": queryset.count(),
        "total_amount": queryset.aggregate(total=Sum("amount"))["total"] or 0,
        "paid_count": queryset.filter(payment_status=RechargeRequest.PaymentStatus.PAID).count(),
        "awaiting_count": queryset.filter(payment_status=RechargeRequest.PaymentStatus.AWAITING_PAYMENT).count(),
        "failed_count": queryset.filter(payment_status=RechargeRequest.PaymentStatus.FAILED).count(),
        "expired_count": queryset.filter(payment_status=RechargeRequest.PaymentStatus.EXPIRED).count(),
        "fulfilled_count": queryset.filter(token_status=RechargeRequest.TokenStatus.FULFILLED).count(),
        "delivery_failures": queryset.filter(token_status=RechargeRequest.TokenStatus.DELIVERY_FAILED).count(),
        "average_fulfilment": fulfilled.annotate(duration=fulfilment_duration).aggregate(value=Avg("duration"))["value"],
        "average_delivery": delivery.annotate(duration=delivery_duration).aggregate(value=Avg("duration"))["value"],
        "customer_summary": customer_summary,
    }
    return render(request, "staff-reports.html", context)


@staff_only
def enter_token(request, recharge_id):
    recharge = get_object_or_404(
        RechargeRequest.objects.select_related("tenant"),
        id=recharge_id,
    )
    if request.method == "GET":
        return render(request, "staff-token-entry.html", {"recharge": recharge})
    if request.method != "POST":
        return HttpResponseBadRequest("Token entry must use POST.")

    token = request.POST.get("token", "").strip()
    if not token or len(token) > 128:
        return HttpResponseBadRequest("Enter a valid token.")
    if recharge.payment_status != RechargeRequest.PaymentStatus.PAID:
        return HttpResponseBadRequest("Only paid requests can be fulfilled.")
    if recharge.token_status != RechargeRequest.TokenStatus.AWAITING_GENERATION:
        return HttpResponseBadRequest("This request is not awaiting token generation.")

    return _complete_token_fulfilment(request, recharge, token, "manual")


@staff_only
def generate_token(request, recharge_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Token generation must use POST.")
    recharge = get_object_or_404(
        RechargeRequest.objects.select_related("tenant"),
        id=recharge_id,
    )
    if recharge.payment_status != RechargeRequest.PaymentStatus.PAID:
        return HttpResponseBadRequest("Only paid requests can be fulfilled.")
    if recharge.token_status != RechargeRequest.TokenStatus.AWAITING_GENERATION:
        return HttpResponseBadRequest("This request is not awaiting token generation.")
    provider = get_token_generator()
    token = provider.generate(recharge.tenant.meter_number, recharge.amount)
    return _complete_token_fulfilment(request, recharge, token, provider.source)


def _complete_token_fulfilment(request, recharge, token, source):
    recharge.attach_token(encrypt_token(token), source)
    recharge.token_generated_by = getattr(request.user, "staff_profile", None)
    recharge.token_generated_at = timezone.now()
    recharge.save(update_fields=[
        "token_value_encrypted", "token_source", "token_status",
        "token_generated_by", "token_generated_at", "updated_at",
    ])

    provider_reference = get_notification_token_provider().send_recharge_token(
        recharge.tenant.phone_number,
        recharge.tenant.meter_number,
        token,
    )
    NotificationDelivery.objects.create(
        recharge=recharge,
        destination=recharge.tenant.phone_number,
        provider_reference=provider_reference,
    )
    record_audit(
        request.user,
        "notification.delivery_attempted",
        recharge.id,
        {"channel": "sms", "status": "sent"},
    )
    recharge.delivered_at = timezone.now()
    recharge.save(update_fields=["delivered_at", "updated_at"])
    record_audit(
        request.user,
        "token.generated" if source != "manual" else "token.entered",
        recharge.id,
        {"source": source, "token_status": recharge.token_status},
    )
    return redirect("staff-fulfilment-queue")
