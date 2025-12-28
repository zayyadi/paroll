from decimal import Decimal

from num2words import num2words
import calendar

PENSION_THRESHOLD = Decimal(360000)


def calculate_percentage(value: Decimal, percentage: Decimal) -> Decimal:
    """Calculates a percentage of a given value."""
    return value * percentage / 100


def get_housing(self):
    return calculate_percentage(self.get_annual_gross, 10)


def get_transport(self):
    return calculate_percentage(self.get_annual_gross, 10)


def get_basic(self):
    return calculate_percentage(self.get_annual_gross, 40)


def get_bht(self):
    return get_transport(self) + get_housing(self) + get_basic(self)


def get_pension_employee(self):
    if self.get_annual_gross <= PENSION_THRESHOLD:
        return Decimal(0)
    return calculate_percentage(self.get_annual_gross, 8)


def get_pension_employer(self):
    if self.get_annual_gross <= PENSION_THRESHOLD:
        return Decimal(0)
    return calculate_percentage(self.get_annual_gross, 10)


def get_pension(self):
    if self.get_annual_gross <= PENSION_THRESHOLD:
        return Decimal(0)
    return get_pension_employee(self) + get_pension_employer(self)


def get_consolidated_calc(self):
    if (self.get_annual_gross * 1 / 100) > 200000:
        return self.get_gross_income * 1 / 100
    return 200000


def get_gross_income(self):
    return (self.basic_salary * 12) - (get_pension_employee(self) * 12)


def get_consolidated_relief(self):
    return get_consolidated_calc(self) + (self.get_gross_income * 20 / 100)


def calculate_taxable_income(self) -> Decimal:
    return (self.get_gross_income) - (get_consolidated_relief(self))


def get_payee(self) -> Decimal:
    taxable_income = self.calculate_taxable_income

    if self.basic_salary <= 30000:
        return Decimal(0.0)

    tax_bands = [
        (300000, Decimal("7")),
        (300000, Decimal("11")),
        (500000, Decimal("15")),
        (500000, Decimal("19")),
        (1600000, Decimal("21")),
        (Decimal("Infinity"), Decimal("24")),
    ]

    remaining_income = taxable_income
    total_tax = Decimal(0.0)
    taxable_limit = Decimal(0.0)

    for band_limit, rate in tax_bands:
        if remaining_income <= 0:
            break

        if band_limit == Decimal("Infinity"):
            taxable_amount = remaining_income
        else:
            taxable_amount = min(remaining_income, band_limit)

        band_tax = taxable_amount * rate / Decimal(100)
        total_tax += band_tax

        remaining_income -= taxable_amount
        taxable_limit += band_limit

    return total_tax / Decimal(12)


def get_new_payee(self):
    taxable_income = self.calculate_taxable_income

    if self.basic_salary <= 77000:
        return Decimal(0.0)

    tax_bands = [
        (800000, Decimal("10")),
        (800000, Decimal("15")),
        (1200000, Decimal("20")),
        (Decimal("Infinity"), Decimal("20")),
    ]

    remaining_income = taxable_income
    total_tax = Decimal(0.0)
    taxable_limit = Decimal(0.0)

    for band_limit, rate in tax_bands:
        if remaining_income <= 0:
            break

        if band_limit == Decimal("Infinity"):
            taxable_amount = remaining_income
        else:
            taxable_amount = min(remaining_income, band_limit)

        band_tax = taxable_amount * rate / Decimal(100)
        total_tax += band_tax

        remaining_income -= taxable_amount
        taxable_limit += band_limit

    return total_tax / Decimal(12)


def get_water_rate(self):
    return Decimal(150) if self.basic_salary <= 75000 else Decimal(200)


def get_net_pay(self):
    """
    Calculates the net pay for an employee.

    Note: This function assumes that get_gross_income returns an annual value
    and divides it by 12 to get the monthly gross income.
    """
    if not self.employee_pay:
        return Decimal(0.0)
    return (
        (self.employee_pay.get_gross_income / 12)
        - (self.employee_pay.payee)
        - (self.employee_pay.water_rate)
    )


def get_num2words(self):
    return num2words(self.net_pay)


def convert_month_to_word(date_str):
    try:

        year, month = date_str.split("-")
        month = int(month)
        year = int(year)

        if month < 1 or month > 12:
            raise ValueError("Invalid month value")

        month_name = calendar.month_name[month]

        output = f"{month_name} {year}"

        return output

    except ValueError as e:
        print(f"Error: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def log_action(user, action, content_object):
    from payroll.models import AuditTrail

    AuditTrail.objects.create(
        user=user,
        action=action,
        content_object=content_object,
    )


def try_parse_date(date_str):
    """
    Utility function to parse a date string in 'YYYY-MM' format.
    Returns a datetime.date object or None if parsing fails.
    """
    from datetime import datetime

    try:
        return datetime.strptime(date_str, "%Y-%m").date()
    except ValueError:
        return None
