from django.conf import settings


def demo_mode(request):
    return {"demo_mode": settings.TOKEN_PROVIDER == "mock"}
