from django.urls import path
from .views import (
    LoginOTPVerifyView, LoginView, LogoutView, MeView, PasswordResetConfirmView, PasswordResetRequestView,
    PaymentWebhookView, RechargeCreateView,
    RechargeListView, RechargeStatusView, TenantRegisterView, TenantVerifyOTPView,
    TenantResendOTPView,
)

urlpatterns = [
    path('tenants/register', TenantRegisterView.as_view(), name='tenant-register'),
    path('tenants/verify-otp', TenantVerifyOTPView.as_view(), name='tenant-verify-otp'),
    path('tenants/resend-otp', TenantResendOTPView.as_view(), name='tenant-resend-otp'),
    path('auth/login', LoginView.as_view(), name='login'),
    path('auth/verify-login-otp', LoginOTPVerifyView.as_view(), name='verify-login-otp'),
    path('auth/password-reset/request', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/confirm', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/logout', LogoutView.as_view(), name='logout'),
    path('auth/me', MeView.as_view(), name='me'),
    path('recharge/', RechargeCreateView.as_view(), name='recharge-create'),
    path('recharge/history', RechargeListView.as_view(), name='recharge-history'),
    path('recharge/<uuid:recharge_id>/', RechargeStatusView.as_view(), name='recharge-status'),
    path('webhooks/payments/', PaymentWebhookView.as_view(), name='payment-webhook'),
]
