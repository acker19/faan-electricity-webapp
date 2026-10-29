import uuid
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle
from django.conf import settings

from .serializers import (
    RechargeCreateSerializer,
    RechargeStatusSerializer,
    TenantRegisterSerializer,
    OTPVerifySerializer,
    LoginSerializer,
    LoginOTPVerifySerializer,
    TenantSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from tenants.models import Tenant, PhoneOTP
from recharge.models import RechargeRequest
from payments.models import WebhookEvent
from payments.providers import get_payment_provider, valid_webhook_signature
from audit.services import record_audit
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import timedelta
from rest_framework import serializers
from notifications.providers import NotificationDeliveryError, get_otp_provider, get_token_provider


class TenantRegisterView(APIView):
    """Tenant self sign-up and phone OTP delivery via Twilio Verify."""

    def post(self, request):
        serializer = TenantRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                tenant = serializer.save()
                get_otp_provider().start_verification(tenant.phone_number, "phone")
        except NotificationDeliveryError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"tenant_id": tenant.id, "message": "Verification code sent.", "otp_sent": True},
            status=status.HTTP_201_CREATED,
        )


class TenantResendOTPView(APIView):
    """Resend phone verification code."""

    def post(self, request):
        serializer = serializers.UUIDField()
        tenant_id = request.data.get("tenant_id")
        try:
            tenant_id = serializer.to_internal_value(tenant_id)
            tenant = Tenant.objects.get(id=tenant_id)
        except (serializers.ValidationError, Tenant.DoesNotExist):
            return Response({"detail": "Signup account not found."}, status=status.HTTP_404_NOT_FOUND)
        if tenant.phone_verified_at:
            return Response({"detail": "This phone number is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            get_otp_provider().start_verification(tenant.phone_number, "phone")
        except NotificationDeliveryError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"message": "Verification code resent.", "otp_sent": True}, status=status.HTTP_200_OK)



class TenantVerifyOTPView(APIView):
    """Verify phone OTP via Twilio Verify. Marks tenant.phone_verified_at on success."""

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_id = serializer.validated_data["tenant_id"]
        otp = serializer.validated_data["otp"]

        tenant = get_object_or_404(Tenant, id=tenant_id)
        
        if not get_otp_provider().check_verification(tenant.phone_number, otp):
            return Response({"detail": "Invalid or expired verification code."}, status=status.HTTP_400_BAD_REQUEST)

        tenant.phone_verified_at = timezone.now()
        tenant.save()
        if tenant.user_id:
            login(request, tenant.user)

        return Response({"detail": "Phone verified."}, status=status.HTTP_200_OK)


