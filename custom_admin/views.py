from django.shortcuts import render, Http404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.apps import apps
from django.urls import reverse_lazy
from django import forms
from django.contrib import messages
from django.http import Http404 # Already imported via shortcut, but good for clarity

# Model imports
# from payroll.models.employee_profile import EmployeeProfile, Department # Already imported in apps.py, but good for clarity if needed directly
# from payroll.models.payroll import Payroll, PayVar, LeaveRequest, IOU, Allowance, Deduction, LeavePolicy, PayT # Already imported in apps.py for registration
from payroll.models.employee_profile import Department
from payroll.models.payroll import Allowance, Deduction, LeavePolicy, PayT # Explicit import for model usage

# Generic Base Views (already defined in this file)
# class AdminUserPassesTestMixin(UserPassesTestMixin): ...
# class BaseListView(AdminUserPassesTestMixin, LoginRequiredMixin, ListView): ...
# class BaseCreateView(AdminUserPassesTestMixin, LoginRequiredMixin, CreateView): ...
# class BaseUpdateView(AdminUserPassesTestMixin, LoginRequiredMixin, UpdateView): ...
# class BaseDeleteView(AdminUserPassesTestMixin, LoginRequiredMixin, DeleteView): ...


class AdminUserPassesTestMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff

@staff_member_required
def dashboard(request):
    total_employees = EmployeeProfile.objects.count()
    # Assuming LeaveRequest status choices include 'PENDING' (or similar)
    pending_leave_requests_count = LeaveRequest.objects.filter(status='PENDING').count()
    # Assuming IOU status choices include 'PENDING' (or similar)
    pending_iou_approvals_count = IOU.objects.filter(status='PENDING').count()
    # Payroll model has status with default 'active'
    active_payroll_count = Payroll.objects.filter(status='active').count()

    # Recent Activities
    # EmployeeProfile has 'created' (DateTimeField)
    recent_employees = EmployeeProfile.objects.order_by('-created')[:5]
    # LeaveRequest has 'created_at' (DateTimeField)
    recent_leave_requests = LeaveRequest.objects.order_by('-created_at')[:5]
    # IOU has 'created_at' (DateField) - adjust if it's DateTimeField for more precision
    recent_ious = IOU.objects.order_by('-created_at')[:5]

    context = {
        'total_employees': total_employees,
        'pending_leave_requests_count': pending_leave_requests_count,
        'pending_iou_approvals_count': pending_iou_approvals_count,
        'active_payroll_count': active_payroll_count,
        'recent_employees': recent_employees,
        'recent_leave_requests': recent_leave_requests,
        'recent_ious': recent_ious,
        'dashboard_title': 'Admin Dashboard Overview'
    }
    return render(request, 'custom_admin/dashboard.html', context)

