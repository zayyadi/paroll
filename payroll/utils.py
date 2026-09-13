from decimal import Decimal, ROUND_HALF_UP

try:
    from num2words import num2words
except ImportError:  # pragma: no cover - fallback for constrained environments
    def num2words(value, **kwargs):
        return str(value)
import calendar
import logging
from datetime import date


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
# These are the built-in fallback when no StatutoryRateVersion rows exist;
# when the version table is populated, rates resolve by effective date so
# retrospective runs use the regime in force for their pay period.
PAYE_BANDS = [
    (Decimal("800000"), Decimal("0")),
    (Decimal("3000000"), Decimal("15")),
    (Decimal("12000000"), Decimal("18")),
    (Decimal("25000000"), Decimal("21")),
    (Decimal("50000000"), Decimal("23")),
    (None, Decimal("25")),
]

# Personal Income Tax Act bands as amended by the Finance Acts (pre-NTA),
# used by the seeded pre-2026 statutory rate versions.
PITA_PAYE_BANDS = [
    (Decimal("300000"), Decimal("7")),
    (Decimal("600000"), Decimal("11")),
    (Decimal("1100000"), Decimal("15")),
    (Decimal("1600000"), Decimal("19")),
    (Decimal("3200000"), Decimal("21")),
    (None, Decimal("24")),
]

# National reference data: statutory rate versions are shared across tenants
# by design (see tenant-isolation matrix 3.3), so this key intentionally does
# NOT go through tenant_cache_key.
_STATUTORY_VERSIONS_CACHE_KEY = "payroll.statutory_rate_versions.v1"
_STATUTORY_VERSIONS_CACHE_TTL = 300

logger = logging.getLogger(__name__)


def _statutory_versions():
    """All StatutoryRateVersion rows, oldest first, cached briefly."""
    from django.core.cache import cache

    versions = cache.get(_STATUTORY_VERSIONS_CACHE_KEY)
    if versions is None:
        from payroll.models import StatutoryRateVersion

        versions = list(StatutoryRateVersion.objects.order_by("effective_date"))
        cache.set(
            _STATUTORY_VERSIONS_CACHE_KEY, versions, _STATUTORY_VERSIONS_CACHE_TTL
        )
    return versions


def statutory_rates_for(as_of=None):
    """
    Resolve the statutory rates in force on ``as_of`` (default: today).

    Returns a dict with the effective PAYE bands, minimum wage, pension, and
    NHF rates. Falls back to the built-in Nigeria Tax Act 2025 defaults when
    no version rows exist (e.g. before the data migration has run).
    """
    target = as_of or date.today()
    resolved = None
    for version in _statutory_versions():
        if version.effective_date <= target:
            resolved = version
        else:
            break

    if resolved is None:
        return {
            "paye_bands": PAYE_BANDS,
            "minimum_wage_monthly": MINIMUM_WAGE_MONTHLY,
            "pension_employee_percentage": DEFAULT_PENSION_EMPLOYEE_PERCENTAGE,
            "pension_employer_percentage": DEFAULT_PENSION_EMPLOYER_PERCENTAGE,
            "nhf_percentage": DEFAULT_NHF_PERCENTAGE,
        }

    return {
        "paye_bands": [
            (Decimal(str(upper)) if upper is not None else None, Decimal(str(rate)))
            for upper, rate in resolved.paye_bands
        ],
        "minimum_wage_monthly": Decimal(resolved.minimum_wage_monthly),
        "pension_employee_percentage": Decimal(
            resolved.pension_employee_percentage
        ),
        "pension_employer_percentage": Decimal(
            resolved.pension_employer_percentage
        ),
        "nhf_percentage": Decimal(resolved.nhf_percentage),
    }


def get_paye_bands(as_of=None):
    """PAYE bands in force on ``as_of`` as (upper|None, rate) tuples."""
    return statutory_rates_for(as_of)["paye_bands"]


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
    # Only memoize a found setting: caching None would freeze this instance
    # on a pre-setting state, so a later save() after the company's payroll
    # setting is created (e.g. enabling ITF) would miss it.
    if setting is not None:
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


def _pension_percentage(self, field_name, default, as_of):
    # Company-level override wins; otherwise the effective-dated statutory
    # version; otherwise the built-in default.
    percentage = _get_setting_percentage(self, field_name, None)
    if percentage is None:
        percentage = statutory_rates_for(as_of)[field_name]
    if percentage is None:
        percentage = default
    return Decimal(percentage)


def get_pension_employee(self, as_of=None):
    percentage = _pension_percentage(
        self, "pension_employee_percentage", DEFAULT_PENSION_EMPLOYEE_PERCENTAGE, as_of
    )
    pension = calculate_percentage(self.get_annual_gross, percentage)
    logger.debug("pension_employee=%s", pension)
    return pension


def get_pension_employer(self, as_of=None):
    percentage = _pension_percentage(
        self, "pension_employer_percentage", DEFAULT_PENSION_EMPLOYER_PERCENTAGE, as_of
    )
    return calculate_percentage(self.get_annual_gross, percentage)


