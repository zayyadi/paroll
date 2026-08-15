"""
Cross-tenant isolation acceptance matrix.

Acceptance gate for flipping ``ALLOW_DEFAULT_COMPANY_FALLBACK`` off. The four
pillars:

1. Natural-key isolation - the same natural key (payroll run name/slug, pay
   period, employee number) must be able to exist independently in two
   companies, and each company must resolve only its own copy.
2. Zero cross-tenant rows - any query/aggregate scoped to company A must never
   include company B's rows.
3. Tenant-safe caching - cached data must be keyed so one company's cache
   entry can never be served to another.
4. Background-task scoping - background jobs (payslips, notifications, email)
   must process only the data of the company/run they were created for.

The companion matrix document is ``plans/TENANT_ISOLATION_ACCEPTANCE_MATRIX.md``.
"""

from datetime import date
from decimal import Decimal
import threading
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from accounting.models import AccountingPeriod, DisciplinaryCase, FiscalYear, Journal
from payroll.models import (
    BankPaymentFile,
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    PayslipEmailJob,
    RemittanceRecord,
    StatutoryRateVersion,
)
from payroll.services.compliance import compliance_obligations
from payroll.services.notification_service import NotificationCacheService

User = get_user_model()


class TenantIsolationBase(TestCase):
    """
    Two companies holding identical-shaped data: same payroll-run name/slug,
    same pay period, same obligation period - different employees and amounts
    so a leak is detectable by value as well as by identity.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.company_a = Company.objects.create(name="Tenant A")
        self.company_b = Company.objects.create(name="Tenant B")

        self.admin_a = self._make_user(
            "admin-a@example.com", "Admin", "One", self.company_a, superuser=True
        )
        self.admin_b = self._make_user(
            "admin-b@example.com", "Admin", "Two", self.company_b, superuser=True
        )

        # Distinct names in the base fixture; the caching tests create their
        # own same-named employees to exercise the key-collision contract.
        self.emp_a = self._make_employee(
            self.company_a, "ada-a@example.com", "Ada", "Ade", "A-001",
            basic_salary=Decimal("120000.00"),
        )
        self.emp_b = self._make_employee(
            self.company_b, "bola-b@example.com", "Bola", "Bello", "B-001",
            basic_salary=Decimal("200000.00"),
        )

        # Same natural key (name, slug "pay-period-2026-06", period) in both.
        self.run_a = self._make_run(self.company_a, self.emp_a, "June 2026 Payroll")
        self.run_b = self._make_run(self.company_b, self.emp_b, "June 2026 Payroll")

        # Same obligation + period in both companies (legal per-company).
        RemittanceRecord.objects.create(
            company=self.company_a,
            obligation="paye",
            period=date(2026, 6, 1),
            remitted_on=date(2026, 7, 5),
        )
        RemittanceRecord.objects.create(
            company=self.company_b,
            obligation="paye",
            period=date(2026, 6, 1),
            remitted_on=date(2026, 7, 5),
        )

        # Bank payment file per company with the same file name.
        BankPaymentFile.objects.create(
            company=self.company_a,
            payroll_run=self.run_a,
            bank_code="001",
            bank_name="Bank A",
            file_name="salaries.xls",
            total_amount=Decimal("1000.00"),
            total_records=1,
        )
        BankPaymentFile.objects.create(
            company=self.company_b,
            payroll_run=self.run_b,
            bank_code="001",
            bank_name="Bank B",
            file_name="salaries.xls",
            total_amount=Decimal("9000.00"),
            total_records=1,
        )

    def _make_user(self, email, first_name, last_name, company, superuser=False):
        return User.objects.create_user(
            email=email,
            password="testpass123",
            first_name=first_name,
            last_name=last_name,
            company=company,
            active_company=company,
            is_staff=superuser,
            is_superuser=superuser,
        )

    def _make_employee(self, company, email, first_name, last_name, emp_id, basic_salary):
        user = self._make_user(email, first_name, last_name, company)
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = company
        employee.status = "active"
        employee.save(update_fields=["company", "status"])
        payroll = Payroll.objects.create(company=company, basic_salary=basic_salary)
        employee.employee_pay = payroll
        employee.emp_id = emp_id
        employee.save(update_fields=["employee_pay", "emp_id"])
        return employee

    def _make_run(self, company, employee, name):
        run = PayrollRun.objects.create(
            company=company,
            name=name,
            paydays=date(2026, 6, 1),
            is_active=True,
        )
        entry = PayrollEntry.objects.create(
            company=company,
            pays=employee,
            status="active",
        )
        PayrollRunEntry.objects.create(payroll_run=run, payroll_entry=entry)
        return run


class NaturalKeyIsolationTests(TenantIsolationBase):
    """Pillar 1: the same natural key is legal and resolves per company."""

    def test_same_payroll_run_name_and_slug_coexist_in_two_companies(self):
        # The same natural key (name, slug) is created independently per
        # company; both rows exist with distinct primary keys.
        self.assertEqual(self.run_a.name, self.run_b.name)
        self.assertEqual(self.run_a.slug, self.run_b.slug)
        self.assertNotEqual(self.run_a.id, self.run_b.id)

        for company, run in [
            (self.company_a, self.run_a),
            (self.company_b, self.run_b),
        ]:
            with self.subTest(company=company.name):
                self.assertEqual(
                    list(PayrollRun.objects.filter(company=company, slug=run.slug)),
                    [run],
                )

    def test_duplicate_payroll_run_name_within_one_company_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayrollRun.objects.create(
                company=self.company_a,
                name="June 2026 Payroll",
                paydays=date(2026, 6, 1),
            )

    def test_pay_period_detail_resolves_only_the_callers_company_run(self):
        # The slug is identical in both companies; the view must return the
        # caller's own run for the same URL.
        self.client.login(email=self.admin_a.email, password="testpass123")
        response = self.client.get(
            reverse("payroll:pay_period_detail", kwargs={"slug": self.run_a.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pay_period"].id, self.run_a.id)

        self.client.login(email=self.admin_b.email, password="testpass123")
        response = self.client.get(
            reverse("payroll:pay_period_detail", kwargs={"slug": self.run_b.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pay_period"].id, self.run_b.id)

    def test_same_employee_number_reusable_across_companies(self):
        """
        ``EmployeeProfile.emp_id`` is unique per company, so two tenants can
        number their employees independently (e.g. both using "A-001").
        """
        user = self._make_user(
            "new-b@example.com", "Ngozi", "B", self.company_b
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company_b
        employee.emp_id = self.emp_a.emp_id  # "A-001" reused in company B
        employee.save(update_fields=["company", "emp_id"])

        self.assertTrue(
            EmployeeProfile.objects.filter(
                company=self.company_b, emp_id=self.emp_a.emp_id
            ).exists()
        )

    def test_duplicate_employee_number_within_one_company_is_rejected(self):
        # The same employee number must not be usable twice inside one tenant.
        with self.assertRaises(IntegrityError), transaction.atomic():
            employee = self._make_user(
                "dup-a@example.com", "Dup", "A", self.company_a
            )
            dup = EmployeeProfile.objects.get(user=employee)
            dup.company = self.company_a
            dup.emp_id = self.emp_a.emp_id
            dup.save(update_fields=["company", "emp_id"])

    def test_emp_id_generator_never_collides_across_concurrent_companies(self):
        """
        Two companies creating employees concurrently must never receive the
        same generated ``emp_id``. The generator's dedupe set is a
        check-then-act race: ``random.randint`` is pinned to one candidate and
        the set ``add`` is slowed so every thread passes the ``not in`` check
        before the first add lands - without the lock this deterministically
        emits duplicates, which would violate the per-company uniqueness
        constraint inside either tenant.
        """
        from payroll import generator as emp_generator

        class SlowAddSet:
            """Set stand-in that pauses before each add, widening the
            check-then-act window so the race fires deterministically."""

            def __init__(self, inner):
                self.inner = inner

            def __contains__(self, value):
                return value in self.inner

            def __len__(self):
                return len(self.inner)

            def add(self, value):
                time.sleep(0.01)
                self.inner.add(value)

        results = []
        errors = []

        def generate():
            try:
                results.append(emp_generator.emp_id())
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        with patch(
            "payroll.generator.random.randint", return_value=1234
        ), patch.object(
            emp_generator, "_used_emp_numbers", SlowAddSet(emp_generator._used_emp_numbers)
        ):
            threads = [threading.Thread(target=generate) for _ in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 50)
        # One thread wins the pinned candidate; the rest fall back to unique
        # sequential values. Any duplicate means a cross-company collision.
        self.assertEqual(len(set(results)), len(results))

    def test_same_tax_ids_reusable_across_companies(self):
        # NIN/TIN are unique per company (via deterministic digests, since the
        # encrypted columns are non-deterministic): company B may hold A's IDs.
        user = self._make_user(
            "tax-b@example.com", "Tax", "Bee", self.company_b
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company_b
        employee.nin = self.emp_a.nin
        employee.tin_no = self.emp_a.tin_no
        employee.save(
            update_fields=["company", "nin", "nin_digest", "tin_no", "tin_no_digest"]
        )

        self.assertTrue(
            EmployeeProfile.objects.filter(
                company=self.company_b,
                nin_digest=self.emp_a.nin_digest,
                tin_no_digest=self.emp_a.tin_no_digest,
            ).exists()
        )

    def test_duplicate_tax_ids_within_one_company_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            user = self._make_user(
                "dup-tax-a@example.com", "Dup", "Tax", self.company_a
            )
            dup = EmployeeProfile.objects.get(user=user)
            dup.company = self.company_a
            dup.nin = self.emp_a.nin
            dup.tin_no = self.emp_a.tin_no
            dup.save(
                update_fields=["company", "nin", "nin_digest", "tin_no", "tin_no_digest"]
            )

    def test_same_journal_transaction_number_reusable_across_companies(self):
        # Journal numbering restarts per company: both tenants get TXN000001
        # and each resolves only its own row.
        journal_a = Journal.objects.create(company=self.company_a, description="A journal")
        journal_b = Journal.objects.create(company=self.company_b, description="B journal")
        self.assertEqual(journal_a.transaction_number, "TXN000001")
        self.assertEqual(journal_b.transaction_number, "TXN000001")
        self.assertEqual(
            Journal.objects.filter(
                company=self.company_a, transaction_number=journal_a.transaction_number
            ).get(),
            journal_a,
        )

    def test_duplicate_journal_transaction_number_within_one_company_is_rejected(self):
        fy = FiscalYear.objects.create(
            company=self.company_a,
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        period = AccountingPeriod.objects.create(
            company=self.company_a,
            fiscal_year=fy,
            period_number=1,
            name="Month 1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Journal.objects.create(
                company=self.company_a,
                description="A journal",
                transaction_number="TXN000001",
                period=period,
            )
            Journal.objects.create(
                company=self.company_a,
                description="Duplicate A journal",
                transaction_number="TXN000001",
                period=period,
            )

    def test_same_case_number_reusable_across_companies(self):
        # Disciplinary case numbering restarts per company: both tenants hold
        # DISC-<year>-00001, and each resolves only its own case.
        case_a = DisciplinaryCase.objects.create(
            company=self.company_a, allegation_summary="A allegation"
        )
        case_b = DisciplinaryCase.objects.create(
            company=self.company_b, allegation_summary="B allegation"
        )
        self.assertEqual(case_a.case_number, case_b.case_number)
        self.assertEqual(
            DisciplinaryCase.objects.filter(
                company=self.company_a, case_number=case_a.case_number
            ).get(),
            case_a,
        )

    def test_duplicate_case_number_within_one_company_is_rejected(self):
        first = DisciplinaryCase.objects.create(
            company=self.company_a, allegation_summary="First A case"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DisciplinaryCase.objects.create(
                company=self.company_a,
                allegation_summary="Duplicate A case",
                case_number=first.case_number,
            )


class ZeroCrossTenantRowsTests(TenantIsolationBase):
    """Pillar 2: company-scoped queries and aggregates never see other rows."""

    def test_company_scoped_querysets_never_return_other_companies_rows(self):
        checks = [
            ("Payroll", Payroll.objects.filter(company=self.company_a)),
            ("PayrollRun", PayrollRun.objects.filter(company=self.company_a)),
            ("PayrollEntry", PayrollEntry.objects.filter(company=self.company_a)),
            (
                "PayrollRunEntry",
                PayrollRunEntry.objects.filter(payroll_entry__company=self.company_a),
            ),
            ("RemittanceRecord", RemittanceRecord.objects.filter(company=self.company_a)),
            ("BankPaymentFile", BankPaymentFile.objects.filter(company=self.company_a)),
        ]
        for label, queryset in checks:
            with self.subTest(model=label):
                self.assertEqual(queryset.count(), 1)

        # The single A row in each scope is the A-owned row, never B's.
        self.assertEqual(PayrollRun.objects.filter(company=self.company_a).get(), self.run_a)
        self.assertEqual(
            PayrollEntry.objects.filter(company=self.company_a).get().pays, self.emp_a
        )
        self.assertFalse(
            PayrollRunEntry.objects.filter(
                payroll_entry__company=self.company_a, payroll_run=self.run_b
            ).exists()
        )
        self.assertFalse(
            BankPaymentFile.objects.filter(
                company=self.company_a, payroll_run=self.run_b
            ).exists()
        )

    def test_report_totals_are_company_scoped(self):
        # The PAYE report total for a run must equal that company's own
        # employees only - not the other company's payroll with the same name.
        self.client.login(email=self.admin_a.email, password="testpass123")
        response = self.client.get(
            reverse("payroll:payeeReport", kwargs={"pay_id": self.run_a.id})
        )
        self.assertEqual(response.status_code, 200)
        expected_a = self.emp_a.employee_pay.payee
        self.assertEqual(response.context["total"], expected_a)
        self.assertNotEqual(response.context["total"], self.emp_b.employee_pay.payee)

    def test_compliance_calendar_only_includes_own_company_obligations(self):
        obligations_a = compliance_obligations(self.company_a, as_of=date(2026, 8, 1))
        paye_rows_a = [o for o in obligations_a if o["key"] == "paye"]
        # Exactly one June 2026 PAYE obligation, for company A's own payroll.
        self.assertEqual(len(paye_rows_a), 1)
        self.assertEqual(paye_rows_a[0]["amount"], self.emp_a.employee_pay.payee)
        self.assertNotEqual(
            paye_rows_a[0]["amount"], self.emp_b.employee_pay.payee
        )

    def test_remittance_records_allow_same_period_in_both_companies(self):
        for company, run in [
            (self.company_a, self.run_a),
            (self.company_b, self.run_b),
        ]:
            with self.subTest(company=company.name):
                records = RemittanceRecord.objects.filter(
                    company=company, obligation="paye", period=date(2026, 6, 1)
                )
                self.assertEqual(records.count(), 1)


class TenantSafeCachingTests(TenantIsolationBase):
    """Pillar 3: cache keys must never serve one company's data to another."""

    def test_unread_count_cache_keys_are_stable_per_employee_id(self):
        # Contract for the fix direction: keying by stable identifiers keeps
        # two companies' employees fully isolated.
        service = NotificationCacheService()
        service.set_unread_count(str(self.emp_a.id), 5)
        service.set_unread_count(str(self.emp_b.id), 9)

        self.assertEqual(service.get_unread_count(str(self.emp_a.id)), 5)
        self.assertEqual(service.get_unread_count(str(self.emp_b.id)), 9)

    def test_unread_count_cache_does_not_collide_across_companies(self):
        """
        ``NotificationCacheService`` keys are tenant-scoped: an ``EmployeeProfile``
        part is normalized to its primary key and carries its company, so two
        same-named employees in different companies can never share an entry.
        """
        emp_c = self._make_employee(
            self.company_a, "ada-c@example.com", "Ada", "Chuks", "A-002",
            basic_salary=Decimal("120000.00"),
        )
        emp_d = self._make_employee(
            self.company_b, "ada-d@example.com", "Ada", "Dike", "B-002",
            basic_salary=Decimal("120000.00"),
        )

        service = NotificationCacheService()
        service.set_unread_count(emp_c, 5)

        # emp_d has the same first name ("Ada") in a different company: its
        # unread count must be a cache miss, not company C's value.
        self.assertIsNone(service.get_unread_count(emp_d))

    def test_statutory_rates_are_national_not_tenant_scoped(self):
        # Positive test: national rate tables are shared by design. They are
        # NOT per-company data, so both companies must resolve the same
        # effective-dated version without it counting as a leak.
        version_a = StatutoryRateVersion.for_date(date(2026, 6, 1))
        version_b = StatutoryRateVersion.for_date(date(2026, 6, 1))
        self.assertIsNotNone(version_a)
        self.assertEqual(version_a.id, version_b.id)