class BaseListView(AdminUserPassesTestMixin, LoginRequiredMixin, ListView):
    template_name = 'custom_admin/generic_list.html'
    paginate_by = 25
    model = None
    app_label = None
    model_name = None
    model_verbose_name = None
    model_verbose_name_plural = None
    model_fields = []
    search_fields = []  # Fields to search across
    list_filter_fields = [] # Fields to enable filtering on

    def dispatch(self, request, *args, **kwargs):
        self.app_label = kwargs.get('app_label')
        self.model_name = kwargs.get('model_name')
        try:
            self.model = apps.get_model(self.app_label, self.model_name)
        except LookupError:
            raise Http404(f"Model {self.app_label}.{self.model_name} not found.")

        self.model_verbose_name = self.model._meta.verbose_name
        self.model_verbose_name_plural = self.model._meta.verbose_name_plural

        # Get concrete fields that are not many-to-many or one-to-many
        self.model_fields = [
            field.name for field in self.model._meta.get_fields()
            if field.concrete and not field.many_to_many and not field.one_to_many and not field.one_to_one
        ]
        # A more refined field list might exclude primary keys or certain other field types by default,
        # or allow customization via the model's admin_config registration.
        # For now, this provides a comprehensive list of direct attributes.

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        if not self.model:
            return self.model.objects.none() # Should not happen if dispatch works
        return self.model.objects.all() # Default, will be modified by search/filter

    def get_queryset(self):
        queryset = super().get_queryset() # Gets self.model.objects.all() or as overridden

        # Search Logic
        search_query = self.request.GET.get('q', '').strip()
        if search_query and hasattr(self, 'search_fields') and self.search_fields:
            from django.db.models import Q
            q_objects = Q()
            for field_name in self.search_fields:
                q_objects |= Q(**{f'{field_name}__icontains': search_query})
            queryset = queryset.filter(q_objects).distinct()

        # Filter Logic
        if hasattr(self, 'list_filter_fields'):
            for field_name in self.list_filter_fields:
                filter_value = self.request.GET.get(field_name)
                if filter_value: # Ensure filter_value is not empty or None
                    queryset = queryset.filter(**{field_name: filter_value})
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_label'] = self.app_label
        context['model_name'] = self.model_name
        context['model_verbose_name'] = self.model_verbose_name
        context['model_verbose_name_plural'] = self.model_verbose_name_plural
        context['model_fields'] = self.model_fields # These are for table columns
        context['title'] = f"{self.model_verbose_name_plural.capitalize()} List"

        # Add search query to context
        context['search_query'] = self.request.GET.get('q', '').strip()

        # Prepare data for filter dropdowns
        filters_data = []
        current_filters = {}
        if hasattr(self, 'list_filter_fields'):
            for field_name in self.list_filter_fields:
                current_filters[field_name] = self.request.GET.get(field_name, '')
                try:
                    model_field = self.model._meta.get_field(field_name)
                    options_list = []
                    if model_field.choices:
                        options_list = list(model_field.choices)
                    elif model_field.is_relation and model_field.related_model:
                        related_model = model_field.related_model
                        # Format as (value, display) tuples
                        options_list = [(obj.pk, str(obj)) for obj in related_model.objects.all()]

                    if options_list: # Only add filter if there are options to choose from
                        filters_data.append({
                            'name': field_name,
                            'verbose_name': getattr(model_field, 'verbose_name', field_name).capitalize(),
                            'options': options_list, # Now always a list of (value, display)
                            'current_value': current_filters[field_name]
                        })
                except Exception as e:
                    # Handle cases where field might not be found or is not suitable for this type of filter
                    print(f"Could not prepare filter for {field_name}: {e}")


        context['filters_data'] = filters_data
        context['current_filters'] = current_filters
        context['actions'] = self.get_actions() # Add actions to context
        return context

    def get_actions(self):
        """
        Returns a dictionary of actions.
        Keys are action names (used in POST), values are display names.
        Example: {'delete_selected': 'Delete selected items'}
        """
        return {}

    def perform_action(self, action_name, selected_pks):
        """
        Performs the given action on the items with the given primary keys.
        Should return the number of affected items, or None if messages are handled manually.
        """
        # Base implementation does nothing, or could raise NotImplementedError
        # messages.info(self.request, f"Action '{action_name}' not implemented in BaseListView.")
        return 0

    def post(self, request, *args, **kwargs):
        # Ensure model and other necessary attributes are set up, similar to dispatch
        # This is important because ListView's default post doesn't set these up for us.
        self.app_label = self.kwargs.get('app_label')
        self.model_name = self.kwargs.get('model_name')
        try:
            self.model = apps.get_model(self.app_label, self.model_name)
        except LookupError:
            raise Http404(f"Model {self.app_label}.{self.model_name} not found.")

        # Set other meta attributes that might be used by get_actions or perform_action
        self.model_verbose_name = self.model._meta.verbose_name
        self.model_verbose_name_plural = self.model._meta.verbose_name_plural
        # If get_queryset needs these (it shouldn't if super().get_queryset() is called in perform_action's context)
        # we might need to call self.object_list = self.get_queryset() here.
        # However, perform_action typically works on selected_pks directly.

        action_name = request.POST.get('action')
        selected_pks_str = request.POST.getlist('selected_ids')

        if not action_name:
            messages.warning(request, "No action was selected.")
            return redirect(request.get_full_path() or request.path_info)

        if not selected_pks_str:
            messages.warning(request, "No items were selected for the action.")
            return redirect(request.get_full_path() or request.path_info)

        # Convert PKs to the correct type
        selected_pks = []
        pk_field_to_python = self.model._meta.pk.to_python
        try:
            for pk_str in selected_pks_str:
                selected_pks.append(pk_field_to_python(pk_str))
        except Exception: # Broad exception for conversion errors (e.g., ValueError)
            messages.error(request, f"Invalid item ID found in selection.")
            return redirect(request.get_full_path() or request.path_info)

        available_actions = self.get_actions()
        if action_name not in available_actions:
            messages.error(request, f"Invalid action: '{action_name}'.")
            return redirect(request.get_full_path() or request.path_info)

        # Call perform_action which should be overridden by subclasses
        affected_count = self.perform_action(action_name, selected_pks)

        if affected_count is not None: # Allow perform_action to handle messages by returning None
            action_display_name = available_actions.get(action_name, action_name.replace('_', ' ').title())
            if affected_count > 0:
                messages.success(request, f"Successfully performed action '{action_display_name}' on {affected_count} item(s).")
            else:
                # Provide more nuanced feedback if action was valid but affected 0 items vs. not implemented fully
                # For now, this message covers both.
                messages.info(request, f"Action '{action_display_name}' completed. 0 items were affected.")

        return redirect(request.get_full_path() or request.path_info)


