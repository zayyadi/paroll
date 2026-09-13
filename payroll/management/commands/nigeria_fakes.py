import random

NIGERIAN_DEMO_COMPANY = "Paroll Nigeria Demo Ltd"

FIRST_NAMES = [
    "Adaeze", "Adebayo", "Amina", "Chiamaka", "Chinedu", "Emeka",
    "Fatima", "Funmilayo", "Hauwa", "Ifeoma", "Kelechi", "Musa",
    "Ngozi", "Obinna", "Olamide", "Oluwaseun", "Sadiya", "Tunde",
    "Uche", "Yakubu", "Zainab",
]

LAST_NAMES = [
    "Abubakar", "Adeyemi", "Afolabi", "Bello", "Chukwu", "Eze",
    "Ibrahim", "Ilori", "Lawal", "Mbah", "Nwosu", "Obi",
    "Okafor", "Okonkwo", "Oladipo", "Oyekan", "Sule", "Uzoma",
]

LOCATIONS = [
    ("Adeola Odeku Street", "Victoria Island", "Lagos", "Lagos State"),
    ("Ahmadu Bello Way", "Central Business District", "Abuja", "FCT"),
    ("Rivers State Road", "GRA", "Port Harcourt", "Rivers State"),
    ("Zaria Road", "Nassarawa", "Kano", "Kano State"),
    ("Ring Road", "Bodija", "Ibadan", "Oyo State"),
    ("Nkwuba Road", "Independence Layout", "Enugu", "Enugu State"),
    ("Sapele Road", "GRA", "Benin City", "Edo State"),
    ("Lafiya Road", "Lugbe", "Abuja", "FCT"),
]

NIGERIAN_BANKS = [
    ("GTB", "Guaranty Trust Bank"),
    ("Zenith", "Zenith Bank"),
    ("Access", "Access Bank"),
    ("UBA", "United Bank for Africa"),
    ("FBN", "First Bank of Nigeria"),
    ("FCMB", "First City Monument Bank"),
    ("Union", "Union Bank of Nigeria"),
    ("Jaiz", "Jaiz Bank"),
    ("Sterling", "Sterling Bank"),
    ("Wema", "Wema Bank"),
]

HMO_PROVIDERS = [
    "AXA", "AVON", "CLEARLINE", "HYGEIA", "INTEGRATED",
    "RELIANCE", "TOTALHEALTH", "WELLNESS",
]

PENSION_FUND_MANAGERS = [
    "AIICO", "APT", "ARM", "FCMB", "FIDELITY", "IEI", "OAK",
    "PAL", "PENCOM", "SIGMA", "STANBIC", "TRUSTFUND", "VERITAS",
]


def nigerian_first_name():
    return random.choice(FIRST_NAMES)


def nigerian_last_name():
    return random.choice(LAST_NAMES)


def nigerian_name():
    return f"{nigerian_first_name()} {nigerian_last_name()}"


def nigerian_phone_number():
    prefix = random.choice(
        ["0803", "0805", "0806", "0807", "0808", "0809", "0810", "0811",
         "0813", "0814", "0815", "0816", "0817", "0818", "0901", "0902"]
    )
    subscriber = f"{random.randint(0, 9999999):07d}"
    return f"+234 {prefix[1:]} {subscriber[:3]} {subscriber[3:]}"


def nigerian_address():
    street, area, city, state = random.choice(LOCATIONS)
    return f"{random.randint(1, 250)} {street}, {area}, {city}, {state}, Nigeria"


def nigerian_nin():
    return f"{random.randint(10000000000, 99999999999)}"


def nigerian_tin():
    return f"{random.randint(1000000000, 9999999999)}"


def nigerian_pension_rsa():
    return f"RSA-{random.randint(10000000000, 99999999999)}"


def nigerian_bank():
    return random.choice(NIGERIAN_BANKS)


def nigerian_hmo_provider():
    return random.choice(HMO_PROVIDERS)


def nigerian_pension_fund_manager():
    return random.choice(PENSION_FUND_MANAGERS)
