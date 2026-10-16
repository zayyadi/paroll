from django.contrib import admin
from .models import ApprovalRequest, ApprovalDecision, ApprovalEvent, ApprovalPolicy
from .access import visible_source_requests, selected_company, can_manage_policies
from .permissions import user_in_company


class ReadOnlyWorkflowAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        visible = visible_source_requests(request.user)
        if self.model == ApprovalRequest:
            return queryset.filter(pk__in=visible.values("pk"))
        if self.model == ApprovalPolicy:
            return (
                queryset.filter(company=selected_company(request.user))
                if can_manage_policies(request.user, selected_company(request.user))
                else queryset.none()
            )
        return queryset.filter(request_id__in=visible.values("pk"))

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return super().has_view_permission(request, obj)
        return self.get_queryset(request).filter(
            pk=obj.pk
        ).exists() and super().has_view_permission(request, obj)


for model in (ApprovalRequest, ApprovalDecision, ApprovalEvent, ApprovalPolicy):
    admin.site.register(model, ReadOnlyWorkflowAdmin)
