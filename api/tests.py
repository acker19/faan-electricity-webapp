from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIClient, APIRequestFactory
from django.utils import timezone

from notifications.providers import NotificationDeliveryError
from tenants.models import Tenant
from recharge.models import RechargeRequest
from .views import TenantRegisterView


class TenantRegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "full_name": "New Customer",
            "phone_number": "+2348031111111",
            "email": "new-customer@example.com",
            "password": "secure-password-123",
            "meter_number": "4500123456",
            "registered_name": "New Customer",
        }

    @patch("api.views.get_otp_provider")
    def test_failed_otp_delivery_rolls_back_account_creation(self, get_provider):
        get_provider.return_value.start_verification.side_effect = NotificationDeliveryError(
            "Could not send verification code. Please try again."
        )

        request = APIRequestFactory().post(
            "/api/v1/tenants/register", self.payload, format="json"
        )
        response = TenantRegisterView.as_view()(request)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(
            get_user_model().objects.filter(username=self.payload["phone_number"]).exists()
        )
        self.assertFalse(Tenant.objects.filter(meter_number=self.payload["meter_number"]).exists())

    @patch("api.views.get_otp_provider")
    def test_registration_recovers_unlinked_user_left_by_failed_signup(self, get_provider):
        get_user_model().objects.create_user(
            username=self.payload["phone_number"],
            email="old-email@example.com",
            password="old-password-123",
        )

        response = self.client.post(
            "/api/v1/tenants/register", self.payload, format="json"
        )

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username=self.payload["phone_number"])
        self.assertEqual(user.email, self.payload["email"])
        self.assertTrue(Tenant.objects.filter(user=user).exists())
        get_provider.return_value.start_verification.assert_called_once_with(
            self.payload["phone_number"], "phone"
        )

    def test_registration_returns_validation_error_for_existing_phone(self):
        user = get_user_model().objects.create_user(
            username=self.payload["phone_number"],
            email="existing@example.com",
            password="old-password-123",
        )
        Tenant.objects.create(
            user=user,
            meter_number="4500099999",
            registered_name="Existing Customer",
            phone_number=self.payload["phone_number"],
        )

        response = self.client.post(
            "/api/v1/tenants/register", self.payload, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone_number", response.data)


@override_settings(
    REST_FRAMEWORK={"DEFAULT_THROTTLE_RATES": {"login": "5/minute"}},
    OTP_PROVIDER="mock",
)
class LoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="+2348030000000",
            email="customer@example.com",
            password="correct-password-123",
        )
        self.tenant = Tenant.objects.create(
            user=self.user,
            meter_number="4500129876",
            registered_name="Customer Name",
            phone_number="+2348030000000",
        )
        self.client.defaults["REMOTE_ADDR"] = (
            f"10.{self.tenant.id.bytes[0]}.{self.tenant.id.bytes[1]}."
            f"{self.tenant.id.bytes[2]}"
        )

    def test_login_requires_phone_verification(self):
        response = self.client.post(
            "/api/v1/auth/login",
            {"identifier": self.tenant.phone_number, "password": "correct-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], "Verify your phone number before signing in.")

    def test_verified_customer_must_verify_email_otp_to_login(self):
        from django.utils import timezone

        self.tenant.phone_verified_at = timezone.now()
        self.tenant.save(update_fields=["phone_verified_at"])

        response = self.client.post(
            "/api/v1/auth/login",
            {"identifier": self.user.email, "password": "correct-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(str(response.data["tenant_id"]), str(self.tenant.id))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        response = self.client.post(
            "/api/v1/auth/verify-login-otp",
            {"tenant_id": str(self.tenant.id), "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["phone_number"], self.tenant.phone_number)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response["Cache-Control"], "no-store")

    @patch("api.views.get_otp_provider")
    def test_login_sends_otp_to_the_account_email(self, get_provider):
        from django.utils import timezone

        self.tenant.phone_verified_at = timezone.now()
        self.tenant.save(update_fields=["phone_verified_at"])

        response = self.client.post(
            "/api/v1/auth/login",
            {"identifier": self.tenant.phone_number, "password": "correct-password-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        get_provider.return_value.start_verification.assert_called_once_with(
            self.user.email, "login", channel="email"
        )

    def test_login_rejects_invalid_email_otp(self):
        from django.utils import timezone

        self.tenant.phone_verified_at = timezone.now()
        self.tenant.save(update_fields=["phone_verified_at"])

        self.client.post(
            "/api/v1/auth/login",
            {"identifier": self.user.email, "password": "correct-password-123"},
            format="json",
        )
        response = self.client.post(
            "/api/v1/auth/verify-login-otp",
            {"tenant_id": str(self.tenant.id), "otp": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_invalid_credentials_use_generic_unauthorized_response(self):
        response = self.client.post(
            "/api/v1/auth/login",
            {"identifier": self.tenant.phone_number, "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Invalid phone number or password.")


class LoginPageTests(TestCase):
    def test_login_page_route_uses_login_template(self):
        match = resolve("/login/")

        self.assertEqual(match.url_name, "login-page")
        self.assertEqual(match.func.view_initkwargs["template_name"], "login.html")


class RechargePaymentInitializationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="+2348032222222",
            email="payer@example.com",
            password="secure-password-123",
        )
        self.tenant = Tenant.objects.create(
            user=self.user,
            meter_number="4500123457",
            registered_name="Payment Customer",
            phone_number="+2348032222222",
            phone_verified_at=timezone.now(),
            verification_status=Tenant.VerificationStatus.APPROVED,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("api.views.get_payment_provider")
    def test_initializes_checkout_with_account_email(self, get_provider):
        get_provider.return_value.initialize.return_value = (
            "https://checkout.paystack.com/example"
        )

        response = self.client.post(
            "/api/v1/recharge/",
            {"amount": "500.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        get_provider.return_value.initialize.assert_called_once_with(
            response.data["payment_reference"],
            Decimal("500.00"),
            self.user.email,
        )
        self.assertEqual(
            response.data["authorization_url"],
            "https://checkout.paystack.com/example",
        )

    @patch("api.views.get_payment_provider")
    def test_rejects_checkout_without_account_email(self, get_provider):
        self.user.email = ""
        self.user.save(update_fields=["email"])

        response = self.client.post(
            "/api/v1/recharge/",
            {"amount": "500.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        get_provider.assert_not_called()

    @patch("api.views.valid_webhook_signature", return_value=True)
    @patch("api.views.get_payment_provider")
    def test_webhook_verifies_amount_before_marking_recharge_paid(
        self, get_provider, verify_signature
    ):
        recharge = RechargeRequest.objects.create(
            tenant=self.tenant,
            amount=Decimal("500.00"),
            payment_reference="FAAN-test-payment",
        )
        get_provider.return_value.verify.return_value = True
        payload = {
            "event": "charge.success",
            "data": {"reference": recharge.payment_reference},
        }

        response = self.client.post(
            "/api/v1/webhooks/payments/",
            payload,
            format="json",
            HTTP_X_PAYSTACK_SIGNATURE="test-signature",
        )

        self.assertEqual(response.status_code, 200)
        get_provider.return_value.verify.assert_called_once_with(
            recharge.payment_reference, Decimal("500.00")
        )
        recharge.refresh_from_db()
        self.assertEqual(recharge.payment_status, RechargeRequest.PaymentStatus.PAID)
        self.assertEqual(
            recharge.token_status, RechargeRequest.TokenStatus.AWAITING_GENERATION
        )
