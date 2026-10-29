from django.urls import path

from .views import demo_checkout

urlpatterns = [
    path("demo-checkout/<str:reference>/", demo_checkout, name="demo-checkout"),
]
