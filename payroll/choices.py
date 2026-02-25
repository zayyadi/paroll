CONTRACT_TYPE = (("P", "Permanent"), ("T", "Temporary"))

GENDER = (
    ("others", "Others"),
    ("male", "Male"),
    ("female", "Female"),
)

LEVEL = (
    ("C", "Casual"),
    ("JS", "Junior staff"),
    ("OP", "Operator"),
    ("SU", "Supervisor"),
    ("M", "Manager"),
    ("COO", "C.O.O"),
    # ("S", "Store Control Officer"),
)


ALLOWANCES = (
    ("NULL", "NULL"),
    ("LV", "Leave Allowance"),
    ("13th", "13th Month"),
    ("Ovr", "Overtime"),
)

DEDUCTIONS = (
    ("NULL", "NULL"),
    ("IOU", "IOU Repayment"),
    ("LT", "Lateness"),
    ("AB", "Absensce"),
    ("DM", "Damages"),
    ("MISC", "Miscellenous"),
)

PAYMENT_METHOD = (
    ("B", "BANK PAYMENT"),
    ("H", "HAND PAYMENT"),
)

BANK = (
    ("Zenith", "Zenith BANK"),
    ("Access", "Access Bank"),
    ("GTB", "GT Bank"),
    ("Jaiz", "JAIZ Bank"),
    ("FCMB", "FCMB"),
    ("FBN", "First Bank"),
    ("Union", "Union Bank"),
    ("UBA", "UBA"),
)

HMO_PROVIDERS = (
    ("AXA", "AXA Mansard Health"),
    ("AVON", "Avon HMO"),
    ("CLEARLINE", "Clearline HMO"),
    ("HYGEIA", "Hygeia HMO"),
    ("INTEGRATED", "Integrated Healthcare Limited"),
    ("RELIANCE", "Reliance HMO"),
    ("TOTALHEALTH", "Total Health Trust"),
    ("WELLNESS", "Wellness Healthcare"),
)

PENSION_FUND_MANAGERS = (
    ("AIICO", "AIICO Pension Managers"),
    ("APT", "APT Pension Funds Managers"),
    ("ARM", "ARM Pension Managers"),
    ("FCMB", "FCMB Pensions"),
    ("FIDELITY", "Fidelity Pension Managers"),
    ("IEI", "IEI-Anchor Pensions"),
    ("OAK", "OAK Pensions"),
    ("PAL", "PAL Pensions"),
    ("PENCOM", "Pension Alliance Limited"),
    ("SIGMA", "Sigma Pensions"),
    ("STANBIC", "Stanbic IBTC Pension Managers"),
    ("TRUSTFUND", "Trustfund Pensions"),
    ("VERITAS", "Veritas Glanvills Pensions"),
)

STATUS = (
    ("active", "ACTIVE"),
    ("pending", "PENDING"),
    ("suspended", "SUSPENDED"),
    ("terminated", "TERMINATED"),
)


# RSAs = (
#     ("LFA", )
# )
