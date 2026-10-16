from django.core.exceptions import PermissionDenied


from django.db import models, transaction

class HRWorkflowQuerySet(models.QuerySet):
    """Keep admin/import/bulk mutation on the same guarded model seam."""
    @transaction.atomic
    def delete(self):
        from payroll.services.hr_workflow import guard_delete
        for record in self.select_for_update():
            guard_delete(record)
        return super().delete()

    @transaction.atomic
    def update(self, **kwargs):
        records = list(self.select_for_update())
        for record in records:
            for name, value in kwargs.items():
                if hasattr(value, "resolve_expression"):
                    raise PermissionDenied("Workflow fields cannot use bulk expressions.")
                setattr(record, name, value)
            record.save(update_fields=list(kwargs))
        return len(records)

    @transaction.atomic
    def bulk_update(self, objs, fields, batch_size=None):
        for record in objs:
            record.save(update_fields=fields)
        return len(objs)

    @transaction.atomic
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("ignore_conflicts") or kwargs.get("update_conflicts"):
            raise PermissionDenied("Conflicting workflow imports require explicit edits.")
        for record in objs:
            record.save(force_insert=True)
        return objs

class HRWorkflowManager(models.Manager.from_queryset(HRWorkflowQuerySet)):
    def get_queryset(self):
        queryset = super().get_queryset()
        if any(f.name == "deleted_at" for f in self.model._meta.fields):
            queryset = queryset.filter(deleted_at__isnull=True)
        return queryset


class SalaryTermsQuerySet(models.QuerySet):
    """Apply salary model guards to public bulk changes of pay terms."""
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise PermissionDenied("Salary records cannot be replaced through bulk conflict updates.")
        return super().bulk_create(objs, **kwargs)

    def _sensitive_fields(self):
        if self.model._meta.label_lower == 'payroll.employeeprofile':
            return {'employee_pay', 'employee_pay_id'}
        return {'basic_salary', 'is_housing', 'is_nhif', 'nhf_scheme'}

    @transaction.atomic
    def update(self, **kwargs):
        if not self._sensitive_fields().intersection(kwargs):
            return super().update(**kwargs)
        records = list(self.select_for_update())
        for record in records:
            for name, value in kwargs.items():
                if hasattr(value, 'resolve_expression'):
                    raise PermissionDenied('Salary changes cannot use bulk expressions.')
                setattr(record, name, value)
            record.save(update_fields=list(kwargs))
        return len(records)

    @transaction.atomic
    def bulk_update(self, objs, fields, batch_size=None):
        if not self._sensitive_fields().intersection(fields):
            return super().bulk_update(objs, fields, batch_size=batch_size)
        records = list(objs)
        for record in records:
            record.save(update_fields=fields)
        return len(records)
