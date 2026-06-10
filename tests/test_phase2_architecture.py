from importlib import import_module

from django.test import SimpleTestCase
from django.urls import reverse, resolve


class Phase2ArchitectureTests(SimpleTestCase):
    def test_employee_view_modules_use_phase2_names(self):
        expected_symbols = {
            "payroll.views.employees": ["employee_list", "add_employee", "employee"],
            "payroll.views.attendance": ["attendance_my_day", "attendance_clock"],
            "payroll.views.documents": ["my_documents", "acknowledge_document"],
            "payroll.views.assets": ["my_assets", "return_asset"],
            "payroll.views.performance": ["my_performance", "performance_overview"],
            "payroll.views.surveys": ["my_surveys", "submit_survey"],
            "payroll.views.learning": ["my_learning", "complete_learning_course"],
        }

        for module_name, symbols in expected_symbols.items():
            module = import_module(module_name)
            for symbol in symbols:
                self.assertTrue(hasattr(module, symbol), f"{module_name}.{symbol} missing")

    def test_forms_can_be_imported_from_phase2_modules_and_package(self):
        expected_symbols = {
            "payroll.forms.employee_forms": ["EmployeeProfileForm", "EmployeeProfileUpdateForm"],
            "payroll.forms.hiring_forms": ["HiringRequisitionForm", "HiringCandidateForm"],
            "payroll.forms.leave_forms": ["LeaveRequestForm", "LeavePolicyForm"],
            "payroll.forms.payroll_forms": ["PayrollForm", "PayrollRunForm"],
            "payroll.forms.attendance_forms": [],
        }

        forms_package = import_module("payroll.forms")
        for module_name, symbols in expected_symbols.items():
            module = import_module(module_name)
            for symbol in symbols:
                self.assertTrue(hasattr(module, symbol), f"{module_name}.{symbol} missing")
                self.assertIs(getattr(forms_package, symbol), getattr(module, symbol))

    def test_discipline_views_are_served_from_payroll_discipline(self):
        expected_routes = {
            "payroll:disciplinary_system": "disciplinary_system_view",
            "payroll:discipline_case_list": "DisciplinaryCaseListView",
            "payroll:discipline_case_create": "DisciplinaryCaseCreateView",
            "payroll:discipline_case_detail": "DisciplinaryCaseDetailView",
            "payroll:discipline_case_update": "DisciplinaryCaseUpdateView",
            "payroll:discipline_case_start_investigation": (
                "disciplinary_case_start_investigation"
            ),
            "payroll:discipline_evidence_create": "DisciplinaryEvidenceCreateView",
            "payroll:discipline_decision_update": "DisciplinaryDecisionUpdateView",
            "payroll:discipline_sanction_create": "DisciplinarySanctionCreateView",
            "payroll:discipline_appeal_create": "DisciplinaryAppealCreateView",
            "payroll:discipline_appeal_review": "DisciplinaryAppealReviewView",
        }

        module = import_module("payroll.discipline.views")
        routes_without_kwargs = {
            "payroll:disciplinary_system",
            "payroll:discipline_case_list",
            "payroll:discipline_case_create",
        }
        for route_name, symbol in expected_routes.items():
            route_kwargs = {} if route_name in routes_without_kwargs else {"pk": 1}
            resolved = resolve(reverse(route_name, kwargs=route_kwargs))
            expected_view = getattr(module, symbol)
            if hasattr(expected_view, "as_view"):
                self.assertEqual(resolved.func.view_class, expected_view)
            else:
                self.assertIs(resolved.func, expected_view)
