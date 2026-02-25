from decimal import Decimal, ROUND_HALF_UP

from num2words import num2words
import calendar
import logging


RENT_THRESHOLD = Decimal("500000")
MINIMUM_WAGE_MONTHLY = Decimal("70000")
DEFAULT_BASIC_PERCENTAGE = Decimal("40")
DEFAULT_HOUSING_PERCENTAGE = Decimal("10")
DEFAULT_TRANSPORT_PERCENTAGE = Decimal("10")
DEFAULT_PENSION_EMPLOYEE_PERCENTAGE = Decimal("8")
DEFAULT_PENSION_EMPLOYER_PERCENTAGE = Decimal("10")
DEFAULT_NHF_PERCENTAGE = Decimal("2.5")

# Nigeria Tax Act 2025 (effective Jan 1, 2026): annual taxable income bands.
# Tuple format: (upper threshold, rate percent). Final band is open-ended.
PAYE_BANDS = [
    (Decimal("800000"), Decimal("0")),
    (Decimal("3000000"), Decimal("15")),
    (Decimal("12000000"), Decimal("18")),
    (Decimal("25000000"), Decimal("21")),
    (Decimal("50000000"), Decimal("23")),
    (None, Decimal("25")),
]

logger = logging.getLogger(__name__)


def calculate_percentage(value: Decimal, percentage: Decimal) -> Decimal:
    """Calculates a percentage of a given value."""
    return value * percentage / 100


def _resolve_company(payroll):
    company = getattr(payroll, "company", None)
    if company:
        return company

    employee_relation = getattr(payroll, "employee_pay", None)
    if employee_relation is None:
        return None

    try:
        profile = employee_relation.first()
    except Exception:
        return None

    return getattr(profile, "company", None)


def _get_company_payroll_setting(payroll):
    if hasattr(payroll, "_company_payroll_setting_cache"):
        return payroll._company_payroll_setting_cache

    manual_setting = getattr(payroll, "payroll_setting", None)
    if manual_setting is not None:
        payroll._company_payroll_setting_cache = manual_setting
        return manual_setting

    company = _resolve_company(payroll)
    if not company:
        payroll._company_payroll_setting_cache = None
        return None

    from payroll.models import CompanyPayrollSetting

    setting = (
        CompanyPayrollSetting.objects.filter(company=company)
        .prefetch_related("health_insurance_tiers")
        .first()
    )
    payroll._company_payroll_setting_cache = setting
    return setting


def _get_setting_percentage(payroll, field_name: str, default: Decimal) -> Decimal:
    setting = _get_company_payroll_setting(payroll)
    if setting is None:
        return default
    value = getattr(setting, field_name, None)
    if value is None:
        return default
    return Decimal(value)


def get_housing(self):
    return calculate_percentage(
        self.get_annual_gross,
        _get_setting_percentage(self, "housing_percentage", DEFAULT_HOUSING_PERCENTAGE),
    )


def get_transport(self):
    return calculate_percentage(
        self.get_annual_gross,
        _get_setting_percentage(
            self, "transport_percentage", DEFAULT_TRANSPORT_PERCENTAGE
        ),
    )


def get_basic(self):
    return calculate_percentage(
        self.get_annual_gross,
        _get_setting_percentage(self, "basic_percentage", DEFAULT_BASIC_PERCENTAGE),
    )


def gross_income(self):
    gi = get_transport(self) + get_housing(self) + get_basic(self)
    logger.debug("gross_income=%s", gi)
    return gi


def get_pension_employee(self):
    pension = calculate_percentage(
        self.get_annual_gross,
        _get_setting_percentage(
            self, "pension_employee_percentage", DEFAULT_PENSION_EMPLOYEE_PERCENTAGE
        ),
    )
    logger.debug("pension_employee=%s", pension)
    return pension


def get_pension_employer(self):
    return calculate_percentage(
        self.get_annual_gross,
        _get_setting_percentage(
            self, "pension_employer_percentage", DEFAULT_PENSION_EMPLOYER_PERCENTAGE
        ),
    )


def get_pension(self):
    return get_pension_employee(self) + get_pension_employer(self)


def calc_housing(self) -> Decimal:
    if self.is_housing:
        nhf_percentage = _get_setting_percentage(
            self, "nhf_percentage", DEFAULT_NHF_PERCENTAGE
        )
        nhf = self.basic * nhf_percentage / 100
        return nhf
    else:
        return Decimal(0.0)


def _default_health_percentages(basic_salary: Decimal) -> tuple[Decimal, Decimal]:
    if basic_salary >= Decimal("1000000"):
        return Decimal("15"), Decimal("0")
    if basic_salary >= Decimal("500000"):
        return Decimal("10"), Decimal("5")
    return Decimal("5"), Decimal("10")


def _get_health_percentages(self) -> tuple[Decimal, Decimal]:
    setting = _get_company_payroll_setting(self)
    salary = Decimal(self.basic_salary or Decimal("0"))

    if setting:
        tier = setting.get_health_tier_for_salary(salary)
        if tier:
            return Decimal(tier.employee_percentage), Decimal(tier.employer_percentage)

    return _default_health_percentages(salary)


def calc_employer_health_contrib(self) -> Decimal:
    if not self.is_nhif:
        return Decimal(0.0)

    _, employer_percentage = _get_health_percentages(self)
    return self.basic_salary * employer_percentage / Decimal("100")


def calc_employee_health_contrib(self) -> Decimal:
    if not self.is_nhif:
        return Decimal(0.0)

    employee_percentage, _ = _get_health_percentages(self)
    return (self.basic_salary * 12) * employee_percentage / Decimal("100")


def calc_health_contrib(self) -> Decimal:
    return calc_employee_health_contrib(self) + calc_employer_health_contrib(self)


