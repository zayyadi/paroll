"""Tenant boundaries and workflow-owned fields for domain admin screens."""
from django.core.exceptions import PermissionDenied
from .access import selected_company
from .guards import CONTROLLED_FIELDS
from .permissions import require_company_authority


class CompanyWorkflowAdminMixin:
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if hasattr(self.model, 'all_objects'):
            queryset = self.model.all_objects.all()
        try:
            company = selected_company(request.user)
        except PermissionDenied:
            return queryset.none()
        return queryset.filter(company=company)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related = db_field.remote_field.model
        try:
            company = selected_company(request.user)
        except PermissionDenied:
            kwargs['queryset'] = related._default_manager.none()
        else:
            if related._meta.label_lower == 'company.company':
                kwargs['queryset'] = related._default_manager.filter(pk=company.pk)
            elif any(field.name == 'company' for field in related._meta.fields):
                kwargs['queryset'] = related._default_manager.filter(company=company)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if self.model._meta.label_lower in CONTROLLED_FIELDS:
            fields.extend(CONTROLLED_FIELDS[self.model._meta.label_lower])
            fields.extend(field.name for field in self.model._meta.fields if field.name in {
                'requested_by', 'approved_by', 'approved_at', 'posted_by', 'posted_at',
                'filed_by', 'filed_at', 'closed_by', 'closed_at', 'approval_request'})
        return tuple(dict.fromkeys(fields))

    def has_import_permission(self, request):
        if self.model._meta.label_lower in CONTROLLED_FIELDS:
            return False
        parent = getattr(super(), 'has_import_permission', None)
        return parent(request) if parent else False

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            rules = CONTROLLED_FIELDS.get(self.model._meta.label_lower, {})
            if any(getattr(obj, field) in states for field, states in rules.items()):
                return False
            from django.contrib.contenttypes.models import ContentType
            from .models import ApprovalRequest
            if ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk, status='PENDING').exists():
                return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        company = selected_company(request.user)
        operation = 'change' if change else 'add'
        require_company_authority(request.user, company, f'{obj._meta.app_label}.{operation}_{obj._meta.model_name}')
        if obj.company_id != company.pk:
            raise PermissionDenied('Admin changes must belong to the selected company.')
        return super().save_model(request, obj, form, change)