class LoginView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        User = get_user_model()
        account = User.objects.filter(username__iexact=identifier).first()
        if account is None:
            account = User.objects.filter(email__iexact=identifier).first()
        user = authenticate(
            request,
            username=account.username if account else identifier,
            password=serializer.validated_data["password"],
        )
        if not user or not hasattr(user, "tenant_profile"):
            return Response(
                {"detail": "Invalid phone number or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.tenant_profile.phone_verified_at:
            return Response({"detail": "Verify your phone number before signing in."}, status=status.HTTP_403_FORBIDDEN)
        if not user.email:
            return Response(
                {"detail": "Add an email address to your account before signing in."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            get_otp_provider().start_verification(
                user.email, "login", channel="email"
            )
        except NotificationDeliveryError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = Response(
            {
                "tenant_id": user.tenant_profile.id,
                "detail": "A verification code was sent to your email address.",
            },
            status=status.HTTP_202_ACCEPTED,
        )
        response["Cache-Control"] = "no-store"
        return response


class LoginOTPVerifyView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = get_object_or_404(
            Tenant.objects.select_related("user"),
            id=serializer.validated_data["tenant_id"],
        )
        if (
            not tenant.user_id
            or not tenant.user.email
            or not tenant.phone_verified_at
        ):
            return Response(
                {"detail": "This account is not eligible to sign in."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not get_otp_provider().check_verification(
            tenant.user.email,
            serializer.validated_data["otp"],
            channel="email",
        ):
            return Response(
                {"detail": "Invalid or expired verification code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, tenant.user)
        response = Response(TenantSerializer(tenant).data)
        response["Cache-Control"] = "no-store"
        return response


class PasswordResetRequestView(APIView):
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        User = get_user_model()
        user = User.objects.filter(username__iexact=identifier).first()
        if user is None:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is None or not hasattr(user, "tenant_profile"):
            return Response({"detail": "No customer account was found."}, status=status.HTTP_404_NOT_FOUND)

        tenant = user.tenant_profile
        try:
            get_otp_provider().start_verification(tenant.phone_number, "password reset")
        except NotificationDeliveryError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"tenant_id": tenant.id, "message": "Password reset code sent.", "otp_sent": True},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = get_object_or_404(Tenant, id=serializer.validated_data["tenant_id"])
        
        if not get_otp_provider().check_verification(tenant.phone_number, serializer.validated_data["otp"]):
            return Response({"detail": "Invalid or expired verification code."}, status=status.HTTP_400_BAD_REQUEST)
        if not tenant.user_id:
            return Response({"detail": "This customer account cannot reset its password."}, status=status.HTTP_400_BAD_REQUEST)
        tenant.user.set_password(serializer.validated_data["password"])
        tenant.user.save(update_fields=["password"])
        PhoneOTP.objects.filter(tenant=tenant).delete()
        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        if not request.user.is_authenticated or not hasattr(request.user, "tenant_profile"):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(TenantSerializer(request.user.tenant_profile).data)


class RechargeListView(APIView):
    def get(self, request):
        if not request.user.is_authenticated or not hasattr(request.user, "tenant_profile"):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        queryset = RechargeRequest.objects.filter(tenant=request.user.tenant_profile).order_by("-created_at")
        return Response(RechargeStatusSerializer(queryset, many=True).data)


class RechargeCreateView(APIView):
    """Create an awaiting-payment recharge for an approved tenant."""

    def post(self, request):
        if not request.user.is_authenticated or not hasattr(request.user, "tenant_profile"):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        payload = request.data.copy()
        payload["tenant_id"] = str(request.user.tenant_profile.id)
        serializer = RechargeCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        email = request.user.email.strip()
        if not email:
            return Response(
                {"detail": "Add an email address to your account before making a payment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            recharge = RechargeRequest.objects.create(
                tenant_id=serializer.validated_data["tenant_id"],
                amount=serializer.validated_data["amount"],
                payment_reference=f"FAAN-{uuid.uuid4().hex[:24].upper()}",
            )
            authorization_url = get_payment_provider().initialize(
                recharge.payment_reference,
                recharge.amount,
                email,
            )

        return Response(
            {
                "id": recharge.id,
                "payment_reference": recharge.payment_reference,
                "payment_status": recharge.payment_status,
                "amount": recharge.amount,
                "authorization_url": authorization_url,
            },
            status=status.HTTP_201_CREATED,
        )


class RechargeStatusView(APIView):
    def get(self, request, recharge_id):
        if not request.user.is_authenticated or not hasattr(request.user, "tenant_profile"):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        recharge = get_object_or_404(RechargeRequest, id=recharge_id)
        if recharge.tenant_id != request.user.tenant_profile.id:
            return Response(
                {"detail": "This recharge does not belong to the signed-in account."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(RechargeStatusSerializer(recharge).data)


class PaymentWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Paystack-Signature", "")
        secret = settings.PAYSTACK_SECRET_KEY
        signature_valid = valid_webhook_signature(raw_body, signature, secret)
        if settings.PAYMENT_PROVIDER == "mock" and settings.DEBUG:
            signature_valid = signature == "mock-signature"
        try:
            payload = request.data
        except Exception:
            payload = {"raw": raw_body.decode("utf-8", errors="replace")}
        reference = payload.get("data", {}).get("reference") if isinstance(payload, dict) else None
        if not signature_valid:
            event = WebhookEvent.objects.create(
                signature_valid=False,
                payload=payload,
                provider_reference=None,
            )
            record_audit("system", "payment.webhook_rejected", event.id, {})
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
        event, created = WebhookEvent.objects.get_or_create(
            provider_reference=reference,
            defaults={"signature_valid": True, "payload": payload},
        )
        if not created and event.processed:
            return Response({"detail": "Webhook already processed."}, status=status.HTTP_200_OK)
        if payload.get("event") != "charge.success" or not reference:
            return Response({"detail": "Webhook ignored."}, status=status.HTTP_200_OK)
        recharge = get_object_or_404(RechargeRequest, payment_reference=reference)
        if recharge.payment_status == RechargeRequest.PaymentStatus.AWAITING_PAYMENT:
            if get_payment_provider().verify(reference, recharge.amount):
                recharge.mark_paid()
                recharge.save(update_fields=["payment_status", "token_status", "paid_at", "updated_at"])
        event.processed = True
        event.save(update_fields=["processed"])
        return Response({"detail": "Webhook processed."}, status=status.HTTP_200_OK)
