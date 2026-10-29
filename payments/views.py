from django.shortcuts import render

# Create your views here.
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.services import record_audit
from recharge.models import RechargeRequest


@login_required(login_url="/")
def demo_checkout(request, reference):
    if settings.PAYMENT_PROVIDER != "mock" or not settings.DEBUG:
        return HttpResponseBadRequest("Demo checkout is disabled.")
    recharge = get_object_or_404(
        RechargeRequest.objects.select_related("tenant"),
        payment_reference=reference,
    )
    if recharge.tenant.user_id != request.user.id:
        return HttpResponseBadRequest("This checkout does not belong to the signed-in account.")
    if request.method == "POST":
        if recharge.payment_status == RechargeRequest.PaymentStatus.AWAITING_PAYMENT:
            recharge.mark_paid()
            recharge.save(update_fields=["payment_status", "token_status", "paid_at", "updated_at"])
            record_audit("system", "payment.demo_completed", recharge.id, {"reference": reference})
        return redirect(f"/?payment=success#{reference}")
    return render(request, "demo-checkout.html", {"recharge": recharge})
