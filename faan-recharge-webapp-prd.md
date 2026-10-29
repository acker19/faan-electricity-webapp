# FAAN Metering Unit — Online Recharge Web App
## Product Requirements Document (PRD) — v1.0 (Draft)

| | |
|---|---|
| **Author** | Tife — SIWES Intern, FAAN Metering Unit, Murtala Muhammed International Airport |
| **Status** | Independent proposal — not yet officially backed by FAAN |
| **Target stack** | Python 3.12, Django 5.x, Django REST Framework, PostgreSQL, Redis, Celery |
| **Scope** | Self-service web app only — tenant signup, verification, and online payment. No POS/agent-network integration (out of scope for this version). |
| **Working name** | *FAAN SwiftRecharge* (placeholder — rename freely) |

**Note to whoever builds from this document:** Sections 8–11 (data model, API, payment integration, security) are binding. Section 14 gives a build order.

---

## 1. Executive Summary

Tenants at MMIA who need to recharge their prepaid electricity meter ("light") currently make three physical trips — to the FAAN Metering Unit office, to a bank, and back to the office — just to exchange cash for a token. This platform replaces that with a web app: a tenant signs up once with their meter number, FAAN-registered name, and phone number; a Metering Unit staff member approves it; and from then on the tenant can request and pay for a recharge from their phone or computer. Payment is verified automatically, staff release the token from FAAN's existing vending system, and it's delivered by SMS — no office visit, no bank trip, no second trip.

The project is currently independent (not yet FAAN-endorsed), so this is written for a sandboxed pilot with a clear path to production once FAAN grants official access.

---

## 2. Problem Statement

### 2.1 Current process (AS-IS)

1. Tenant goes to the FAAN Metering Unit office with their meter number and the name registered with FAAN.
2. Tenant tells the attending staff member how much light they want to buy.
3. Staff generates a FAAN RRR (Remita Retrieval Reference) for that amount.
4. Tenant travels to a bank to deposit the money against that RRR.
5. Bank issues a payment receipt.
6. Tenant travels back to the office and presents the receipt.
7. Staff records the payment and issues the recharge token from FAAN's existing vending system.

### 2.2 Cost of the current process

- Three physical journeys (office → bank → office) for a single recharge.
- Transport fare paid on every recharge.
- Time lost queueing twice at the office and once at the bank.
- Reconciliation is manual and paper-based, with no structured audit trail.

---

## 3. Goals

### 3.1 Product goals

- **G1.** A tenant can sign up without visiting the FAAN office.
- **G2.** A tenant can request, pay for, and receive a recharge without visiting the FAAN office.
- **G3.** No token is released until payment is verified electronically — no manual receipt-matching.
- **G4.** FAAN staff keep control of token generation (via the existing vending system) but stop manually matching paper receipts or handing tokens over in person.
- **G5.** Every transaction is logged and auditable.

### 3.2 Explicit non-goals

- **NG1.** This platform does **not** generate real STS tokens — that stays inside FAAN's existing vending system, which holds the meter-specific cryptographic keys (see §16 Glossary, A5.1). The MVP's `MockTokenProvider` (A5.2) produces demo placeholders only, never anything that functions on a real meter.
- **NG2.** No changes to FAAN's core metering infrastructure.
- **NG3.** No POS/agent-network channel in this version — a tenant needs their own phone or computer and a way to pay online (card, bank transfer, or USSD). This is a deliberate scope cut, not an oversight: it means tenants without a smartphone, without any digital payment method, or less comfortable navigating a web form aren't served by v1. Worth revisiting later if that turns out to matter for adoption — see §15.
- **NG4.** Electricity recharge only — no rent, parking, or other billing types.

---

## 4. Actors & Roles

| Actor | Who | Primary interactions |
|---|---|---|
| **Tenant** | Airport shop/office holder with a FAAN-managed prepaid meter | Signs up once; requests and pays for recharges online; receives tokens |
| **Metering Unit Staff** | FAAN staff | Approves tenant sign-ups; fulfils token requests via the existing vending system; handles exceptions |
| **Platform Admin** | Whoever administers the app (Tife, initially) | Manages staff accounts, payment gateway config, monitoring |
| **System** | The Django platform | Orchestrates sign-up, payment verification, token requests, delivery, notifications, audit |

---

