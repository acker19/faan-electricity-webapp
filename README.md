# FAAN Electricity Vending — Web Frontend MVP

Frontend implementation based on the FAAN Electricity Vending Web Application PRD v2.0.

## Included
- Customer dashboard, meters, recharge, transactions, token, receipt and profile
- Staff dashboard, fulfilment queue, transaction detail and token-entry screen
- Admin dashboard, staff management and audit-log screen
- Responsive mobile/tablet/desktop design
- Mock interactions ready to be replaced by Django REST calls

## Deferred
POS, OPay/Moniepoint, real Remita, and the real FAAN vending integration.

The UI does not invent external API contracts. Payment and vending are shown as separate stages, matching the PRD.

## Production Setup

### Environment Variables for DigitalOcean (Recommended)

For Nigerian customers, configure these in your DigitalOcean App Platform environment:

**Core Settings:**
```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<your-secret-key>
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com
REDIS_URL=<your-redis-connection-string>
```

**Customer Verification (Twilio Verify) — SMS and Email OTP:**
```env
OTP_PROVIDER=twilio_verify
TWILIO_ACCOUNT_SID=<your-account-sid>
TWILIO_AUTH_TOKEN=<your-auth-token>
TWILIO_VERIFY_SERVICE_ID=<your-verify-service-id>
```

**Token Delivery (Twilio SMS):**
```env
TOKEN_SMS_PROVIDER=twilio_sms
TWILIO_FROM_NUMBER=+234...
```

**Paystack sandbox payments:**
```env
PAYMENT_PROVIDER=paystack
PAYSTACK_SECRET_KEY=sk_test_<your-test-secret-key>
```

Set the Paystack webhook URL to
`https://<your-domain>/api/v1/webhooks/payments/`. Keep the secret key server-side;
never add it to frontend code or commit it. The application verifies the webhook
signature and confirms the transaction with Paystack, including the reference,
amount, and NGN currency. Use a test key until sandbox checkout and webhook
confirmation have both been validated.

**SSL & Security:**
```env
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SECURE_HSTS_SECONDS=31536000
```

### Setup Steps

1. **Configure Twilio Verify:**
   - Go to [Twilio Console → Verify](https://www.twilio.com/console/verify/services)
   - Create a Verify Service and enable SMS for registration and phone verification
   - Copy the Service ID and add as `TWILIO_VERIFY_SERVICE_ID`
   - In Twilio SendGrid, verify your sender/domain and create a Dynamic Template containing the required `{{twilio_message}}` placeholder.
   - In Twilio Console **Settings → Email Integration**, create an integration with the verified sender, SendGrid API key, and template ID. Link that integration to the Verify Service under its **Email** tab.
   - Keep the SendGrid API key in Twilio's Email Integration configuration; the app does not need or use it.
   - The login flow sends an OTP to the account's registered email only after the password is accepted. In development, `OTP_PROVIDER=mock` accepts `123456` and does not send a real email; real delivery requires the Twilio credentials above and the Verify Email channel to be configured.

2. **Get Your Twilio SMS Number:**
   - Go to [Twilio Console → Phone Numbers](https://www.twilio.com/console/phone-numbers/incoming)
   - Buy a number with Nigerian routing or use your existing Messaging Service
   - Format: `+234` prefix for Nigerian numbers

3. **Deploy to DigitalOcean:**
   - Push to a Git repository
   - In DigitalOcean, create App Platform → connect your repo
   - Add PostgreSQL database and Redis (DigitalOcean managed)
   - Set environment variables from above
   - Deploy

4. **Security Checklist:**
   - Never commit `.env` files or secrets to version control
   - Use DigitalOcean's Secrets/Environment feature for sensitive values
   - Enable HTTPS on your custom domain
   - Rotate `DJANGO_SECRET_KEY` regularly

### Phone Number Format
- Nigerian numbers: `+234XXXXXXXXXX` (11 digits after country code)
- Example: `+2348012345678`