class BaseCreateView(AdminUserPassesTestMixin, LoginRequiredMixin, CreateView):
    template_name = 'custom_admin/generic_form.html'
    model = None
    fields = '__all__'  # Default, can be overridden
    app_label = None
    model_name = None
    model_verbose_name = None

    def dispatch(self, request, *args, **kwargs):
        self.app_label = kwargs.get('app_label')
        self.model_name = kwargs.get('model_name')
        try:
            self.model = apps.get_model(self.app_label, self.model_name)
        except LookupError:
            raise Http404(f"Model {self.app_label}.{self.model_name} not found.")

        self.model_verbose_name = self.model._meta.verbose_name
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        if self.form_class:
            return self.form_class
        else:
            # Dynamically create a ModelForm
            Meta = type('Meta', (object,), {'model': self.model, 'fields': self.fields})
            GeneratedForm = type(f'{self.model_name}ModelForm', (forms.ModelForm,), {'Meta': Meta})
            return GeneratedForm

    def get_success_url(self):
        return reverse_lazy('custom_admin:generic_list', kwargs={'app_label': self.app_label, 'model_name': self.model_name})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_label'] = self.app_label
        context['model_name'] = self.model_name
        context['model_verbose_name'] = self.model_verbose_name
        context['title'] = f"Add {self.model_verbose_name.capitalize()}"
        context['form_action_type'] = "Add"
        return context

class BaseUpdateView(AdminUserPassesTestMixin, LoginRequiredMixin, UpdateView):
    template_name = 'custom_admin/generic_form.html'
    model = None
    fields = '__all__' # Default, can be overridden
    app_label = None
    model_name = None
    model_verbose_name = None

    def dispatch(self, request, *args, **kwargs):
        self.app_label = kwargs.get('app_label')
        self.model_name = kwargs.get('model_name')
        try:
            self.model = apps.get_model(self.app_label, self.model_name)
        except LookupError:
            raise Http404(f"Model {self.app_label}.{self.model_name} not found.")

        self.model_verbose_name = self.model._meta.verbose_name
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        if self.form_class:
            return self.form_class
        else:
            # Dynamically create a ModelForm
            Meta = type('Meta', (object,), {'model': self.model, 'fields': self.fields})
            GeneratedForm = type(f'{self.model_name}ModelForm', (forms.ModelForm,), {'Meta': Meta})
            return GeneratedForm

    def get_success_url(self):
        return reverse_lazy('custom_admin:generic_list', kwargs={'app_label': self.app_label, 'model_name': self.model_name})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_label'] = self.app_label
        context['model_name'] = self.model_name
        context['model_verbose_name'] = self.model_verbose_name
        obj_display = str(self.object) if hasattr(self, 'object') and self.object else self.model_verbose_name.capitalize()
        context['title'] = f"Edit {obj_display}"
        context['form_action_type'] = "Update"
        return context

