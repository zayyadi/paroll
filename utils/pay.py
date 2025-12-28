import json
import random
from datetime import datetime, timedelta


MIN_SALARY = 100000
MAX_SALARY = 10000000
NUM_RECORDS = 100
OUTPUT_FILENAME = "payroll_data.json"


def calculate_consolidated_relief(gross_income):
    """Calculates consolidated relief based on common Nigerian tax rules."""

    relief_option1 = 0.20 * gross_income
    relief_option2 = 200000 + (0.01 * gross_income)
    return max(relief_option1, relief_option2)


def calculate_payee(taxable_income):
    """Calculates PAYEE based on simplified Nigerian tax brackets."""
    payee = 0
    income = taxable_income

    bands = [
        (300000, 0.07),
        (300000, 0.11),
        (500000, 0.15),
        (500000, 0.19),
        (1600000, 0.21),
        (float("inf"), 0.24),
    ]

    remaining_income = income
    for amount, rate in bands:
        if remaining_income <= 0:
            break
        taxable_amount = min(remaining_income, amount)
        payee += taxable_amount * rate
        remaining_income -= taxable_amount

    return payee


def generate_payroll_data(num_records):
    """Generates a list of payroll records."""
    payroll_list = []

    if (MAX_SALARY - MIN_SALARY) < num_records:

        salary_pool = [
            random.randint(MIN_SALARY, MAX_SALARY) for _ in range(num_records)
        ]
    else:
        salary_pool = random.sample(range(MIN_SALARY, MAX_SALARY + 1), num_records)

    for i in range(1, num_records + 1):
        basic_salary = float(salary_pool[i - 1])

        basic = basic_salary * 4.8
        housing = basic_salary * 1.2
        transport = basic_salary * 1.2
        bht = basic + housing + transport
        pension_employee = basic * 0.08
        pension_employer = basic * 0.10
        pension = pension_employee + pension_employer
        gross_income = bht + pension_employer
        consolidated_relief = calculate_consolidated_relief(gross_income)
        taxable_income = gross_income - consolidated_relief - pension_employee
        payee = calculate_payee(taxable_income)
        water_rate = 150.00
        nsitf = basic_salary * 0.01

        now = datetime.now()
        random_offset = timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        timestamp = (now - random_offset).strftime("%Y-%m-%d %H:%M:%S")
        updated = now.strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "id": i,
            "basic_salary": f"{basic_salary:.2f}",
            "basic": f"{basic:.2f}",
            "housing": f"{housing:.2f}",
            "transport": f"{transport:.2f}",
            "bht": f"{bht:.2f}",
            "pension_employee": f"{pension_employee:.2f}",
            "pension_employer": f"{pension_employer:.2f}",
            "pension": f"{pension:.2f}",
            "gross_income": f"{gross_income:.2f}",
            "consolidated_relief": f"{consolidated_relief:.2f}",
            "taxable_income": f"{taxable_income:.2f}",
            "payee": f"{payee:.2f}",
            "water_rate": f"{water_rate:.2f}",
            "nsitf": f"{nsitf:.2f}",
            "timestamp": timestamp,
            "updated": updated,
            "status": "active",
        }
        payroll_list.append(record)

    return payroll_list


if __name__ == "__main__":
    print(f"Generating {NUM_RECORDS} payroll records...")
    data = generate_payroll_data(NUM_RECORDS)

    with open(OUTPUT_FILENAME, "w") as f:
        json.dump(data, f, indent=4)

    print(f"Successfully generated {OUTPUT_FILENAME} with {len(data)} records.")
