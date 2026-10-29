from django.urls import path

from . import views

urlpatterns = [
    path("", views.staff_dashboard, name="staff-dashboard"),
    path("queue/approvals", views.approval_queue, name="staff-approval-queue"),
    path("queue/approvals/<uuid:tenant_id>", views.approval_detail, name="staff-approval-detail"),
    path("queue/approvals/<uuid:tenant_id>/approve", views.approve_tenant, name="staff-approve-tenant"),
    path("queue/approvals/<uuid:tenant_id>/reject", views.reject_tenant, name="staff-reject-tenant"),
    path("queue/fulfilment", views.fulfilment_queue, name="staff-fulfilment-queue"),
    path("queue/exceptions", views.exceptions_queue, name="staff-exceptions-queue"),
    path("transactions/<uuid:recharge_id>", views.transaction_detail, name="staff-transaction-detail"),
    path("fulfilment/<uuid:recharge_id>/enter-token", views.enter_token, name="staff-enter-token"),
    path("fulfilment/<uuid:recharge_id>/generate-token", views.generate_token, name="staff-generate-token"),
    path("admin/staff", views.staff_management, name="staff-management"),
    path("admin/audit", views.audit_logs, name="staff-audit"),
    path("reports", views.reports, name="staff-reports"),
]