def get_pension(self, as_of=None):
    return get_pension_employee(self, as_of=as_of) + get_pension_employer(
        self, as_of=as_of
    )


def calc_housing(self, as_of=None) -> Decimal:
    # NHF is deducted when the legacy is_housing switch is on or the employee
    # is classified under either NHF scheme (compulsory/voluntary).
    nhf_scheme = getattr(self, "nhf_scheme", "none") or "none"
    if self.is_housing or nhf_scheme != "none":
        nhf_percentage = _get_setting_percentage(self, "nhf_percentage", None)
        if nhf_percentage is None:
            nhf_percentage = statutory_rates_for(as_of)["nhf_percentage"]
        if nhf_percentage is None:
            nhf_percentage = DEFAULT_NHF_PERCENTAGE
        nhf = self.basic * Decimal(nhf_percentage) / 100
        return nhf
    else:
        return Decimal(0.0)


# NHIA Act 2022 statutory splits by contribution basis:
#   basic        -> employee 5% / employer 10% of monthly basic salary
#   consolidated -> employee 1.75% / employer 3.25% of monthly consolidated
#                   salary (basic + housing + transport)
STATUTORY_HEALTH_SPLITS = {
    "basic": (Decimal("5"), Decimal("10")),
    "consolidated": (Decimal("1.75"), Decimal("3.25")),
}


def _health_basis(self) -> str:
    setting = _get_company_payroll_setting(self)
    basis = getattr(setting, "health_basis", None)
    return basis or "basic"


def _health_premium(self):
    """Per-employee monthly HMO premium override, or None when not set."""
    setting = _get_company_payroll_setting(self)
    premium = getattr(setting, "hmo_monthly_premium", None)
    if premium:
        return Decimal(premium)
    return None


def _statutory_health_percentages(basis: str) -> tuple[Decimal, Decimal]:
    return STATUTORY_HEALTH_SPLITS.get(basis, STATUTORY_HEALTH_SPLITS["basic"])


def _get_health_percentages(self) -> tuple[Decimal, Decimal]:
    """
    Employee/employer NHIA percentages for ``self``.

    An explicitly configured health-insurance tier wins; otherwise the
    statutory split for the company's contribution basis applies.
    """
    setting = _get_company_payroll_setting(self)
    salary = Decimal(self.basic_salary or Decimal("0"))

    if setting:
        tier = setting.get_health_tier_for_salary(salary)
        if tier:
            return Decimal(tier.employee_percentage), Decimal(tier.employer_percentage)

    return _statutory_health_percentages(_health_basis(self))


def _health_contribution_base(self, basis: str) -> Decimal:
    """Monthly base the NHIA percentage applies to for the given basis."""
    if basis == "consolidated":
        annual_gross = getattr(self, "gross_income", None)
        if annual_gross is None:
            annual_gross = getattr(self, "get_gross_income", Decimal("0")) or Decimal("0")
        return Decimal(annual_gross) / Decimal("12")
    return Decimal(getattr(self, "basic_salary", Decimal("0")) or Decimal("0"))


def calc_employee_health_contrib(self) -> Decimal:
    if not self.is_nhif:
        return Decimal(0.0)

    employee_percentage, _ = _get_health_percentages(self)
    employee_contrib = (
        _health_contribution_base(self, _health_basis(self))
        * employee_percentage
        / Decimal("100")
    )
    premium = _health_premium(self)
    if premium is not None:
        # The employee's statutory share is never more than the premium.
        employee_contrib = min(employee_contrib, premium)
    return employee_contrib


def calc_employer_health_contrib(self) -> Decimal:
    if not self.is_nhif:
        return Decimal(0.0)

    employee_percentage, employer_percentage = _get_health_percentages(self)
    base = _health_contribution_base(self, _health_basis(self))
    premium = _health_premium(self)
    if premium is not None:
        employee_contrib = min(base * employee_percentage / Decimal("100"), premium)
        # Employer tops the negotiated premium up to the employee's statutory share.
        return max(premium - employee_contrib, Decimal("0.00"))
    return base * employer_percentage / Decimal("100")


def calc_health_contrib(self) -> Decimal:
    return calc_employee_health_contrib(self) + calc_employer_health_contrib(self)


def _employer_levy_applies(self, field_name: str, default: bool) -> bool:
    setting = _get_company_payroll_setting(self)
    if setting is None:
        return default
    return bool(getattr(setting, field_name, default))


def get_nsitf(self) -> Decimal:
    """NSITF Employees' Compensation: 1% of monthly basic, employer-paid."""
    if not _employer_levy_applies(self, "nsitf_applicable", True):
        return Decimal("0.00")
    return self.basic_salary * Decimal("1") / Decimal("100")


def get_itf(self) -> Decimal:
    """ITF training levy: 1% of annual gross, employer-paid, if applicable."""
    if not _employer_levy_applies(self, "itf_applicable", False):
        return Decimal("0.00")
    return self.gross_income * Decimal("1") / Decimal("100")


