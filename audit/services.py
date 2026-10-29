from .models import AuditLogEntry


def record_audit(actor, action, target, metadata=None):
    actor_name = "system"
    if actor is not None:
        if hasattr(actor, "username"):
            actor_name = actor.username
        else:
            actor_name = str(actor)
    return AuditLogEntry.objects.create(
        actor=actor_name,
        action=action,
        target=str(target),
        metadata=metadata or {},
    )