class BaseDeleteView(AdminUserPassesTestMixin, LoginRequiredMixin, DeleteView):
    template_name = 'custom_admin/generic_confirm_delete.html'
    model = None
    app_label = None
    model_name = None
    model_verbose_name = None

    def dispatch(self, request, *args, **kwargs):
        self.app_label = kwargs.get('app_label')
        self.model_name = kwargs.get('model_name')
        try:
            self.model = apps.get_model(self.app_label, self.model_name)
        except LookupError:
            raise Http404(f"Model {self.app_label}.{self.model_name} not found.")

        self.model_verbose_name = self.model._meta.verbose_name
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('custom_admin:generic_list', kwargs={'app_label': self.app_label, 'model_name': self.model_name})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_label'] = self.app_label
        context['model_name'] = self.model_name
        context['model_verbose_name'] = self.model_verbose_name
        context['title'] = f"Delete {self.model_verbose_name.capitalize()}"
        # self.object is available by default in DeleteView context
        return context

# EmployeeProfile Specific Views
class EmployeeProfileListView(BaseListView):
    model = EmployeeProfile
    search_fields = ['first_name', 'last_name', 'email', 'emp_id']
    list_filter_fields = ['department', 'status', 'job_title'] # Added job_title

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Override model_fields for the EmployeeProfile list template columns
        context['model_fields'] = ['emp_id', 'first_name', 'last_name', 'email', 'job_title', 'status']
        # The base get_context_data in BaseListView handles adding filters_data
        return context

class EmployeeProfileCreateView(BaseCreateView):
    model = EmployeeProfile
    fields = [
        'first_name', 'last_name', 'email', 'department', 'job_title',
        'contract_type', 'date_of_employment', 'date_of_birth', 'gender',
        'phone', 'address', 'employee_pay', 'pension_rsa', 'bank',
        'bank_account_name', 'bank_account_number', 'photo',
        'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone',
        'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'status'
    ]
    # Note: 'user' field is typically handled separately (e.g., linked to request.user or auto-created)
    # 'emp_id', 'slug' are likely auto-generated or set programmatically

class EmployeeProfileUpdateView(BaseUpdateView):
    model = EmployeeProfile
    fields = [
        'first_name', 'last_name', 'email', 'department', 'job_title',
        'contract_type', 'date_of_employment', 'date_of_birth', 'gender',
        'phone', 'address', 'employee_pay', 'pension_rsa', 'bank',
        'bank_account_name', 'bank_account_number', 'photo',
        'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone',
        'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'status'
    ]

class EmployeeProfileDeleteView(BaseDeleteView):
    model = EmployeeProfile

# Payroll Specific Views
class PayrollListView(BaseListView):
    model = Payroll
    search_fields = ['id', 'status']
    list_filter_fields = ['status']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'basic_salary', 'gross_income', 'payee', 'status', 'timestamp']
        # BaseListView's get_context_data already populates app_label, model_name, verbose_name, etc.
        # and sets the title based on model_verbose_name_plural.
        return context

class PayrollCreateView(BaseCreateView):
    model = Payroll
    fields = ['basic_salary', 'water_rate', 'status']

class PayrollUpdateView(BaseUpdateView):
    model = Payroll
    fields = ['basic_salary', 'water_rate', 'status']

