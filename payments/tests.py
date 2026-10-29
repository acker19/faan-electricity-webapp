import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from .providers import PaystackProvider, get_payment_provider


class PaystackProviderTests(TestCase):
    def set_paystack_response(self, payload, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"status": True, "data": payload}
        ).encode()
        context = MagicMock()
        context.__enter__.return_value = response
        mock_urlopen.return_value = context

    @patch("payments.providers.urlopen")
    def test_initialize_uses_kobo_amount_and_customer_email(self, mock_urlopen):
        self.set_paystack_response(
            {"authorization_url": "https://checkout.paystack.com/test"},
            mock_urlopen,
        )

        url = PaystackProvider("sk_test_example").initialize(
            "FAAN-reference", Decimal("500.00"), "payer@example.com"
        )

        self.assertEqual(url, "https://checkout.paystack.com/test")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.paystack.co/transaction/initialize")
        self.assertEqual(
            json.loads(request.data),
            {
                "email": "payer@example.com",
                "amount": 50000,
                "reference": "FAAN-reference",
            },
        )

    @patch("payments.providers.urlopen")
    def test_verify_requires_matching_success_reference_amount_and_currency(
        self, mock_urlopen
    ):
        provider = PaystackProvider("sk_test_example")
        valid_transaction = {
            "status": "success",
            "reference": "FAAN-reference",
            "amount": 50000,
            "currency": "NGN",
        }
        for transaction in (
            valid_transaction,
            {**valid_transaction, "reference": "another-reference"},
            {**valid_transaction, "amount": 50001},
            {**valid_transaction, "currency": "USD"},
            {**valid_transaction, "status": "abandoned"},
        ):
            with self.subTest(transaction=transaction):
                self.set_paystack_response(transaction, mock_urlopen)
                self.assertEqual(
                    provider.verify("FAAN-reference", Decimal("500.00")),
                    transaction is valid_transaction,
                )


class PaymentProviderConfigurationTests(TestCase):
    @override_settings(PAYMENT_PROVIDER="paystack", PAYSTACK_SECRET_KEY="")
    def test_missing_paystack_key_fails_when_provider_is_requested(self):
        with self.assertRaisesMessage(
            RuntimeError,
            "PAYSTACK_SECRET_KEY is required when PAYMENT_PROVIDER=paystack.",
        ):
            get_payment_provider()
