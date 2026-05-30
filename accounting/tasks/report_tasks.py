import os
import tempfile

from celery import shared_task
from django.utils import timezone
from django.template.loader import render_to_string

try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = CSS = None


def _resolve_report_params(job):
    """Return (context, template_name) for the job's report type."""
    from accounting.utils import get_trial_balance, get_trial_balance_totals

    company = job.company
    as_of_date = job.as_of_date or job.period.end_date if job.period else timezone.now().date()
    trial_balance = get_trial_balance(as_of_date=as_of_date, company=company)
    totals = get_trial_balance_totals(trial_balance)
    title = f"{job.get_report_type_display()} - {as_of_date}"

    base_context = {
        "trial_balance": trial_balance,
        "report_title": title,
        "as_of_date": as_of_date,
        **totals,
    }

    if job.report_type == "TRIAL_BALANCE":
        return base_context, "accounting/reports/pdf/trial_balance_pdf.html"
    elif job.report_type == "BALANCE_SHEET":
        base_context["page_title"] = "Balance Sheet"
        return base_context, "accounting/reports/pdf/balance_sheet_pdf.html"
    elif job.report_type == "INCOME_STATEMENT":
        base_context["page_title"] = "Income Statement"
        return base_context, "accounting/reports/pdf/income_statement_pdf.html"
    else:
        from accounting.models import Account
        from accounting.utils import get_account_balance_as_of
        accounts = Account.objects.filter(company=company).order_by("account_number")
        ledger = []
        for acct in accounts:
            balance = get_account_balance_as_of(acct, as_of_date)
            if balance != 0:
                ledger.append({"account": acct, "balance": balance})
        base_context["ledger"] = ledger
        return base_context, "accounting/reports/pdf/general_ledger_pdf.html"


@shared_task(
    bind=True,
    name="accounting.generate_financial_report",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_financial_report_task(self, job_id):
    from accounting.models import FinancialReportJob

    try:
        job = FinancialReportJob.objects.select_related("company", "period", "user").get(pk=job_id)
    except FinancialReportJob.DoesNotExist:
        return

    job.status = FinancialReportJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])

    try:
        context, template_name = _resolve_report_params(job)

        html_string = render_to_string(template_name, context)
        html = HTML(string=html_string)
        css = CSS(string="""
            @page { size: A4 landscape; margin: 1cm; }
            table { border-collapse: collapse; width: 100%; font-size: 10px; }
            th, td { border: 1px solid #e2e8f0; padding: 4px 6px; }
            th { background-color: #f1f5f9; }
            .text-right { text-align: right; }
            .text-danger { color: #dc2626; }
            .text-success { color: #16a34a; }
            .font-bold { font-weight: 700; }
        """)

        output_dir = os.path.join(tempfile.gettempdir(), "paroll_reports")
        os.makedirs(output_dir, exist_ok=True)
        filename = (
            f"{job.report_type.lower()}_{job.company_id}_{job.queued_at.strftime('%Y%m%d%H%M%S')}.pdf"
        )
        output_path = os.path.join(output_dir, filename)
        html.write_pdf(target=output_path)

        job.output_file = output_path
        job.status = FinancialReportJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["output_file", "status", "completed_at", "updated_at"])

    except Exception as exc:
        job.status = FinancialReportJob.Status.FAILED
        job.error_message = str(exc)[:1000]
        job.save(update_fields=["status", "error_message", "updated_at"])
        raise


@shared_task(
    bind=True,
    name="accounting.cleanup_draft_journals",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
)
def cleanup_draft_journals_task(self):
    """Remove draft journals older than 30 days to prevent accumulation."""
    from accounting.models import Journal

    cutoff = timezone.now() - timezone.timedelta(days=30)
    stale = Journal.objects.filter(
        status=Journal.JournalStatus.DRAFT,
        created_at__lt=cutoff,
    )
    count = stale.count()
    stale.delete()
    return {"success": True, "deleted_draft_journals": count}
