import hashlib
import hmac
import json
from decimal import Decimal
from urllib.request import Request, urlopen


class PaymentProvider:
    def initialize(self, reference: str, amount: Decimal, email: str) -> str:
        raise NotImplementedError

    def verify(self, reference: str, amount: Decimal) -> bool:
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    def initialize(self, reference, amount, email):
        del amount, email
        return f"/payments/demo-checkout/{reference}/"

    def verify(self, reference, amount):
        del amount
        return bool(reference)


class PaystackProvider(PaymentProvider):
    endpoint = "https://api.paystack.co"

    def __init__(self, secret_key):
        self.secret_key = secret_key

    def _request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.endpoint}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
            },
            method="POST" if payload is not None else "GET",
        )
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("status"):
            raise RuntimeError("Paystack request failed.")
        return result["data"]

    def initialize(self, reference, amount, email):
        data = self._request("/transaction/initialize", {
            "email": email,
            "amount": int(Decimal(amount) * 100),
            "reference": reference,
        })
        return data["authorization_url"]

    def verify(self, reference, amount):
        data = self._request(f"/transaction/verify/{reference}")
        return (
            data.get("status") == "success"
            and data.get("reference") == reference
            and data.get("amount") == int(Decimal(amount) * 100)
            and data.get("currency") == "NGN"
        )


def get_payment_provider():
    from django.conf import settings
    if settings.PAYMENT_PROVIDER == "mock":
        return MockPaymentProvider()
    if settings.PAYMENT_PROVIDER == "paystack":
        return PaystackProvider(settings.PAYSTACK_SECRET_KEY)
    raise RuntimeError(
        f"Unsupported PAYMENT_PROVIDER={settings.PAYMENT_PROVIDER!r}."
    )


def valid_webhook_signature(raw_body, signature, secret):
    if not signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)
