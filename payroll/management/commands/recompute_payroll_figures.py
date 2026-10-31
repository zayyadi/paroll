from django.core.management.base import BaseCommand

from payroll.services.payroll_recompute import recompute_payroll_figures


class Command(BaseCommand):
    help = (
        "Recompute stored salary-config figures (PAYE, pension, NHF, NHIA, NSITF, "
        "ITF) and employees' stored net pay. Dry-run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist the recomputed figures.")

    def handle(self, *args, **options):
        result = recompute_payroll_figures(apply=options["apply"])
        verb = "Updated" if result["applied"] else "Would update"
        self.stdout.write(
            f"{verb} {result['configs']} salary config(s) and "
            f"{result['profiles']} employee net pay value(s)."
        )
