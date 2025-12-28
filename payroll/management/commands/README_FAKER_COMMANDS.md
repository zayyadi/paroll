# Fake Data Generation Commands

This directory contains Django management commands for generating fake data for the payroll system. These commands are useful for testing, development, and demonstrations.

## Available Commands

### 1. `create_fake_users`
Creates fake user accounts for the payroll system.

```bash
python manage.py create_fake_users [options]
```

**Options:**
- `--count`: Number of fake users to create (default: 50)
- `--include-admin`: Include admin users in the generated data

**Examples:**
```bash
# Create 100 fake users
python manage.py create_fake_users --count 100

# Create 50 users including admin accounts
python manage.py create_fake_users --include-admin
```

**Generated Admin Accounts:**
- Email: admin@payroll.com, Password: admin123
- Email: hr@payroll.com, Password: admin123
- Email: manager@payroll.com, Password: admin123
- Email: accountant@payroll.com, Password: admin123

**Regular User Password:**
- All regular users use password: password123

### 2. `create_fake_employees`
Creates fake employee profiles linked to user accounts.

```bash
python manage.py create_fake_employees [options]
```

**Options:**
- `--count`: Number of fake employees to create (default: 50)
- `--create-departments`: Create departments if they don't exist

**Examples:**
```bash
# Create 100 fake employees
python manage.py create_fake_employees --count 100

# Create employees and departments
python manage.py create_fake_employees --create-departments
```

**Generated Departments:**
- Engineering
- Human Resources
- Finance
- Marketing
- Operations
- Customer Service
- Administration
- Research & Development

### 3. `create_fake_payroll`
Creates comprehensive payroll data including salaries, allowances, deductions, and more.

```bash
python manage.py create_fake_payroll [options]
```

**Options:**
- `--count`: Number of months to generate payroll for (default: 12)
- `--include-allowances`: Generate allowances for employees
- `--include-deductions`: Generate deductions for employees
- `--include-iou`: Generate IOU records for employees
- `--include-leave`: Generate leave requests and policies

**Examples:**
```bash
# Generate 6 months of basic payroll data
python manage.py create_fake_payroll --count 6

# Generate comprehensive payroll data with all features
python manage.py create_fake_payroll --count 12 --include-all
```

### 4. `create_fake_accounts` (Accounting)
Creates fake accounting accounts for the integrated accounting system.

```bash
python manage.py create_fake_accounts [options]
```

**Options:**
- `--count`: Number of fake accounts to create (default: 20)
- `--include-fiscal-year`: Also create a fiscal year and periods if they do not exist

### 5. `generate_all_fake_data` (Master Command)
Generates all fake data in the correct order. This is the recommended command for setting up a complete test environment.

```bash
python manage.py generate_all_fake_data [options]
```

**Options:**
- `--users`: Number of fake users to create (default: 50)
- `--employees`: Number of fake employees to create (default: 50)
- `--months`: Number of months of payroll data to generate (default: 12)
- `--accounts`: Number of fake accounting accounts to create (default: 30)
- `--skip-existing`: Skip data generation if data already exists
- `--clear-existing`: Clear existing data before generating new data
- `--include-all`: Include all optional data (allowances, deductions, IOU, leave, etc.)

**Examples:**
```bash
# Generate a complete test environment with default settings
python manage.py generate_all_fake_data

# Generate a large test environment with all features
python manage.py generate_all_fake_data --users 100 --employees 100 --months 24 --include-all

# Clear existing data and regenerate
python manage.py generate_all_fake_data --clear-existing
```

## Usage Workflow

### For New Development Environment:

1. **Complete Setup (Recommended):**
   ```bash
   python manage.py generate_all_fake_data --include-all
   ```

2. **Or Step-by-Step:**
   ```bash
   # Step 1: Create users
   python manage.py create_fake_users --count 50 --include-admin
   
   # Step 2: Create employees and departments
   python manage.py create_fake_employees --count 50 --create-departments
   
   # Step 3: Create accounting data
   python manage.py create_fake_accounts --count 30 --include-fiscal-year
   
   # Step 4: Create comprehensive payroll data
   python manage.py create_fake_payroll --count 12 --include-allowances --include-deductions --include-iou --include-leave
   ```

### For Testing Specific Features:

- **User Management:** `python manage.py create_fake_users --count 10`
- **Employee Management:** `python manage.py create_fake_employees --count 10`
- **Payroll Processing:** `python manage.py create_fake_payroll --count 3 --include-all`
- **Accounting Integration:** `python manage.py create_fake_accounts --count 20`

## Generated Data Characteristics

### Users:
- Random names and email addresses
- Mix of regular users and managers (10% chance of being manager)
- Default password: `password123`

### Employees:
- Realistic salary ranges based on job titles:
  - Casual: ₦30,000 - ₦60,000
  - Junior Staff: ₦60,000 - ₦120,000
  - Operator: ₦120,000 - ₦200,000
  - Supervisor: ₦200,000 - ₦350,000
  - Manager: ₦350,000 - ₦500,000
  - COO: ₦500,000 - ₦800,000
- Complete contact information
- Emergency contacts and next of kin
- Bank account details
- Employment dates and contract types

### Payroll Data:
- Monthly payroll periods
- Automatic calculation of taxes, pensions, and deductions
- Allowances (30% chance per employee per period)
- Deductions (20% chance per employee per period)
- IOU records with repayment schedules (30% chance)
- Leave requests and policies

### Accounting Data:
- Complete chart of accounts
- Fiscal year and monthly periods
- Balanced journal entries
- Transaction numbers and audit trails

## Best Practices

1. **Use `--clear-existing`** when you want to start fresh
2. **Use `--skip-existing`** to avoid accidentally regenerating data
3. **Use the master command** (`generate_all_fake_data`) for complete setups
4. **Test with smaller datasets first** before generating large amounts of data
5. **Regular users use `password123`**, admins use `admin123`

## Troubleshooting

### Common Issues:

1. **"No active employees found"**
   - Run `create_fake_users` first, then `create_fake_employees`

2. **"No departments found"**
   - Use the `--create-departments` flag with `create_fake_employees`

3. **"Not enough users available"**
   - Increase the number of users or decrease the number of employees

4. **Database constraints**
   - Use `--clear-existing` to start with a clean slate

### Performance Tips:

- For large datasets (>1000 employees), consider running commands separately
- Use `--skip-existing` when adding to existing data
- Monitor memory usage with very large datasets