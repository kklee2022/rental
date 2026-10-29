from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from core.models import record_audit

from .models import Role
from .permissions import HasTenantMembership, has_role


class AuditedTenantModelViewSet(ModelViewSet):
    """Tenant-bound CRUD with role checks and generic audit events."""

    write_roles = (Role.RENTAL,)
    queryset_model: Any = None
    queryset_select_related: tuple[str, ...] = ()
    queryset_prefetch_related: tuple[str, ...] = ()
    read_permission_classes = [IsAuthenticated, HasTenantMembership]

    def get_queryset(self):
        request = getattr(self, "request", None)
        if getattr(request, "tenant", None) is None:
            return self.queryset_model._base_manager.none()
        return (
            self.queryset_model.objects.select_related(*self.queryset_select_related)
            .prefetch_related(*self.queryset_prefetch_related)
            .all()
        )

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            permission_classes = self.read_permission_classes
        else:
            permission_classes = [IsAuthenticated, has_role(*self.write_roles)]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        extra = {}
        if any(
            field.name == "created_by" for field in serializer.Meta.model._meta.fields
        ):
            extra["created_by"] = self.request.user
        instance = serializer.save(**extra)
        record_audit(
            f"{instance._meta.model_name}.created",
            actor=self.request.user,
            obj=instance,
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        record_audit(
            f"{instance._meta.model_name}.updated",
            actor=self.request.user,
            obj=instance,
            changed_fields=sorted(serializer.validated_data),
        )

    def perform_destroy(self, instance):
        object_id = instance.pk
        model_name = instance._meta.model_name
        instance.delete()
        record_audit(
            f"{model_name}.deleted",
            actor=self.request.user,
            object_id=str(object_id),
        )
