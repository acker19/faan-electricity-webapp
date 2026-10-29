from abc import ABC, abstractmethod
import logging


logger = logging.getLogger(__name__)


class NotificationDeliveryError(Exception):
    """Raised when an external notification provider cannot deliver a message."""


class OTPProvider(ABC):
    @abstractmethod
    def start_verification(
        self, recipient: str, purpose: str, channel: str = "sms"
    ) -> str:
        """Start OTP verification and return a session ID."""
        raise NotImplementedError

    @abstractmethod
    def check_verification(
        self, recipient: str, otp: str, channel: str = "sms"
    ) -> bool:
        """Verify OTP code. Returns True if valid, False otherwise."""
        raise NotImplementedError


class TokenProvider(ABC):
    @abstractmethod
    def send_recharge_token(self, phone_number: str, meter_number: str, token: str) -> str:
        raise NotImplementedError


class MockOTPProvider(OTPProvider):
    """Test-only OTP provider."""
    def start_verification(
        self, recipient: str, purpose: str, channel: str = "sms"
    ) -> str:
        return f"mock-sid:{channel}:{recipient}"

    def check_verification(
        self, recipient: str, otp: str, channel: str = "sms"
    ) -> bool:
        return otp == "123456"


class MockTokenProvider(TokenProvider):
    """Test-only token provider."""
    def send_recharge_token(self, phone_number: str, meter_number: str, token: str) -> str:
        return f"mock-token-sid:{phone_number}"


class TwilioVerifyOTPProvider(OTPProvider):
    """Twilio Verify for OTP management."""
    def __init__(self):
        from django.conf import settings
        from twilio.rest import Client

        self._verify_service_id = settings.TWILIO_VERIFY_SERVICE_ID
        self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def start_verification(
        self, recipient: str, purpose: str, channel: str = "sms"
    ) -> str:
        try:
            verification = self._client.verify.v2.services(
                self._verify_service_id
            ).verifications.create(to=recipient, channel=channel)
            return verification.sid
        except Exception as exc:
            error_code = getattr(exc, "code", None)
            logger.warning(
                "Twilio Verify send failed (status=%s, code=%s).",
                getattr(exc, "status", None),
                error_code,
            )
            detail = "Could not send verification code. Please try again."
            if error_code == 60217:
                detail = (
                    "Email verification is not configured for this service. "
                    "Please contact support. (Twilio error 60217.)"
                )
            elif error_code is not None:
                detail += f" (Twilio error {error_code}.)"
            raise NotificationDeliveryError(
                detail
            ) from exc

    def check_verification(
        self, recipient: str, otp: str, channel: str = "sms"
    ) -> bool:
        try:
            result = self._client.verify.v2.services(
                self._verify_service_id
            ).verification_checks.create(to=recipient, code=otp)
            return result.status == "approved"
        except Exception:
            return False


class TwilioSMSTokenProvider(TokenProvider):
    """Twilio SMS for token delivery."""
    def __init__(self):
        from django.conf import settings
        from twilio.rest import Client

        self._from_number = settings.TWILIO_FROM_NUMBER
        self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def send_recharge_token(self, phone_number: str, meter_number: str, token: str) -> str:
        try:
            message = self._client.messages.create(
                body=f"FAAN Electricity: Your token for meter {meter_number} is {token}.",
                from_=self._from_number,
                to=phone_number,
            )
            return message.sid
        except Exception as exc:
            raise NotificationDeliveryError(
                "Could not send token. Please try again."
            ) from exc


def get_otp_provider() -> OTPProvider:
    from django.conf import settings

    if settings.OTP_PROVIDER == "mock":
        return MockOTPProvider()
    if settings.OTP_PROVIDER == "twilio_verify":
        return TwilioVerifyOTPProvider()
    raise RuntimeError(
        f"Unsupported OTP_PROVIDER={settings.OTP_PROVIDER!r}"
    )


def get_token_provider() -> TokenProvider:
    from django.conf import settings

    if settings.TOKEN_SMS_PROVIDER == "mock":
        return MockTokenProvider()
    if settings.TOKEN_SMS_PROVIDER == "twilio_sms":
        return TwilioSMSTokenProvider()
    raise RuntimeError(
        f"Unsupported TOKEN_SMS_PROVIDER={settings.TOKEN_SMS_PROVIDER!r}"
    )
