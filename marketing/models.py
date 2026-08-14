from django.db import models
from django.conf import settings

# Capability catalog used by the competitor-tracking matrix. ``paynest`` is
# PayNest's own status for the capability; vendor rows store the same keys
# in ``Competitor.features`` as yes / no / partial / unknown.
FEATURE_CATALOG = [
    ("statutory_paye", "NTA-2025 PAYE computation", "yes"),
    ("statutory_reports", "Statutory schedules and reports", "yes"),
    ("compliance_calendar", "Compliance calendar and penalty flags", "yes"),
    ("audit_trails", "Audit trails (sensitive access)", "yes"),
    ("segregation", "Segregation of duties", "yes"),
    ("bank_files", "Bank payment files", "yes"),
    ("remita", "Remita / PSP disbursement", "no"),
    ("ewa", "Earned wage access", "partial"),
    ("mobile", "Mobile app / PWA", "no"),
    ("published_pricing", "Published \u20a6 pricing", "yes"),
    ("multi_country", "Multi-country engine", "no"),
    ("eor", "EOR services", "no"),
]

FEATURE_LABELS = {key: label for key, label, _ in FEATURE_CATALOG}
PAYNEST_FEATURE_STATUS = {key: status for key, _, status in FEATURE_CATALOG}


class LeadInquiry(models.Model):
    COMPANY_SIZE_CHOICES = [
        ("1-10", "1-10"),
        ("11-50", "11-50"),
        ("51-200", "51-200"),
        ("201-500", "201-500"),
        ("500+", "500+"),
    ]
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_QUALIFIED = "qualified"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_QUALIFIED, "Qualified"),
        (STATUS_CLOSED, "Closed"),
    ]

    full_name = models.CharField(max_length=120)
    work_email = models.EmailField()
    company_name = models.CharField(max_length=150)
    company_size = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_lead_inquiries",
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.full_name} - {self.company_name}"


class Competitor(models.Model):
    """
    Market-intelligence record: one row per tracked vendor with its current
    pricing, capability matrix, and status, so positioning stays current
    without re-researching the market each quarter.
    """

    class Segment(models.TextChoices):
        LOCAL = "local", "Local (Nigeria)"
        PAN_AFRICAN = "pan_african", "Pan-African"
        GLOBAL = "global", "Global"
        EWA = "ewa", "EWA / Fintech"
        EOR = "eor", "EOR"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEFUNCT = "defunct", "Defunct / Collapsed"
        WATCH = "watch", "Watch"

    FEATURE_VALUES = ["yes", "no", "partial", "unknown"]

    name = models.CharField(max_length=120, unique=True)
    website = models.URLField(blank=True)
    segment = models.CharField(max_length=20, choices=Segment.choices, default=Segment.LOCAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    pricing_summary = models.TextField(
        blank=True,
        help_text="Current published/cited pricing, human-readable.",
    )
    pricing_as_of = models.DateField(
        null=True,
        blank=True,
        help_text="Date the pricing_summary was last verified.",
    )
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Capability map, e.g. {\"statutory_paye\": \"yes\", \"ewa\": \"partial\"}. "
            "Values: yes / no / partial / unknown."
        ),
    )
    positioning_notes = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    last_verified = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["segment", "name"]
        verbose_name = "Competitor"
        verbose_name_plural = "Competitors"

    def __str__(self) -> str:
        return self.name

    def feature_status(self, key: str) -> str:
        status = self.features.get(key)
        return status if status in self.FEATURE_VALUES else "unknown"

    def is_stale(self, as_of) -> bool:
        """True when last_verified is missing or more than 90 days old."""
        if self.last_verified is None:
            return True
        from datetime import timedelta

        return self.last_verified < as_of - timedelta(days=90)


class PricingPlan(models.Model):
    """
    Published \u20a6 pricing tier shown on the marketing pricing page.

    Prices are per employee per month; ``annual_monthly_price`` is the per-
    employee monthly equivalent when billed annually (the toggle swaps between
    the two). ``features`` are the module-gated bullets advertised for the
    tier, kept truthful against the platform's shipped capabilities.
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Per employee per month, billed monthly. Leave blank for custom "
            "(Enterprise) pricing."
        ),
    )
    annual_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Per employee per month when billed annually (shown on Annual).",
    )
    billing_note = models.CharField(
        max_length=120,
        blank=True,
        default="per employee / month",
    )
    max_employees = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Headcount cap for free/entry tiers; blank means unlimited.",
    )
    features = models.JSONField(
        default=list,
        blank=True,
        help_text="Module-gated feature bullets rendered on the pricing page.",
    )
    highlight = models.BooleanField(
        default=False,
        help_text="Featured plan on the pricing page.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Pricing Plan"
        verbose_name_plural = "Pricing Plans"

    def __str__(self) -> str:
        return self.name

    @property
    def is_custom(self) -> bool:
        """True for plans without a published per-user price (Enterprise)."""
        return self.monthly_price is None


class MarketingEvent(models.Model):
    event_name = models.CharField(max_length=120)
    path = models.CharField(max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_events",
    )
    session_key = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_name} @ {self.path}"