## 5. Assumptions, Constraints & Dependencies
- **A5.1 — Token generation stays external.** FAAN's Metering Unit already has a digital system that generates STS-compliant tokens. This platform treats it as an external boundary and never reimplements token cryptography — that requires the Supply Group Code-specific vending keys FAAN's system holds (see Glossary).
- **A5.2 — Three token sources, one interface.** Real STS tokens can only come from FAAN's licensed vending system — this project never reimplements that cryptography (A5.1). For the MVP, before there's staff or API access, a `MockTokenProvider` auto-generates a plausible-looking but cryptographically meaningless placeholder, purely so the platform can be demoed and pitched end-to-end without a human in the loop for every run — it will not credit a real meter. Once there's staff access, switch to manual entry: staff generate the real token in the existing tool exactly as today and paste it into the dashboard once. Once FAAN exposes an API, swap in a real `FAANVendingAPITokenProvider`. All three sit behind the same `TokenProvider` interface (§7.2) and are recorded on `RechargeRequest.token_source` (§8), so which kind of token any given request got is never ambiguous — critical, given only two of the three are real.
- **A5.3 — Independent project, sandboxed pilot.** Not yet FAAN-endorsed. Production access — a live payment gateway account under FAAN's name, direct access to FAAN's tenant database, a Remita/TSA collections account — requires FAAN's business registration and sign-off. Build and pilot against sandbox/test credentials, with a go-live checklist (§14) for the switch.
- **A5.4 — No live tenant registry access assumed.** This platform keeps its own tenant register, populated by self-sign-up plus a one-time staff approval (staff cross-check against FAAN's existing records during approval, exactly as today — but once per tenant, not once per recharge).
- **A5.5 — Remita/TSA reconciliation is a business item, not (yet) a code item.** FAAN, as a federal agency, is generally required to route revenue through Remita into the Treasury Single Account, regardless of which payment gateway collects it. Full per-transaction reconciliation needs FAAN's own Remita MDA credentials, which this project doesn't have yet. The data model reserves a `remita_rrr` field (§8) so reconciliation can be wired in later — per-transaction via Remita's API, or a periodic bulk RRR raised by FAAN finance against total collections — without a schema change. Flag this to FAAN's finance/ICT side before any real-money launch.
- **A5.6 — Data protection.** Handling meter numbers, names, and phone numbers makes this platform a data controller under the Nigeria Data Protection Act 2023, in force since June 2023, which replaced the earlier 2019 regulation and created the Nigeria Data Protection Commission (NDPC) to enforce it. Practical implications are in §11.4.

---

## 6. Target User Journeys (TO-BE)

### 6.1 Tenant sign-up & verification (one-time)

1. Tenant opens the web app and enters: meter number, the name registered with FAAN, and a phone number.
2. Platform creates a `Tenant` record (`verification_status = pending`) and sends an OTP to confirm the phone number.
3. Once confirmed, the sign-up lands in the staff approval queue.
4. A Metering Unit staff member cross-checks meter number + name against FAAN's internal records — today's process, done once instead of on every visit — and approves or rejects.
5. On approval, the tenant is notified by SMS and can recharge from then on. On rejection, they're told why (e.g. name mismatch) and can resubmit.

### 6.2 Recharge & online payment

1. A verified tenant logs in (phone number + OTP — no password) and requests a recharge, entering the amount.
2. Platform creates a `RechargeRequest` (`payment_status = awaiting_payment`), initializes a transaction with the payment gateway, and redirects the tenant to pay (card, bank transfer, or USSD).
3. Tenant pays; the gateway redirects back and also fires a server-to-server webhook.
4. Platform verifies the webhook signature, cross-checks with a direct server-side "verify transaction" call for belt-and-braces confirmation, matches it to the request by reference, marks it `paid`, and queues it for fulfilment.
5. Staff generate the token in FAAN's existing vending system (as today) and paste it into the platform.
6. Platform encrypts and stores the token, marks the request `fulfilled`, and delivers it to the tenant by SMS (and in-app).

### 6.3 Staff token fulfilment workflow

1. Staff dashboard lists every `paid` request awaiting a token, oldest first, with tenant name, meter number, and amount.
2. Staff generate the token in FAAN's existing vending system for that meter number and amount, exactly as today.
3. Staff paste the token into the platform against that request; the platform validates the format, encrypts it, marks the request `fulfilled`, logs which staff member fulfilled it and when, and triggers delivery.

### 6.4 Exceptions

- Payment received against a meter number that's since been unverified/revoked: held in an exceptions queue for manual staff review rather than silently failing.
- Token entry fails basic format validation: request stays open, staff is alerted, tenant sees "processing," never a wrong token.
- Payment initiated but never completed (tenant abandons checkout): `RechargeRequest` auto-expires after a set window so it doesn't sit as a false pending forever.

---

## 7. System Architecture

### 7.1 High-level

A Django monolith — nothing about this scope needs microservices. PostgreSQL for durable data; Redis for caching, idempotency keys, and as the Celery broker; Celery for async work (webhook processing, SMS dispatch, retries with backoff); Django REST Framework for the API surface (the payment webhook, any JS-driven frontend bits); server-rendered Django templates for the tenant-facing app and staff dashboard, unless a richer frontend is wanted later. Deployed behind Nginx + Gunicorn, TLS terminated upstream.

### 7.2 Django app breakdown

| App | Responsibility |
|---|---|
| `accounts` | Tenant auth (phone + OTP) and staff auth (password + MFA), roles/permissions |
| `tenants` | `Tenant` model, sign-up, verification/approval workflow |
| `recharge` | `RechargeRequest` — the core orchestration state machine |
| `payments` | Payment gateway adapter, webhook handling, signature verification |
| `tokens` | `TokenProvider` interface; `MockTokenProvider` (MVP/demo — A5.2); manual entry via `staffdesk`; `FAANVendingAPITokenProvider` (future) |
| `notifications` | SMS/email dispatch behind a `NotificationProvider` interface |
| `staffdesk` | Staff dashboard — approval queue, fulfilment queue, exceptions |
| `audit` | `AuditLogEntry` model plus signals to record sensitive actions |
| `api` | DRF routers/viewsets for the webhook and any JS frontend calls |
| `core` | Shared base models (UUID PK, timestamps), utilities, settings |

### 7.3 Why these choices

- **Django over FastAPI**: this is CRUD-plus-workflow with an admin-heavy staff side — Django's admin, ORM, and auth save real time.
- **Celery + Redis over synchronous webhook handling**: a payment webhook must never block on SMS delivery; ack fast, process async.
- **PostgreSQL over SQLite**: this handles money — transactional integrity and concurrent writes matter from day one.
- **`PaymentProvider` interface even with one gateway**: keeps Paystack-specific code out of the rest of the app, so switching or adding a gateway later (Flutterwave, or OPay's Checkout API, if POS/fintech access ever comes back into scope) is a new adapter, not a rewrite.

---

## 8. Data Model

```python
# tenants/models.py
class Tenant(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    meter_number = models.CharField(max_length=32, unique=True, db_index=True)
    registered_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)  # E.164
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=12, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    verified_by = models.ForeignKey("accounts.StaffUser", null=True, blank=True, on_delete=models.SET_NULL)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

```python
# recharge/models.py
class RechargeRequest(models.Model):
    class PaymentStatus(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    class TokenStatus(models.TextChoices):
        NOT_APPLICABLE = "n_a", "N/A"
        AWAITING_GENERATION = "awaiting_generation", "Awaiting generation"
        FULFILLED = "fulfilled", "Fulfilled"
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="recharge_requests")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    payment_reference = models.CharField(max_length=100, unique=True)  # doubles as the idempotency key
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.AWAITING_PAYMENT)
    paid_at = models.DateTimeField(null=True, blank=True)
    remita_rrr = models.CharField(max_length=32, blank=True)  # reserved for reconciliation — see A5.5

    token_status = models.CharField(max_length=20, choices=TokenStatus.choices, default=TokenStatus.NOT_APPLICABLE)
    token_source = models.CharField(max_length=10, blank=True)  # "mock" | "manual" | "api" — see A5.2; "mock" must never appear once real money is involved
    token_value_encrypted = models.BinaryField(null=True, blank=True)  # never store plaintext — see §11.3
    token_generated_by = models.ForeignKey("accounts.StaffUser", null=True, blank=True, on_delete=models.SET_NULL)
    token_generated_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["payment_status", "token_status"])]
