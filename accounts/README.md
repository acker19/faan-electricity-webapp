# Customer account: signup and sign-in

Customer account endpoints are implemented in the `api` app and use Django
session authentication. The `accounts` app currently contains the staff-user
model; customer credentials are Django users linked one-to-one to a tenant.

## Signup and phone verification

1. The browser submits the customer's name, phone number, email, password,
   meter number, and FAAN-registered name to `POST /api/v1/tenants/register`.
2. The API validates the fields, creates the user and tenant, then starts a
   Twilio Verify SMS verification for the phone number.
3. On success, the API returns `tenant_id` and the browser stores it temporarily
   while showing the code-entry screen.
4. The browser submits `tenant_id` and the six-digit code to
   `POST /api/v1/tenants/verify-otp`. A valid code marks the phone as verified
   and signs the customer in with a Django session.
5. To send another code, submit `tenant_id` to
   `POST /api/v1/tenants/resend-otp`.

Signup uses the SMS channel, so Twilio Verify must be able to send SMS to the
customer's number. If delivery fails, signup returns HTTP 503 and rolls back
the user and tenant creation. An account created by an older failed attempt
without a tenant can be reused when the customer retries with the same phone.
An already registered phone, email, or meter is rejected with a validation
error.

## Password and email-code sign-in

1. The customer submits their phone number or email and password to
   `POST /api/v1/auth/login`.
2. The API checks the password and requires the customer's phone number to
   have been verified. It then starts a Twilio Verify code to the account's
   registered email using the `email` channel. The API responds with HTTP 202
   and a `tenant_id`; it does not sign the customer in yet.
3. The customer submits `tenant_id` and the six-digit code to
   `POST /api/v1/auth/verify-login-otp`.
4. If the code is approved, the API creates the Django session and returns the
   customer profile. The frontend uses same-origin requests with credentials
   and loads the profile from `GET /api/v1/auth/me` when needed.

The login email code is **not sent through the app's email client**. Twilio
Verify sends it, so the Verify Service must have its Email channel configured
with a working Email Integration. In Twilio Console, configure the SendGrid
integration, verified sender/domain, and Verify email template containing the
required `{{twilio_message}}` placeholder, then link that integration to the
Verify Service. The app needs no SendGrid API key; do not put one in the
project environment.

## Password reset

`POST /api/v1/auth/password-reset/request` accepts the customer's phone number
or email and starts a Twilio Verify SMS to the account phone. Submit the
returned `tenant_id`, SMS code, and new password to
`POST /api/v1/auth/password-reset/confirm`.

## Configuration and troubleshooting

Configure these server-side environment variables for Twilio Verify:

```env
OTP_PROVIDER=twilio_verify
TWILIO_ACCOUNT_SID=<Twilio account SID>
TWILIO_AUTH_TOKEN=<Twilio auth token>
TWILIO_VERIFY_SERVICE_ID=<Verify Service SID>
```

Never put Twilio credentials in browser code or commit them to source control.
Keep the local `.env` private. For local mock testing, set `OTP_PROVIDER=mock`;
the mock provider accepts `123456` and does not send messages.

If the API returns HTTP 503 while starting verification, check the Twilio error
code shown in the response and the server log. SMS signup failures concern the
SMS channel and destination number; login-email failures concern the Verify
Service's Email Integration and email channel. Do not expose authentication
tokens or raw provider responses when reporting errors.
