from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .providers import NotificationDeliveryError, TwilioVerifyOTPProvider


class TwilioVerifyOTPProviderTests(SimpleTestCase):
    @override_settings(
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="test-auth-token",
        TWILIO_VERIFY_SERVICE_ID="VA" + "2" * 32,
    )
    @patch("twilio.rest.Client")
    def test_start_email_verification_uses_twilio_email_channel(self, client_class):
        create_verification = (
            client_class.return_value.verify.v2.services.return_value
            .verifications.create
        )
        create_verification.return_value.sid = "VE123"

        provider = TwilioVerifyOTPProvider()

        sid = provider.start_verification(
            "customer@example.com", "login", channel="email"
        )

        self.assertEqual(sid, "VE123")
        create_verification.assert_called_once_with(
            to="customer@example.com", channel="email"
        )

    @override_settings(
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="test-auth-token",
        TWILIO_VERIFY_SERVICE_ID="VA" + "2" * 32,
    )
    @patch("twilio.rest.Client")
    def test_send_error_exposes_only_twilio_error_code(self, client_class):
        provider_error = Exception("Provider response includes private data")
        provider_error.code = 60200
        provider_error.status = 400
        client_class.return_value.verify.v2.services.return_value.verifications.create.side_effect = provider_error

        provider = TwilioVerifyOTPProvider()

        with self.assertRaises(NotificationDeliveryError) as raised:
            provider.start_verification("+2348031111111", "phone")

        self.assertIn("Twilio error 60200", str(raised.exception))
        self.assertNotIn("private data", str(raised.exception))

    @override_settings(
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="test-auth-token",
        TWILIO_VERIFY_SERVICE_ID="VA" + "2" * 32,
    )
    @patch("twilio.rest.Client")
    def test_missing_email_integration_error_is_actionable(self, client_class):
        provider_error = Exception("Provider response includes private data")
        provider_error.code = 60217
        provider_error.status = 400
        client_class.return_value.verify.v2.services.return_value.verifications.create.side_effect = provider_error

        provider = TwilioVerifyOTPProvider()

        with self.assertRaises(NotificationDeliveryError) as raised:
            provider.start_verification(
                "customer@example.com", "login", channel="email"
            )

        self.assertIn("Email verification is not configured", str(raised.exception))
        self.assertIn("Twilio error 60217", str(raised.exception))
        self.assertNotIn("private data", str(raised.exception))