```

```python
# payments/models.py
class WebhookEvent(models.Model):
    """Raw log of every inbound webhook: signature result, payload, outcome.
    Exists independently of RechargeRequest so nothing is ever silently dropped."""
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    signature_valid = models.BooleanField()
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
```

```python
# audit/models.py
class AuditLogEntry(models.Model):
    actor = models.CharField(max_length=255)   # staff username, "system", or tenant id
    action = models.CharField(max_length=100)  # "tenant.approved", "token.entered", ...
    target = models.CharField(max_length=255)  # e.g. the RechargeRequest id
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 9. API Specification
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/v1/tenants/register` | Public, rate-limited | Tenant self sign-up |
| `POST /api/v1/tenants/verify-otp` | Public | Confirm phone ownership |
| `GET /api/v1/tenants/me` | Tenant session | Check verification status |
| `POST /api/v1/recharge/` | Tenant session | Initiate a recharge; returns a payment redirect URL |
| `GET /api/v1/recharge/{id}/` | Tenant session | Poll recharge status |
| `POST /api/v1/webhooks/payments/` | Signed, server-to-server | Payment notification from the gateway |
| `GET /staff/queue/approvals` | Staff auth | Tenant approval queue |
| `GET /staff/queue/fulfilment` | Staff auth | Requests awaiting a token |
| `POST /staff/fulfilment/{id}/enter-token` | Staff auth + MFA | Enter the generated token; triggers delivery |

---

## 10. Payment Gateway Integration

**Recommended default: Paystack.** It's the most widely used gateway for Nigerian web apps, has strong Django library support, and covers cards, bank transfer, and USSD out of the box — a reasonable match for tenants without a card. This is a default assumption, not a hard requirement — Flutterwave is a drop-in alternative behind the same `PaymentProvider` interface if preferred.

How it works:

1. **Initialize:** on `POST /api/v1/recharge/`, the platform calls Paystack's Initialize Transaction endpoint with the tenant's email/amount and gets back an `authorization_url` to redirect the tenant to, plus a `reference` — store this as `RechargeRequest.payment_reference` immediately, before the tenant even pays, so nothing is lost if they abandon checkout.
2. **Tenant pays** on Paystack's hosted checkout page.
3. **Confirm, twice:** Paystack sends a webhook (`charge.success`) signed with `X-Paystack-Signature` — an HMAC-SHA512 of the raw request body, computed with the same secret API key used for outbound calls (Paystack has no separate webhook secret). Verify this before trusting anything in the payload. Then, rather than trusting the webhook alone, make a direct server-side call to Paystack's Verify Transaction endpoint using the reference — this belt-and-braces check protects against a forged or replayed webhook. Only mark `RechargeRequest.payment_status = paid` once both agree.
4. **Idempotency:** `payment_reference` is unique and indexed; a duplicate webhook for the same reference is detected and no-op'd, never double-processed.
5. There's an existing `paystack-django` package (`djpaystack`) covering initialization, verification, signature-checked webhooks, and Django signals — worth evaluating as a starting point rather than writing the raw HTTP calls by hand, though it's not required.

*(Note: Paystack's checkout also offers "Pay with OPay" as one of its channels, alongside cards/transfer/USSD — meaning some OPay-wallet reach comes along for free through this single integration, without a separate OPay merchant relationship. Just an FYI, not a requirement.)*

---

## 11. Security Requirements

### 11.1 Authentication & authorization

- **Tenants:** phone number + OTP, no password — accessibility matters more than a login form here. OTPs expire quickly (e.g. 5 minutes) and are rate-limited per phone number.
- **Staff:** username/password + mandatory MFA (TOTP), given staff view fulfilment queues and enter tokens. Role-based access (metering staff vs. admin) via Django's permission framework.
- Every staff/admin endpoint sits behind auth + explicit permission checks.

### 11.2 Webhook security

- The payment webhook is signature-verified before any processing; invalid signatures are logged and rejected with no side effects. Consider also checking the source IP against the gateway's published list as a second layer.
- `payment_reference` is unique and indexed — duplicate deliveries are detected and no-op'd.
- Verify server-side against the gateway's own "check transaction" API rather than trusting the webhook payload alone (§10, step 3).

### 11.3 Token confidentiality

- The recharge token is financially equivalent to cash and meter-specific. Store it encrypted at rest (e.g. Fernet, with the key from a secrets manager or environment variable — never in source control), not as plaintext.
- Never log the token value in plaintext, including in error logs or crash-reporting breadcrumbs.
- Delivered over TLS (HTTPS, and SMS — accept that SMS isn't end-to-end encrypted, an inherent trade-off, and one reason to also surface it in-app).

### 11.4 Data protection (NDPA 2023)

Meter numbers, names, and phone numbers make this platform a data controller under Nigeria's federal data protection law, in force since June 2023, which set up the Nigeria Data Protection Commission (NDPC) as an independent regulator. In practice: collect only what's needed, restrict staff access to what their role requires, encrypt personal data at rest where practical, define a retention/deletion policy up front, and revisit registration obligations with FAAN's legal side as usage scales.

### 11.5 Fraud & abuse prevention

- A recharge can only be requested against an `approved` tenant — no ad hoc meter numbers.
- Rate-limit sign-up, OTP requests, and recharge initiation per phone number/IP.
- Flag unusually large or frequent recharges for manual review instead of auto-approving everything.

### 11.6 Secrets & infrastructure

- Payment gateway keys, encryption keys, and SMS credentials come from environment variables or a secrets manager — never hardcoded, never committed.
- Enforce HTTPS/HSTS, secure + HttpOnly cookies, Django's CSRF protection on every form.
- Brute-force protection (e.g. django-axes) on staff login.
- Keep dependencies current; run a vulnerability scan (e.g. pip-audit) in CI.

### 11.7 Audit logging

Every sensitive action — sign-up approval/rejection, token entry, webhook received, delivery attempt — writes an `AuditLogEntry` with actor, action, target, and timestamp.

---

## 12. Non-Functional Requirements

- **Availability:** standard cloud-hosting uptime (99%+) is a reasonable target for pilot scale.
- **Performance:** the payment redirect and webhook processing should feel instant to the tenant — no more than a couple of seconds between paying and seeing "payment confirmed."
- **Observability:** structured logging plus an error tracker (e.g. Sentry) from day one; a lightweight ops view showing pending fulfilments and failed deliveries.
- **Scalability:** the tenant/recharge model doesn't hardcode MMIA — extending to other FAAN airports later is a config change, not a rebuild.
- **Demo-mode clarity:** whenever `TOKEN_PROVIDER=mock` is active, the UI visibly flags "Demo Mode" (banner or similar) so nobody — including whoever you're pitching to — mistakes a placeholder for a working recharge token.

---

## 13. Admin/Staff Dashboard Requirements

- Approval queue (pending sign-ups, approve/reject + reason).
- Fulfilment queue (paid, awaiting token) with a token-entry form.
- Exceptions queue (payment issues needing manual resolution).
- Basic reporting: recharges by day/amount, average time-to-fulfilment, failed deliveries.

---

## 14. Build Sequence

1. **Milestone 1 — Core platform (MVP/demo).** Tenant model, sign-up/approval flow, staff auth, the `RechargeRequest` state machine, `MockTokenProvider` for token generation, SMS delivery. This is what you present — the full flow runs end-to-end without needing a real generated token for every demo run.
2. **Milestone 2 — Payment integration.** Wire up Paystack (sandbox): initialize, redirect, webhook + server-side verify, idempotent processing.
3. **Milestone 3 — Production readiness.** Swap sandbox payment credentials for FAAN's own (once granted); swap `MockTokenProvider` for manual staff entry or a real API integration (once access exists) — the mock must never run against real tenant payments; full security review, NDPA compliance pass, Remita reconciliation wiring (A5.5).

---

## 15. Risks & Open Items

- **Token generation is the ceiling on scale** until/unless FAAN grants API access to the existing vending system.
- **Production payment + Remita access both depend on FAAN sign-off** (A5.3). Without it, this stays a pitch-ready pilot rather than a system handling real tenant money.
- **NDPA obligations scale with usage** — revisit with FAAN's legal/compliance side before a real production launch.
- **Accessibility gap, by design.** Cutting POS/agent access means tenants without a smartphone or a digital payment method aren't served by this version — worth a conscious decision on whether that's an acceptable v1 trade-off or something to revisit once the core platform proves out.
- **The mock token provider is for demos only.** It produces no functioning token — critical that it stays clearly labeled (§12) and is never left running against real tenant payments once this moves past a pitch.

---

## 16. Glossary

- **RRR** — Remita Retrieval Reference: the reconciliation reference Remita issues per government payment, tracked against the Treasury Single Account.
- **STS** — Standard Transfer Specification: the global cryptographic standard prepaid meters use, ensuring a token can only be used by the one meter it was generated for. This is why token generation can't be reimplemented outside FAAN's licensed vending system.
- **SGC** — Supply Group Code: identifies which utility/vending system a meter belongs to.
- **MDA** — Ministry, Department or Agency — Nigerian federal government terminology; FAAN is one.
- **NDPC** — Nigeria Data Protection Commission, the regulator established under the NDPA 2023.

---

## Sources Consulted

- Nigeria Data Protection Act 2023 — overview: https://kpmg.com/ng/en/insights/2023/09/the-nigeria-data-protection-act--2023.html
- STS (Standard Transfer Specification) overview: https://phed.com.ng/?p=10100 and https://www.sts.org.za/STS-EDITION2-BROCHURE-A5.pdf
- Paystack webhook/transaction flow: https://paystack-django.readthedocs.io/en/stable/webhooks.html and https://paystack-django.readthedocs.io/en/stable/

*(Fintech API docs move fast — re-verify exact endpoint contracts against the live docs at integration time, not just this PRD.)*
