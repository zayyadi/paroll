# Accounting Faker Commands

This document describes the management commands available for generating fake accounting data for testing purposes.

## Commands Overview

### 1. create_fake_accounts

Creates fake accounts for testing the accounting system.

#### Usage:
```bash
python manage.py create_fake_accounts [--count N] [--include-fiscal-year]
```

#### Options:
- `--count N`: Number of fake accounts to create (default: 20)
- `--include-fiscal-year`: Also create a fiscal year and periods if they do not exist

#### Examples:
```bash
# Create 20 fake accounts
python manage.py create_fake_accounts

# Create 50 fake accounts with fiscal year
python manage.py create_fake_accounts --count 50 --include-fiscal-year
```

### 2. generate_sample_data

Generates comprehensive sample accounting data including accounts, fiscal years, periods, and journals with balanced entries.

#### Usage:
```bash
python manage.py generate_sample_data [--accounts N] [--journals N] [--fiscal-year Y] [--clear-existing]
```

#### Options:
- `--accounts N`: Number of fake accounts to create (default: 30)
- `--journals N`: Number of sample journals to create (default: 50)
- `--fiscal-year Y`: Fiscal year to generate data for (default: current year)
- `--clear-existing`: Clear existing sample data before generating new data

#### Examples:
```bash
# Generate default sample data
python manage.py generate_sample_data

# Generate 100 accounts and 200 journals for 2024
python manage.py generate_sample_data --accounts 100 --journals 200 --fiscal-year 2024

# Clear existing data and generate fresh sample data
python manage.py generate_sample_data --clear-existing
```

### 3. create_initial_accounts

Creates basic initial accounts required for the payroll system.

#### Usage:
```bash
python manage.py create_initial_accounts
```

#### Accounts Created:
- Cash (1010) - Asset
- Salaries Payable (2010) - Liability
- Pension Payable (2020) - Liability
- PAYE Tax Payable (2030) - Liability
- NSITF Payable (2040) - Liability
- Salary Expense (5010) - Expense
- Pension Expense (5020) - Expense

## Data Generated

### Account Types
The faker generates accounts for all standard accounting types:
- **Assets** (1000-1999): Cash, receivables, inventory, equipment, etc.
- **Liabilities** (2000-2999): Payables, taxes, loans, etc.
- **Equity** (3000-3999): Share capital, retained earnings, etc.
- **Revenue** (4000-4999): Sales, service income, interest income, etc.
- **Expenses** (5000-5999): Salaries, rent, utilities, etc.

### Journal Entries
The sample data generator creates realistic journal entries with:
- Balanced debits and credits
- Various transaction types (expenses, revenues, asset purchases, etc.)
- Random dates within fiscal periods
- Proper transaction numbering
- Descriptive memos

### Fiscal Year Structure
- Annual fiscal year (January 1 - December 31)
- 12 monthly periods
- Current period marked as active

## Best Practices

1. **For Development**: Use `create_initial_accounts` for basic setup, then `generate_sample_data` for comprehensive testing
2. **For Testing**: Use `--clear-existing` flag to ensure clean test data
3. **For Production**: Never use faker commands in production environments

## Troubleshooting

### Migration Issues
If you encounter migration errors:
1. Ensure all migrations are applied: `python manage.py migrate`
2. Check if jazzmin package is installed: `pip install django-jazzmin`
3. Verify database connection in settings.py

### Common Errors
- **"No module named 'jazzmin'"**: Install the package with `pip install django-jazzmin`
- **"Database connection failed"**: Check your .env file for correct database credentials
- **"Account already exists"**: Use `--clear-existing` or manually delete existing accounts

## Data Relationships

The generated data maintains proper relationships:
- Journals → Journal Entries (one-to-many)
- Journals → Accounting Period (many-to-one)
- Accounting Period → Fiscal Year (many-to-one)
- Journal Entries → Accounts (many-to-one)
- All models include proper audit trails

## Security Notes

- These commands should only be used in development/testing environments
- Generated user accounts use default passwords
- No sensitive financial data is included in the generated samples
- All monetary values are randomized and not based on real transactions