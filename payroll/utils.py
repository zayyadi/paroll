from decimal import Decimal

from num2words import num2words
import calendar


RENT_THRESHOLD = Decimal("500000")
TAX_FREE = Decimal("800000")


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
    return calculate_percentage(self.get_annual_gross, 8)


def get_pension_employer(self):
    return calculate_percentage(self.get_annual_gross, 10)


def get_pension(self):
    return get_pension_employee(self) + get_pension_employer(self)


def get_gross_income(self):
    return (self.basic_salary * 12) - (get_pension_employee(self) * 12)


def calc_housing(self) -> Decimal:
    if self.is_housing:
        return self.get_annual_gross * Decimal(2.5) / 100
    else:
        return Decimal(0.0)


def calc_employer_health_contrib(self) -> Decimal:
    if self.is_nhif:
        return self.get_annual_gross * Decimal(3.25) / 100
    else:
        return Decimal(0.0)


def calc_employee_health_contrib(self) -> Decimal:
    if self.is_nhif:
        return self.get_annual_gross * Decimal(1.75) / 100
    else:
        return Decimal(0.0)


def calc_health_contrib(self) -> Decimal:
    return calc_employee_health_contrib(self) + calc_employer_health_contrib(self)


# def get_rent_relief(employee):
#     # Access rent_paid through the employee_pay relationship (EmployeeProfile)
#     # rent_paid_value = self.employee_pay.rent_paid if self.employee_pay else Decimal(0.0)
#     # rent_relief = calculate_percentage(rent_paid_value, 20)
#     # if rent_relief >= Decimal(RENT_THRESHOLD):
#     #     return Decimal(RENT_THRESHOLD)
#     # return rent_relief

#     # def get_employee_rent_relief(employee):
#     rent_paid = employee.rent_paid or Decimal("0.00")
#     relief = calculate_percentage(rent_paid, Decimal("20"))
#     return min(relief, RENT_THRESHOLD)


def get_rent_relief(payroll):
    profile = payroll.employee_pay.first()  # reverse FK to EmployeeProfile
    rent_paid = profile.rent_paid if profile else Decimal("0.00")
    relief = calculate_percentage(rent_paid, Decimal("20"))
    return min(relief, RENT_THRESHOLD)


def get_total_relief(self):
    return get_rent_relief(self) + self.employee_health + self.nhf


def calculate_taxable_income(self) -> Decimal:
    calc = (self.get_gross_income) - (get_total_relief(self))

    if calc <= 0:
        return Decimal(0.0)
    return calc


# def get_payee(self) -> Decimal:
#     taxable_income = Decimal(self.calculate_taxable_income())


#     if taxable_income <= TAX_FREE:
#         return Decimal("0")

#     remaining_income = taxable_income - TAX_FREE
#     total_tax = Decimal("0")

#     tax_bands = [
#         (Decimal("2200000"), Decimal("15")),
#         (Decimal("9000000"), Decimal("18")),
#         (Decimal("13000000"), Decimal("21")),
#         (Decimal("25000000"), Decimal("23")),
#         (Decimal("Infinity"), Decimal("25")),
#     ]

#     for band_amount, rate in tax_bands:
#         if remaining_income <= 0:
#             break

#         taxable_amount = min(remaining_income, band_amount)
#         total_tax += taxable_amount * rate / Decimal("100")
#         remaining_income -= taxable_amount

#     # Monthly PAYE
#     return total_tax / Decimal("12")


def get_payee(self):
    taxable_income = calculate_taxable_income(self)

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
        - (self.employee_pay.employee_health)
        - (self.employee_pay.nhf)
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


# def export_lirs_form_a8(remittances, year):
#     wb = Workbook()
#     ws = wb.active
#     ws.title = "LIRS FORM A8"

#     headers = [
#         "Employer TIN",
#         "Employer Name",
#         "Employee Name",
#         "Employee TIN",
#         "Annual Gross",
#         "Annual Taxable",
#         "Annual PAYE",
#         "Year",
#     ]
#     ws.append(headers)

#     for r in remittances:
#         ws.append([
#             r.employer_tin,
#             r.employer_name,
#             r.employee.full_name,
#             r.employee_tin,
#             float(r.gross_income),
#             float(r.taxable_income),
#             float(r.paye),
#             year,
#         ])

#     response = HttpResponse(
#         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#     )
#     response["Content-Disposition"] = f"attachment; filename=LIRS_Form_A8_{year}.xlsx"

#     wb.save(response)
#     return response