class BackgroundTaskScopingTests(TenantIsolationBase):
    """Pillar 4: background jobs process only their own company's data."""

    def test_payslip_email_task_only_sends_for_its_own_company_run(self):
        from payroll.tasks.payslip_tasks import send_payslips_for_payroll_run_task

        job_a = PayslipEmailJob.objects.create(payroll_run=self.run_a)
        job_b = PayslipEmailJob.objects.create(payroll_run=self.run_b)

        with patch(
            "payroll.views.payroll_payslips.generate_payslip_pdf",
            return_value=b"pdf",
        ) as pdf_mock, patch(
            "payroll.views.payroll_payslips.custom_send_mail"
        ) as mail_mock:
            send_payslips_for_payroll_run_task.apply(
                args=[self.run_a.id, job_a.id]
            )

        # Only company A's employee received mail; company B's job untouched.
        self.assertEqual(mail_mock.call_count, 1)
        sent_to = mail_mock.call_args.kwargs["recipient_list"]
        self.assertEqual(sent_to, [self.emp_a.email])
        self.assertEqual(pdf_mock.call_count, 1)

        job_a.refresh_from_db()
        job_b.refresh_from_db()
        self.assertEqual(job_a.status, PayslipEmailJob.Status.SENT)
        self.assertEqual(job_b.status, PayslipEmailJob.Status.QUEUED)

    def test_payslip_email_job_belongs_to_its_run_company(self):
        job = PayslipEmailJob.objects.create(payroll_run=self.run_a)
        self.assertEqual(job.payroll_run.company, self.company_a)
        self.assertNotEqual(job.payroll_run.company, self.company_b)