def get_rent_relief(payroll):
    # During initial Payroll.save(), reverse relations may not exist yet.
    if not getattr(payroll, "pk", None):
        return Decimal("0.00")

    profile = payroll.employee_pay.first()  # reverse FK to EmployeeProfile
    if not profile:
        return Decimal("0.00")
    return profile.rent_relief_amount


def get_total_relief(self):
    rent_relief = getattr(self, "rent_relief", None)
    if rent_relief is None:
        rent_relief = get_rent_relief(self)

    tr = (
        rent_relief
        + getattr(self, "employee_health", Decimal("0.00"))
        + getattr(self, "nhf", Decimal("0.00"))
        + getattr(self, "pension_employee", Decimal("0.00"))
    )
    logger.debug("total_relief=%s", tr)
    return tr


def _annual_gross_for_tax(self) -> Decimal:
    annual_gross = getattr(self, "get_annual_gross", None)
    if annual_gross is None:
        basic_salary = getattr(self, "basic_salary", Decimal("0.00"))
        annual_gross = Decimal(basic_salary or Decimal("0.00")) * Decimal("12")
    return Decimal(annual_gross or Decimal("0.00"))


def compute_annual_paye(annual_taxable_income: Decimal) -> Decimal:
    taxable_income = Decimal(annual_taxable_income or Decimal("0.00"))
    total_tax = Decimal("0.00")

    if taxable_income <= 0:
        return total_tax

    previous_threshold = Decimal("0.00")

    for threshold, rate in PAYE_BANDS:
        if taxable_income <= previous_threshold:
            break

        if threshold is None:
            taxable_amount = taxable_income - previous_threshold
            # print(f"threshold1: {taxable_amount}")
        else:
            band_size = threshold - previous_threshold
            taxable_amount = min(taxable_income - previous_threshold, band_size)
            # print(f"threshold2: {taxable_amount}")

        if taxable_amount > 0:
            total_tax += (taxable_amount * rate) / Decimal("100")
            # print(f"threshold3: {taxable_amount}")

        if threshold is not None:
            previous_threshold = threshold
            # print(f"threshold4: {previous_threshold}")

    return total_tax


def calculate_taxable_income(self) -> Decimal:
    # Taxable income is based on annual gross income minus applicable reliefs.
    # Rent relief is employee-specific via get_rent_relief(self).
    calc = gross_income(self) - get_total_relief(self)

    if calc <= 0:
        return Decimal(0.0)
    return calc


def get_payee(self):
    taxable_income = calculate_taxable_income(self)

    if self.basic_salary <= MINIMUM_WAGE_MONTHLY:
        return Decimal(0.0)

    payee = compute_annual_paye(taxable_income) / Decimal("12")
    logger.debug("payee=%s", payee)
    return payee


def get_water_rate(self):
    return Decimal(150) if self.basic_salary <= 75000 else Decimal(200)


def get_net_pay(self):
    """
    Calculates the net pay for an employee.

    Note: This function assumes that get_gross_income returns an annual value
    and divides it by 12 to get the monthly gross income.
    """
    payroll = getattr(self, "employee_pay", None)
    # Allow direct usage with Payroll instance as well.
    if payroll is None and hasattr(self, "basic_salary"):
        payroll = self

    if not payroll:
        return Decimal(0.0)

    annual_gross = Decimal(
        getattr(payroll, "gross_income", Decimal("0.00")) or Decimal("0.00")
    )
    logger.debug("annual_gross=%s", annual_gross)
    if annual_gross <= 0:
        annual_gross = gross_income(payroll)

    employee_health = Decimal(
        getattr(payroll, "employee_health", Decimal("0.00")) or Decimal("0.00")
    )
    logger.debug("employee_health=%s", employee_health)
    nhf = Decimal(getattr(payroll, "nhf", Decimal("0.00")) or Decimal("0.00"))
    logger.debug("nhf=%s", nhf)
    payee = Decimal(getattr(payroll, "payee", Decimal("0.00")) or Decimal("0.00"))
    # print(f"payeess: {payee}")
    water_rate = Decimal(
        getattr(payroll, "water_rate", Decimal("0.00")) or Decimal("0.00")
    )

    return (
        (annual_gross / Decimal("12"))
        - (employee_health / Decimal("12"))
        - (nhf / Decimal("12"))
        - payee
        - water_rate
    )


def get_num2words(self):
    return num2words(self.net_pay)


def format_currency_words_with_kobo(amount) -> str:
    """
    Format a monetary amount as words with explicit naira and 2-digit kobo.
    Example: "Nine Million ... naira Nine Two kobo"
    """
    value = Decimal(str(amount or "0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    naira_part = int(value)
    kobo_part = int((value - Decimal(naira_part)) * 100)

    naira_words = num2words(naira_part).title()
    kobo_digits = f"{kobo_part:02d}"
    kobo_words = " ".join(num2words(int(digit)).title() for digit in kobo_digits)

    return f"{naira_words} naira {kobo_words} kobo"


def convert_month_to_word(date_str):
    try:
        # Accept date-like objects, 'YYYY-MM', and 'YYYY-MM-DD' strings.
        if hasattr(date_str, "year") and hasattr(date_str, "month"):
            year = int(date_str.year)
            month = int(date_str.month)
        else:
            parts = str(date_str).split("-")
            if len(parts) < 2:
                raise ValueError("Invalid date format")
            year = int(parts[0])
            month = int(parts[1])

        if month < 1 or month > 12:
            raise ValueError("Invalid month value")

        month_name = calendar.month_name[month]

        output = f"{month_name} {year}"

        return output

    except ValueError as e:
        return None
    except Exception as e:
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
