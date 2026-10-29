import secrets
from abc import ABC, abstractmethod
from decimal import Decimal


class TokenProvider(ABC):
    source = ""

    @abstractmethod
    def generate(self, meter_number: str, amount: Decimal) -> str:
        raise NotImplementedError


class MockTokenProvider(TokenProvider):
    """Generate a visibly non-functional token for local demos only."""

    source = "mock"

    def generate(self, meter_number: str, amount: Decimal) -> str:
        del meter_number
        amount_part = f"{amount:.2f}".replace(".", "")
        random_part = secrets.token_hex(8).upper()
        return f"DEMO-{amount_part}-{random_part}"


def get_token_provider() -> TokenProvider:
    from django.conf import settings

    if settings.TOKEN_PROVIDER == "mock":
        return MockTokenProvider()
    raise RuntimeError(
        f"Unsupported TOKEN_PROVIDER={settings.TOKEN_PROVIDER!r}; "
        "configure a real provider before processing requests."
    )
