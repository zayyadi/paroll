from django.shortcuts import render, Http404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.apps import apps
from django.urls import reverse_lazy
from django import forms

# Model imports
from payroll.models.employee_profile import EmployeeProfile
from payroll.models.payroll import Payroll, PayVar # Import PayVar model

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
    return render(request, 'custom_admin/dashboard.html')

class BaseListView(AdminUserPassesTestMixin, LoginRequiredMixin, ListView):
    template_name = 'custom_admin/generic_list.html'
    paginate_by = 25
    model = None
    app_label = None
    model_name = None
    model_verbose_name = None
    model_verbose_name_plural = None
    model_fields = []

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
        return self.model.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_label'] = self.app_label
        context['model_name'] = self.model_name
        context['model_verbose_name'] = self.model_verbose_name
        context['model_verbose_name_plural'] = self.model_verbose_name_plural
        context['model_fields'] = self.model_fields
        context['title'] = f"{self.model_verbose_name_plural.capitalize()} List"
        return context

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Override model_fields for the EmployeeProfile list template
        context['model_fields'] = ['emp_id', 'first_name', 'last_name', 'email', 'job_title', 'status']
        # Ensure other necessary context from BaseListView is preserved
        # The super().get_context_data() already sets title based on model's verbose_name_plural
        # It also sets app_label, model_name, verbose_name, verbose_name_plural
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