class PayrollDeleteView(BaseDeleteView):
    model = Payroll

# PayVar Specific Views
class PayVarListView(BaseListView):
    model = PayVar
    search_fields = ['id', 'pays__first_name', 'pays__last_name', 'pays__email', 'status']
    list_filter_fields = ['status', 'pays', 'allowance_id', 'deduction_id', 'is_housing', 'is_nhif']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'pays', 'allowance_id', 'deduction_id', 'is_housing', 'is_nhif', 'status', 'netpay']
        # BaseListView's get_context_data already populates app_label, model_name, verbose_name, etc.
        # and sets the title based on model_verbose_name_plural.
        return context

class PayVarCreateView(BaseCreateView):
    model = PayVar
    fields = ['pays', 'allowance_id', 'deduction_id', 'is_housing', 'is_nhif', 'status']

class PayVarUpdateView(BaseUpdateView):
    model = PayVar
    fields = ['pays', 'allowance_id', 'deduction_id', 'is_housing', 'is_nhif', 'status']

class PayVarDeleteView(BaseDeleteView):
    model = PayVar

# LeaveRequest Specific Views
class LeaveRequestListView(BaseListView):
    model = LeaveRequest
    list_filter_fields = ['status', 'leave_type', 'employee']
    search_fields = ['employee__first_name', 'employee__last_name', 'leave_type', 'status'] # Added search_fields

    def get_actions(self):
        return {
            'approve_selected': 'Mark Selected as Approved',
            'reject_selected': 'Mark Selected as Rejected',
        }

    def perform_action(self, action_name, selected_pks):
        # self.model is already set to LeaveRequest by the view's configuration
        queryset = self.model.objects.filter(pk__in=selected_pks)
        updated_count = 0

        # Define valid target statuses for actions
        valid_statuses_for_action = ['PENDING'] # Example: only act on PENDING requests

        if action_name == 'approve_selected':
            # Filter for requests that can be approved
            approvable_requests = queryset.filter(status__in=valid_statuses_for_action)
            updated_count = approvable_requests.update(status='APPROVED')

            # Notify if some selected items were not in a state to be approved
            if updated_count < queryset.count(): # queryset.count() is the number of initially selected items
                skipped_count = queryset.count() - updated_count
                messages.warning(self.request, f"{skipped_count} selected item(s) were not in a state to be approved (e.g., not PENDING) and were skipped.")

        elif action_name == 'reject_selected':
            # Filter for requests that can be rejected
            rejectable_requests = queryset.filter(status__in=valid_statuses_for_action)
            updated_count = rejectable_requests.update(status='REJECTED')

            # Notify if some selected items were not in a state to be rejected
            if updated_count < queryset.count():
                skipped_count = queryset.count() - updated_count
                messages.warning(self.request, f"{skipped_count} selected item(s) were not in a state to be rejected (e.g., not PENDING) and were skipped.")
        else:
            # This case should ideally not be reached if action_name is validated in BaseListView.post
            # but as a safeguard:
            # The message for unknown action is already handled by BaseListView.post
            # Here, we just ensure we return 0 if this specific view doesn't handle an action
            # that somehow passed validation (e.g. if get_actions was dynamically changed by another mixin)
            return 0

        return updated_count

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'employee', 'leave_type', 'start_date', 'end_date', 'status', 'created_at']
        return context

class LeaveRequestCreateView(BaseCreateView):
    model = LeaveRequest
    fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason', 'status']

class LeaveRequestUpdateView(BaseUpdateView):
    model = LeaveRequest
    fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason', 'status']

class LeaveRequestDeleteView(BaseDeleteView):
    model = LeaveRequest

# IOU Specific Views
class IOUListView(BaseListView):
    model = IOU
    list_filter_fields = ['status', 'employee_id', 'payment_method']
    search_fields = ['employee_id__first_name', 'employee_id__last_name', 'status', 'reason'] # Added search_fields

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'employee_id', 'amount', 'tenor', 'status', 'payment_method', 'created_at']
        return context

