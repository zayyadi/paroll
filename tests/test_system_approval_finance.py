"""Financial effects require independent approval and retain decision provenance."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from company.models import Company, ActionProposal
from accounting.models import Account, Journal, AccountingPeriod
from accounting.utils import create_journal_with_entries
from approvals.services import submit_approval, decide_approval
from approvals.models import ApprovalPolicy, ApprovalRequest
from inventory.models import Supplier, InventoryDocument
from inventory.services import post_supplier_payment

class FinancialApprovalTests(TestCase):
    def setUp(self):
        self.company=Company.objects.create(name='Financial workflow test')
        User=get_user_model()
        self.maker=User.objects.create_superuser(email='maker@financial.test',password='test',company=self.company,active_company=self.company)
        self.checker=User.objects.create_superuser(email='checker@financial.test',password='test',company=self.company,active_company=self.company)
        self.third=User.objects.create_superuser(email='third@financial.test',password='test',company=self.company,active_company=self.company)
        self.bank=Account.objects.create(company=self.company,name='Bank',account_number='1001',type='ASSET')
        self.payable=Account.objects.create(company=self.company,name='Payables',account_number='2001',type='LIABILITY')
        self.equity=Account.objects.create(company=self.company,name='Opening equity',account_number='3001',type='EQUITY')
        self.supplier=Supplier.objects.create(company=self.company,name='Supplier',payable_account=self.payable)
        journal=create_journal_with_entries(company=self.company,date=date(2026,10,1),description='Opening test cash',user=self.maker,
            entries=[{'account':self.bank,'entry_type':'DEBIT','amount':Decimal('1000')},
                     {'account':self.equity,'entry_type':'CREDIT','amount':Decimal('1000')}])
        journal.submit_for_approval()
        journal.approve(self.checker)
        journal.post(self.checker)

    def proposal(self):
        return post_supplier_payment(company=self.company,supplier=self.supplier,cash_account=self.bank,
            amount=Decimal('100'),reference='PAY-001',approval_actor=self.maker)

    def test_supplier_payment_is_pending_until_independent_decision(self):
        count=Journal.objects.count()
        request=self.proposal()
        self.assertEqual(request.status,'PENDING')
        self.assertEqual(Journal.objects.count(),count)
        self.assertFalse(InventoryDocument.objects.exists())
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request,actor=self.maker)
        decide_approval(approval=request,actor=self.checker)
        journal=Journal.objects.exclude(description='Opening test cash').get()
        self.assertEqual(journal.approval_request_id,request.pk)
        self.assertEqual(journal.status,'POSTED')
        self.assertEqual(InventoryDocument.objects.count(),1)
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.balance,Decimal('900'))

    def test_two_stage_policy_defers_money_until_last_checker(self):
        ApprovalPolicy.objects.create(company=self.company,action='inventory.supplier_payment',currency='NGN',minimum_amount=Decimal('50'),
            stages=[{'permission':'inventory.change_inventorydocument','approver_ids':[self.checker.pk]},
                    {'permission':'inventory.change_inventorydocument','approver_ids':[self.third.pk]}])
        request=self.proposal()
        decide_approval(approval=request,actor=self.checker)
        self.assertFalse(InventoryDocument.objects.exists())
        decide_approval(approval=request,actor=self.third)
        self.assertEqual(InventoryDocument.objects.count(),1)

    def test_child_failure_rolls_back_decision_and_money(self):
        request=self.proposal()
        with patch('inventory.services._mark_document_posted',side_effect=ValidationError('Injected child failure')):
            with self.assertRaisesMessage(ValidationError,'Injected child failure'):
                decide_approval(approval=request,actor=self.checker)
        request.refresh_from_db()
        self.assertEqual(request.status,'PENDING')
        self.assertFalse(request.decisions.exists())
        self.assertEqual(Journal.objects.count(),1)
        self.assertFalse(InventoryDocument.objects.exists())

    def test_stale_supplier_terms_cannot_be_approved(self):
        request=self.proposal()
        self.supplier.name='Changed reviewed supplier'
        self.supplier.save()
        with self.assertRaisesMessage(ValidationError,'source changed'):
            decide_approval(approval=request,actor=self.checker)
        self.assertFalse(InventoryDocument.objects.exists())

    def test_manual_journal_maker_cannot_approve(self):
        journal=create_journal_with_entries(company=self.company,date=date(2026,10,1),description='Manual draft',user=self.maker,
            entries=[{'account':self.bank,'entry_type':'DEBIT','amount':Decimal('10')},
                     {'account':self.equity,'entry_type':'CREDIT','amount':Decimal('10')}])
        journal.submit_for_approval()
        with self.assertRaises(PermissionDenied):
            journal.approve(self.maker)
        journal.refresh_from_db()
        self.assertEqual(journal.status,'PENDING_APPROVAL')

    def test_actorless_direct_financial_operation_is_denied(self):
        with self.assertRaises(PermissionDenied):
            post_supplier_payment(company=self.company,supplier=self.supplier,cash_account=self.bank,amount=Decimal('100'))

    def test_approval_proposal_cannot_be_changed_or_forged(self):
        request=self.proposal()
        with self.assertRaises(ValidationError):
            ActionProposal.objects.filter(pk=request.object_id).update(parameters={})
        with self.assertRaises(ValidationError):
            InventoryDocument.objects.create(company=self.company,document_type='SUPPLIER_PAYMENT',status='POSTED')

    def test_submission_retry_reuses_one_request_and_one_payment(self):
        first = self.proposal()
        second = self.proposal()
        self.assertEqual(first.pk, second.pk)
        decide_approval(approval=first, actor=self.checker)
        replay = self.proposal()
        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(InventoryDocument.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=replay, actor=self.checker)

    def test_payload_currency_cannot_bypass_the_source_threshold(self):
        from approvals.services import cancel_approval
        approval = self.proposal()
        source = approval.source
        cancel_approval(approval=approval, actor=self.maker, reason='Revise instruction')
        with self.assertRaisesMessage(ValidationError, 'currency'):
            submit_approval(source=source, action='inventory.supplier_payment', requester=self.maker, payload={'currency':'USD'})

    def test_numeric_reversal_amount_keys_round_trip_without_widening(self):
        from approvals.proposals import encode_value, decode_value
        amounts = {12: Decimal('40.00'), 13: Decimal('40.00')}
        self.assertEqual(decode_value(encode_value(amounts), self.company), amounts)

    def test_partial_reversal_threshold_includes_default_full_entry_amounts(self):
        from approvals.proposals import encode_value
        journal = Journal.objects.get()
        debit = journal.entries.get(entry_type='DEBIT')
        credit = journal.entries.get(entry_type='CREDIT')
        ApprovalPolicy.objects.create(company=self.company, action='accounting.journal.reverse_partial',
            currency='NGN', minimum_amount=Decimal('500'), stages=[
                {'permission':'accounting.change_journal', 'approver_ids':[self.checker.pk]},
                {'permission':'accounting.change_journal', 'approver_ids':[self.third.pk]}])
        proposal = ActionProposal.objects.create(company=self.company, action='accounting.journal.reverse_partial',
            created_by=self.maker, request_key='partial-amount-threshold', parameters=encode_value({
                'journal':journal, 'user':self.maker, 'reason':'Default full selected amounts',
                'entry_ids':[debit.pk, credit.pk], 'amounts':{}, 'ip_address':None, 'user_agent':None}))
        approval = submit_approval(source=proposal, action=proposal.action, requester=self.maker)
        self.assertEqual(Decimal(approval.policy_snapshot['amount']), Decimal('1000'))
        self.assertEqual(len(approval.policy_snapshot['stages']), 2)

    def test_reversal_snapshot_contains_immutable_reviewed_journal_entries(self):
        from approvals.proposals import encode_value
        journal = Journal.objects.get()
        proposal = ActionProposal.objects.create(company=self.company, action='accounting.journal.reverse',
            created_by=self.maker, request_key='reviewed-journal-lines', parameters=encode_value({
                'journal':journal, 'user':self.maker, 'reason':'Reviewed reversal', 'ip_address':None, 'user_agent':None}))
        approval = submit_approval(source=proposal, action=proposal.action, requester=self.maker)
        entry = journal.entries.get(entry_type='DEBIT')
        reference = approval.source_snapshot['references'][0]
        self.assertEqual(len(reference['data']['entries']), 2)
        self.assertEqual(reference['data']['entries'][0]['id'], entry.pk)
        entry.memo = 'Updated source memo'
        with self.assertRaises(ValidationError):
            entry.save(update_fields=['memo'])
        self.assertFalse(approval.decisions.exists())

    def test_assigned_salary_and_pay_link_bulk_edits_require_approval(self):
        from payroll.models import Payroll, EmployeeProfile
        salary = Payroll.objects.create(company=self.company, basic_salary=Decimal('100000'))
        replacement = Payroll.objects.create(company=self.company, basic_salary=Decimal('150000'))
        employee = EmployeeProfile.objects.get(user=self.third)
        employee.employee_pay = salary
        employee.save(update_fields=['employee_pay'])
        with self.assertRaises(ValidationError):
            Payroll.objects.filter(pk=salary.pk).update(basic_salary=Decimal('200000'))
        with self.assertRaises(ValidationError):
            Payroll.all_objects.filter(pk=salary.pk).update(nhf_scheme='compulsory')
        with self.assertRaises(ValidationError):
            EmployeeProfile.objects.filter(pk=employee.pk).update(employee_pay=replacement)
        employee.employee_pay = replacement
        with self.assertRaises(ValidationError):
            EmployeeProfile.objects.bulk_update([employee], ['employee_pay'])
        employee.refresh_from_db()
        self.assertEqual(employee.employee_pay_id, salary.pk)

    def test_tax_filing_route_queues_reviewed_reference_and_full_tax_threshold(self):
        from django.urls import reverse
        from accounting.models import TaxReturn, TaxReturnLine
        from approvals.services import decide_approval
        journal = Journal.objects.get()
        tax_return = TaxReturn.objects.create(company=self.company, return_type='VAT', period=journal.period,
            return_period_start=date(2026,10,1), return_period_end=date(2026,10,31))
        TaxReturnLine.objects.create(tax_return=tax_return, account=self.bank, gross_amount=Decimal('10000'),
            tax_rate=Decimal('7.5'), tax_amount=Decimal('750'))
        ApprovalPolicy.objects.create(company=self.company, action='accounting.tax_return.file', currency='NGN',
            minimum_amount=Decimal('500'), stages=[
                {'permission':'accounting.change_taxreturn','approver_ids':[self.checker.pk]},
                {'permission':'accounting.change_taxreturn','approver_ids':[self.third.pk]}])
        self.client.force_login(self.maker)
        response = self.client.post(reverse('accounting:tax_return_file', args=[tax_return.pk]), {'filing_reference':'TAX-REVIEWED'})
        approval = ApprovalRequest.objects.get(action='accounting.tax_return.file')
        self.assertRedirects(response, reverse('approvals:detail', args=[approval.pk]))
        self.assertEqual(Decimal(approval.policy_snapshot['amount']), Decimal('750'))
        tax_return.refresh_from_db()
        self.assertEqual(tax_return.status, 'DRAFT')
        self.assertEqual(tax_return.filing_reference, '')
        decide_approval(approval=approval, actor=self.checker)
        tax_return.refresh_from_db()
        self.assertEqual(tax_return.status, 'DRAFT')
        decide_approval(approval=approval, actor=self.third)
        tax_return.refresh_from_db()
        self.assertEqual(tax_return.status, 'FILED')
        self.assertEqual(tax_return.filing_reference, 'TAX-REVIEWED')
        self.assertEqual(tax_return.filed_by_id, self.third.pk)
        line = tax_return.lines.get()
        draft_return = TaxReturn.objects.create(company=self.company, return_type='WHT', period=tax_return.period,
            return_period_start=date(2026,10,1), return_period_end=date(2026,10,31))
        with self.assertRaises(ValidationError):
            TaxReturnLine.objects.filter(pk=line.pk).update(tax_amount=Decimal('1'))
        line.tax_return = draft_return
        with self.assertRaises(ValidationError):
            line.save(update_fields=['tax_return'])
        from django.db import transaction
        with self.assertRaises(ValidationError), transaction.atomic():
            line.delete()
        with self.assertRaises(ValidationError):
            TaxReturnLine.objects.create(tax_return=tax_return, account=self.bank,
                gross_amount=Decimal('100'), tax_rate=Decimal('7.5'), tax_amount=Decimal('7.5'))

    def test_salary_history_records_actual_maker_and_final_checker(self):
        from payroll.models import EmployeeProfile, SalaryHistory
        from payroll.financial_approval_actions import change_salary
        employee = EmployeeProfile.objects.get(user=self.third)
        approval = change_salary(employee=employee, basic_salary=Decimal('150000'), user=self.maker)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=approval, actor=self.third)
        decide_approval(approval=approval, actor=self.checker)
        employee.refresh_from_db()
        history = SalaryHistory.objects.get(employee=employee, salary_config=employee.employee_pay)
        self.assertEqual(history.changed_by_id, self.maker.pk)
        self.assertEqual(history.approved_by_id, self.checker.pk)

    def test_accounting_admin_is_company_scoped_and_cannot_change_pending_source(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from accounting.admin import JournalAdmin
        from payroll.admin.general_admin import PayrollRunAdmin
        from payroll.models import PayrollRun
        other = Company.objects.create(name='Other admin company')
        foreign = Journal.objects.create(company=other, description='Foreign private journal', date=date(2026,10,1))
        request = RequestFactory().get('/admin/accounting/journal/')
        request.user = self.maker
        journal_admin = JournalAdmin(Journal, AdminSite())
        self.assertFalse(journal_admin.get_queryset(request).filter(pk=foreign.pk).exists())
        self.assertIn('status', journal_admin.get_readonly_fields(request))
        self.assertFalse(journal_admin.has_import_permission(request))
        self.assertFalse(journal_admin.has_change_permission(request, Journal.objects.get(company=self.company)))
        draft = create_journal_with_entries(company=self.company, date=date(2026,10,1), description='Reviewed draft', user=self.maker,
            entries=[{'account':self.bank,'entry_type':'DEBIT','amount':Decimal('10')},
                     {'account':self.equity,'entry_type':'CREDIT','amount':Decimal('10')}])
        draft.submit_for_approval()
        submit_approval(source=draft, action='journal.approve', requester=self.maker)
        self.assertFalse(journal_admin.has_change_permission(request, draft))
        run_admin = PayrollRunAdmin(PayrollRun, AdminSite())
        self.assertIn('closed', run_admin.get_readonly_fields(request))
        self.assertNotIn('status', run_admin.list_editable)

    def test_fx_policy_uses_reviewed_base_currency(self):
        from accounting.models import CurrencyRevaluation, CurrencyRevaluationLine
        from accounting.utils import post_fx_revaluation
        revaluation = CurrencyRevaluation.objects.create(company=self.company, revaluation_date=date(2026,10,1),
            base_currency='USD', created_by=self.maker)
        CurrencyRevaluationLine.objects.create(revaluation=revaluation, account=self.bank, foreign_currency='EUR',
            balance_fc=Decimal('100'), rate_at_original=Decimal('1'), rate_at_revaluation=Decimal('2'),
            base_value_original=Decimal('100'), base_value_revalued=Decimal('200'),
            unrealized_gain_loss=Decimal('100'), entry_type='DEBIT')
        ApprovalPolicy.objects.create(company=self.company, action='accounting.fx_revaluation.post', currency='USD',
            minimum_amount=Decimal('50'), stages=[
                {'permission':'accounting.change_currencyrevaluation','approver_ids':[self.checker.pk]},
                {'permission':'accounting.change_currencyrevaluation','approver_ids':[self.third.pk]}])
        approval = post_fx_revaluation(revaluation, self.maker, self.equity, self.payable)
        self.assertEqual(approval.policy_snapshot['currency'], 'USD')
        self.assertEqual(Decimal(approval.policy_snapshot['amount']), Decimal('100'))
        self.assertEqual(len(approval.policy_snapshot['stages']), 2)
        self.assertEqual(approval.source_snapshot['currency'], 'USD')
        revaluation.refresh_from_db()
        self.assertEqual(revaluation.status, 'DRAFT')

    def test_budget_threshold_reviews_lines_and_rejects_foreign_accounts(self):
        from accounting.models import Budget, BudgetLine
        period = Journal.objects.get().period
        budget = Budget.objects.create(company=self.company, fiscal_year=period.fiscal_year, name='Reviewed annual budget')
        line = BudgetLine.objects.create(budget=budget, account=self.bank, period=period, amount=Decimal('1000'))
        ApprovalPolicy.objects.create(company=self.company, action='accounting.budget.approve', currency='NGN', minimum_amount=Decimal('500'),
            stages=[{'permission':'accounting.change_budget','approver_ids':[self.checker.pk]},
                    {'permission':'accounting.change_budget','approver_ids':[self.third.pk]}])
        approval = submit_approval(source=budget, action='accounting.budget.approve', requester=self.maker)
        self.assertEqual(Decimal(approval.policy_snapshot['amount']), Decimal('1000'))
        decide_approval(approval=approval, actor=self.checker)
        budget.refresh_from_db()
        self.assertEqual(budget.status, 'DRAFT')
        decide_approval(approval=approval, actor=self.third)
        budget.refresh_from_db()
        self.assertEqual(budget.status, 'APPROVED')
        with self.assertRaises(ValidationError):
            BudgetLine.objects.filter(pk=line.pk).update(amount=Decimal('1'))
        other = Company.objects.create(name='Foreign budget account owner')
        foreign_account = Account.objects.create(company=other, name='Foreign bank', account_number='F1001', type='ASSET')
        draft = Budget.objects.create(company=self.company, fiscal_year=period.fiscal_year, name='Invalid draft budget')
        BudgetLine.objects.create(budget=draft, account=foreign_account, amount=Decimal('1000'))
        with self.assertRaisesMessage(ValidationError, 'reviewed company'):
            submit_approval(source=draft, action='accounting.budget.approve', requester=self.maker)

    def test_historical_leave_allowance_backfill_needs_review_and_keeps_paid_amount(self):
        from payroll.models import EmployeeProfile, LeaveRequest, Allowance, CompanyPayrollSetting, LeaveAllowanceEmailJob
        from payroll.financial_approval_actions import change_salary, request_leave_allowance_backfill
        from tests.approval_helpers import approve_source, approve_request
        from payroll.services.leave_allowance import process_leave_allowance_for_request
        employee = EmployeeProfile.objects.get(user=self.third)
        leave = LeaveRequest.objects.create(employee=employee, leave_type='ANNUAL', start_date=date(2026,10,1),
            end_date=date(2026,10,2), reason='Historical leave without salary configuration')
        approve_source(leave, 'leave.approve', maker=self.third)
        self.assertFalse(Allowance.objects.filter(source_leave_request=leave).exists())
        approve_request(change_salary(employee=employee, basic_salary=Decimal('100000'), user=self.maker))
        employee.refresh_from_db()
        leave.refresh_from_db()
        count = Journal.objects.count()
        with self.assertRaisesMessage(ValidationError, 'independent financial approval'):
            process_leave_allowance_for_request(leave)
        approval = request_leave_allowance_backfill(leave_request=leave, actor=self.maker, queue_email=False)
        self.assertEqual(approval.status, 'PENDING')
        self.assertFalse(Allowance.objects.filter(source_leave_request=leave).exists())
        self.assertEqual(Journal.objects.count(), count)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=approval, actor=self.third)
        decide_approval(approval=approval, actor=self.checker)
        allowance = Allowance.objects.get(source_leave_request=leave)
        job = LeaveAllowanceEmailJob.objects.get(leave_request=leave)
        self.assertEqual(job.allowance_id, allowance.pk)
        self.assertEqual(job.amount, allowance.amount)
        self.assertEqual(Journal.objects.exclude(description='Opening test cash').get().approval_request_id, approval.pk)
        paid = allowance.amount
        setting = CompanyPayrollSetting.objects.get(company=self.company)
        setting.leave_allowance_percentage *= Decimal('2')
        setting.save(update_fields=['leave_allowance_percentage'])
        process_leave_allowance_for_request(leave)
        allowance.refresh_from_db()
        self.assertEqual(allowance.amount, paid)
        self.assertEqual(Journal.objects.count(), count + 1)

    def test_nonannual_leave_has_no_annual_cash_allowance(self):
        from payroll.models import EmployeeProfile, LeaveRequest, Allowance, CompanyPayrollSetting
        from payroll.financial_approval_actions import change_salary
        from payroll.services.leave_allowance import calculate_leave_allowance_amount
        from tests.approval_helpers import approve_request, approve_source
        employee = EmployeeProfile.objects.get(user=self.third)
        approve_request(change_salary(employee=employee, basic_salary=Decimal('100000'), user=self.maker))
        employee.refresh_from_db()
        leave = LeaveRequest.objects.create(employee=employee, leave_type='SICK', start_date=date(2026,10,1),
            end_date=date(2026,10,2), reason='Approved sick absence')
        self.assertEqual(calculate_leave_allowance_amount(leave), Decimal('0'))
        count = Journal.objects.count()
        approve_source(leave, 'leave.approve', maker=self.third)
        self.assertFalse(Allowance.objects.filter(source_leave_request=leave).exists())
        self.assertEqual(Journal.objects.count(), count)

    def test_paid_leave_threshold_binds_salary_and_percentage(self):
        from payroll.models import EmployeeProfile, LeaveRequest, CompanyPayrollSetting
        from payroll.financial_approval_actions import change_salary
        from tests.approval_helpers import approve_request
        employee = EmployeeProfile.objects.get(user=self.third)
        approve_request(change_salary(employee=employee, basic_salary=Decimal('100000'), user=self.maker))
        employee.refresh_from_db()
        setting, _ = CompanyPayrollSetting.objects.get_or_create(company=self.company)
        setting.leave_allowance_percentage = Decimal('10')
        setting.save(update_fields=['leave_allowance_percentage'])
        ApprovalPolicy.objects.create(company=self.company, action='leave.approve', currency='NGN', minimum_amount=Decimal('50000'),
            stages=[{'permission':'payroll.change_leaverequest','approver_ids':[self.maker.pk]},
                    {'permission':'accounting.change_journal','approver_ids':[self.checker.pk]}])
        leave = LeaveRequest.objects.create(employee=employee, leave_type='ANNUAL', start_date=date(2026,10,1),
            end_date=date(2026,10,2), reason='Reviewed financial benefit')
        approval = submit_approval(source=leave, action='leave.approve', requester=self.third)
        self.assertEqual(Decimal(approval.policy_snapshot['amount']), Decimal('120000'))
        decide_approval(approval=approval, actor=self.maker)
        setting.leave_allowance_percentage = Decimal('20')
        setting.save(update_fields=['leave_allowance_percentage'])
        with self.assertRaisesMessage(ValidationError, 'source changed'):
            decide_approval(approval=approval, actor=self.checker)
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'PENDING')

    def test_employee_cannot_approve_source_backed_journal_or_its_reversal(self):
        from payroll.models import EmployeeProfile, Allowance
        from accounting.utils import reverse_journal
        employee = EmployeeProfile.objects.get(user=self.third)
        allowance = Allowance.objects.create(employee=employee, allowance_type='LV', amount=Decimal('100'))
        journal = create_journal_with_entries(company=self.company, date=date(2026,10,1), description='Employee-linked journal', user=self.maker,
            source_object=allowance, entries=[{'account':self.bank,'entry_type':'DEBIT','amount':Decimal('100')},
                                             {'account':self.equity,'entry_type':'CREDIT','amount':Decimal('100')}])
        journal.submit_for_approval()
        approval = submit_approval(source=journal, action='journal.approve', requester=self.maker)
        self.assertIn(self.third.pk, approval.beneficiary_ids)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=approval, actor=self.third)
        decide_approval(approval=approval, actor=self.checker)
        journal.refresh_from_db()
        journal.post(self.checker)
        reversal = reverse_journal(journal, self.maker, 'Reviewed employee-related reversal')
        self.assertIn(self.third.pk, reversal.beneficiary_ids)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=reversal, actor=self.third)
        reversal = decide_approval(approval=reversal, actor=self.checker)
        self.assertEqual(reversal.status, 'APPROVED')

    def test_payroll_currency_cannot_disguise_ngn_obligations(self):
        from payroll.models import PayrollRun
        from payroll.financial_approval_actions import validate_run
        run = PayrollRun(company=self.company, name='Unsupported denomination', currency='USD')
        with self.assertRaisesMessage(ValidationError, 'require NGN'):
            validate_run(run, {})