def monthly_cost_breakdown(config) -> dict:
    """
    Monthly employer-vs-employee cost figures for one pay config.

    Conventions match the Cost of Employment report: annual stored fields
    (gross, pension, NHF, NHIA, ITF) are divided by 12; PAYE and water are
    monthly; NSITF is 1% of monthly basic. Employer cost = gross + all
    employer-funded levies (pension, NHIA, NSITF, ITF).
    """
    cents = Decimal("0.01")
    gross = (Decimal(config.gross_income or 0) / Decimal("12")).quantize(cents)
    employee_paye = Decimal(config.payee or 0).quantize(cents)
    employee_pension = (
        Decimal(config.pension_employee or 0) / Decimal("12")
    ).quantize(cents)
    employee_nhf = (Decimal(config.nhf or 0) / Decimal("12")).quantize(cents)
    employee_nhia = (
        Decimal(config.employee_health or 0) / Decimal("12")
    ).quantize(cents)
    employee_water = Decimal(config.water_rate or 0).quantize(cents)
    net_pay = (
        gross
        - employee_paye
        - employee_pension
        - employee_nhf
        - employee_nhia
        - employee_water
    ).quantize(cents)
    employer_pension = (
        Decimal(config.pension_employer or 0) / Decimal("12")
    ).quantize(cents)
    employer_nhia = (
        Decimal(config.emplyr_health or 0) / Decimal("12")
    ).quantize(cents)
    employer_nsitf = Decimal(config.nsitf or 0).quantize(cents)
    employer_itf = (Decimal(config.itf or 0) / Decimal("12")).quantize(cents)
    employer_cost = (
        gross + employer_pension + employer_nhia + employer_nsitf + employer_itf
    ).quantize(cents)
    return {
        "gross": gross,
        "employee_paye": employee_paye,
        "employee_pension": employee_pension,
        "employee_nhf": employee_nhf,
        "employee_nhia": employee_nhia,
        "employee_water": employee_water,
        "net_pay": net_pay,
        "employer_pension": employer_pension,
        "employer_nhia": employer_nhia,
        "employer_nsitf": employer_nsitf,
        "employer_itf": employer_itf,
        "employer_cost": employer_cost,
    }


def health_contribution_summary(self) -> dict:
    """
    Human-readable NHIA mode for reports: basis, percentages, premium.

    Percentages are the effective ones for this employee (tier or statutory).
    """
    basis = _health_basis(self)
    employee_percentage, employer_percentage = _get_health_percentages(self)
    summary = {
        "basis": basis,
        "employee_percentage": employee_percentage,
        "employer_percentage": employer_percentage,
        "premium": _health_premium(self),
    }
    basis_label = "Consolidated salary" if basis == "consolidated" else "Basic salary"
    if summary["premium"] is not None:
        summary["label"] = (
            f"HMO premium \u20a6{summary['premium']:,.2f} per employee/month "
            f"(employee share {employee_percentage}%)"
        )
    else:
        summary["label"] = (
            f"{basis_label} basis \u2014 employee {employee_percentage}% / "
            f"employer {employer_percentage}%"
        )
    return summary


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


def compute_annual_paye(annual_taxable_income: Decimal, as_of=None) -> Decimal:
    taxable_income = Decimal(annual_taxable_income or Decimal("0.00"))
    total_tax = Decimal("0.00")

    if taxable_income <= 0:
        return total_tax

    previous_threshold = Decimal("0.00")

    for threshold, rate in get_paye_bands(as_of):
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
    calc = _annual_gross_for_tax(self) - get_total_relief(self)

    if calc <= 0:
        return Decimal(0.0)
    return calc


def get_payee(self, as_of=None):
    taxable_income = calculate_taxable_income(self)

    minimum_wage = statutory_rates_for(as_of)["minimum_wage_monthly"]
    if self.basic_salary <= minimum_wage:
        return Decimal(0.0)

    payee = compute_annual_paye(taxable_income, as_of=as_of) / Decimal("12")
    logger.debug("payee=%s", payee)
    return payee


def get_water_rate(self):
    """Monthly water-rate deduction governed by CompanyPayrollSetting.

    Defaults (150 at/below ₦75,000, else 200) preserve legacy behavior when
    no company setting exists. Configure per-tenant via water_rate_* fields.
    """
    low = Decimal(150)
    high = Decimal(200)
    threshold = Decimal(75000)
    try:
        from payroll.models import CompanyPayrollSetting

        setting = None
        company_id = getattr(getattr(self, "company", None), "id", None) or getattr(
            self, "company_id", None
        )
        if company_id:
            setting = CompanyPayrollSetting.objects.filter(
                company_id=company_id
            ).first()
        else:
            employee = getattr(self, "employee_pay", None)
            if employee is not None:
                # Payroll config rows may carry company via related profile.
                company_id = getattr(getattr(employee, "first", lambda: None)(), "company_id", None)
                if company_id:
                    setting = CompanyPayrollSetting.objects.filter(
                        company_id=company_id
                    ).first()
        if setting is not None:
            low = Decimal(setting.water_rate_low or low)
            high = Decimal(setting.water_rate_high or high)
            threshold = Decimal(setting.water_rate_threshold or threshold)
    except Exception:
        pass
    basic = Decimal(getattr(self, "basic_salary", 0) or 0)
    return low if basic <= threshold else high


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