class IOUCreateView(BaseCreateView):
    model = IOU
    fields = ['employee_id', 'amount', 'tenor', 'reason', 'interest_rate', 'payment_method', 'status', 'approved_at']

class IOUUpdateView(BaseUpdateView):
    model = IOU
    fields = ['employee_id', 'amount', 'tenor', 'reason', 'interest_rate', 'payment_method', 'status', 'approved_at', 'due_date']

class IOUDeleteView(BaseDeleteView):
    model = IOU

# Department Specific Views
class DepartmentListView(BaseListView):
    model = Department
    search_fields = ['name', 'description']
    list_filter_fields = [] # No obvious choice fields on Department model for simple filtering

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'name', 'description']
        # BaseListView already sets: app_label, model_name, verbose_name, verbose_name_plural, title
        return context

class DepartmentCreateView(BaseCreateView):
    model = Department
    fields = ['name', 'description']

class DepartmentUpdateView(BaseUpdateView):
    model = Department
    fields = ['name', 'description']

class DepartmentDeleteView(BaseDeleteView):
    model = Department

# Allowance Specific Views
class AllowanceListView(BaseListView):
    model = Allowance
    search_fields = ['name']
    list_filter_fields = ['name']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'name', 'percentage', 'amount']
        # BaseListView already sets: app_label, model_name, verbose_name, verbose_name_plural, title
        return context

class AllowanceCreateView(BaseCreateView):
    model = Allowance
    fields = ['name', 'percentage', 'amount']

class AllowanceUpdateView(BaseUpdateView):
    model = Allowance
    fields = ['name', 'percentage', 'amount']

class AllowanceDeleteView(BaseDeleteView):
    model = Allowance

# Deduction Specific Views
class DeductionListView(BaseListView):
    model = Deduction
    search_fields = ['name']
    list_filter_fields = ['name']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'name', 'percentage']
        # BaseListView already sets: app_label, model_name, verbose_name, verbose_name_plural, title
        return context

class DeductionCreateView(BaseCreateView):
    model = Deduction
    fields = ['name', 'percentage']

class DeductionUpdateView(BaseUpdateView):
    model = Deduction
    fields = ['name', 'percentage']

class DeductionDeleteView(BaseDeleteView):
    model = Deduction

# LeavePolicy Specific Views
class LeavePolicyListView(BaseListView):
    model = LeavePolicy
    search_fields = ['leave_type']
    list_filter_fields = ['leave_type']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'leave_type', 'max_days']
        # BaseListView already sets: app_label, model_name, verbose_name, verbose_name_plural, title
        return context

class LeavePolicyCreateView(BaseCreateView):
    model = LeavePolicy
    fields = ['leave_type', 'max_days']

class LeavePolicyUpdateView(BaseUpdateView):
    model = LeavePolicy
    fields = ['leave_type', 'max_days']

class LeavePolicyDeleteView(BaseDeleteView):
    model = LeavePolicy

from .forms import PayTAdminForm # Import the new form

# PayT Specific Views
class PayTListView(BaseListView):
    model = PayT
    search_fields = ['name', 'slug', 'paydays']
    list_filter_fields = ['is_active', 'closed']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_fields'] = ['id', 'name', 'slug', 'paydays', 'is_active', 'closed']
        # BaseListView already sets: app_label, model_name, verbose_name, verbose_name_plural, title
        return context

class PayTCreateView(BaseCreateView):
    model = PayT
    form_class = PayTAdminForm # Use custom form
    # fields attribute is now inherited from PayTAdminForm

class PayTUpdateView(BaseUpdateView):
    model = PayT
    form_class = PayTAdminForm # Use custom form
    # fields attribute is now inherited from PayTAdminForm

class PayTDeleteView(BaseDeleteView):
    model = PayT
