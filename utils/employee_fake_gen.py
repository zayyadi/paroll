import json
import random
from faker import Faker
from datetime import datetime

fake = Faker()


def generate_employee(emp_id, user_id):
    first_name = fake.first_name()
    last_name = fake.last_name()
    slug = f"{first_name.lower()}-{last_name.lower()}"
    email = f"{first_name.lower()}.{last_name.lower()}@example.com"

    return {
        "id": emp_id,
        "deleted_at": "",
        "emp_id": f"EMP-{random.randint(1000,9999)}-2025",
        "slug": slug,
        "department": random.randint(1, 3),
        "user": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "employee_pay": random.randint(1, 10),
        "created": fake.date_time_this_year().strftime("%Y-%m-%d %H:%M:%S"),
        "photo": "default.png",
        "nin": f"NG-{random.randint(10000000000,99999999999)}",
        "tin_no": f"TIN-{random.randint(10000000000,99999999999)}",
        "pension_rsa": f"RSA-{random.randint(10000000000,99999999999)}",
        "date_of_birth": fake.date_of_birth(minimum_age=22, maximum_age=60).strftime(
            "%Y-%m-%d"
        ),
        "date_of_employment": fake.date_between(
            start_date="-5y", end_date="today"
        ).strftime("%Y-%m-%d"),
        "contract_type": random.choice(["P", "C"]),  # Permanent or Contract
        "phone": f"+234 {random.randint(800,899)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
        "gender": random.choice(["male", "female"]),
        "address": fake.address(),
        "emergency_contact_name": fake.name(),
        "emergency_contact_relationship": random.choice(
            ["Brother", "Sister", "Friend", "Parent", "Spouse"]
        ),
        "emergency_contact_phone": f"+234 {random.randint(800,899)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
        "next_of_kin_name": fake.name(),
        "next_of_kin_relationship": random.choice(
            ["Brother", "Sister", "Friend", "Parent", "Spouse"]
        ),
        "next_of_kin_phone": f"+234 {random.randint(800,899)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
        "job_title": random.choice(
            ["Engineer", "Manager", "Analyst", "Designer", "COO", "JS", "HR", "Admin"]
        ),
        "bank": random.choice(["GTB", "Zenith", "FBN", "FCMB", "UBA", "Access"]),
        "bank_account_name": f"{first_name} {last_name}",
        "bank_account_number": str(random.randint(1000000000, 9999999999)),
        "net_pay": f"{random.uniform(40000, 1200000):.2f}",
        "status": random.choice(["active", "pending"]),
    }


# Generate 100 mock entries
employees = [
    generate_employee(i, i) for i in range(6, 106)
]  # IDs continue from 6 since 1–5 already exist

# Print JSON
print(json.dumps(employees, indent=4))
