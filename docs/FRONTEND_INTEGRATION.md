# Django Integration

Replace the mock actions in `static/js/app.js` with calls to the API from PRD v2.0.

Core endpoints:
- POST /api/v1/auth/register/
- POST /api/v1/auth/login/
- POST /api/v1/auth/verify-otp/
- GET /api/v1/meters/
- POST /api/v1/meters/
- POST /api/v1/meters/validate/
- POST /api/v1/recharges/
- GET /api/v1/recharges/{reference}/
- POST /api/v1/payments/initiate/
- GET /api/v1/payments/{reference}/
- GET /api/v1/receipts/{reference}/

Staff:
- GET /api/v1/staff/recharges/pending/
- GET /api/v1/staff/recharges/{reference}/
- POST /api/v1/staff/recharges/{reference}/token/

Important:
1. Never trust browser payment-return status.
2. Backend payment verification is authoritative.
3. Backend RBAC is authoritative.
4. Do not expose provider secrets in JS.
5. Do not log plaintext tokens.
6. Frontend fee calculations are display-only; backend total is authoritative.
7. Keep payment and vending status separate.
