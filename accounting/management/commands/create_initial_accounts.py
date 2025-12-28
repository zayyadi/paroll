from django.core.management.base import BaseCommand
from accounting.models import Account

class Command(BaseCommand):
    help = 'Creates initial accounts for the payroll system'

    def handle(self, *args, **options):
        accounts = [
            {'name': 'Cash', 'account_number': '1010', 'type': Account.AccountType.ASSET},
            {'name': 'Salaries Payable', 'account_number': '2010', 'type': Account.AccountType.LIABILITY},
            {'name': 'Pension Payable', 'account_number': '2020', 'type': Account.AccountType.LIABILITY},
            {'name': 'PAYE Tax Payable', 'account_number': '2030', 'type': Account.AccountType.LIABILITY},
            {'name': 'NSITF Payable', 'account_number': '2040', 'type': Account.AccountType.LIABILITY},
            {'name': 'Salary Expense', 'account_number': '5010', 'type': Account.AccountType.EXPENSE},
            {'name': 'Pension Expense', 'account_number': '5020', 'type': Account.AccountType.EXPENSE},
        ]

        for acc_data in accounts:
            account, created = Account.objects.get_or_create(
                name=acc_data['name'],
                defaults={
                    'account_number': acc_data['account_number'],
                    'type': acc_data['type']
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created account: {account.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Account already exists: {account.name}'))
