import json
import random
from datetime import datetime

# Load the employee profiles
with open("employee_profiles.json", "r") as f:
    employee_profiles = json.load(f)

# Generate PayVar data for each employee
payvar_data = []

for employee in employee_profiles:
    # Generate PayVar information
    payvar = {
        "employee": employee["id"],  # Link to employee profile ID
        "basic_salary": random.randint(50000, 200000),  # Monthly basic salary in Naira
        "housing_allowance": random.randint(10000, 50000),
        "transport_allowance": random.randint(5000, 20000),
        "medical_allowance": random.randint(2000, 10000),
        "meal_allowance": random.randint(2000, 10000),
        "utility_allowance": random.randint(2000, 10000),
        "entertainment_allowance": random.randint(1000, 5000),
        "leave_allowance": random.randint(1000, 5000),
        "overtime_allowance": 0,  # Will be calculated separately
        "bonus": random.choice(
            [0, 0, 0, 0, 0, random.randint(10000, 50000)]
        ),  # Occasional bonus
        "deductions": {
            "paye": 0,  # Will be calculated
            "pension": random.randint(2000, 10000),
            "nhf": random.randint(1000, 5000),  # National Housing Fund
            "health_insurance": random.randint(2000, 8000),
            "life_assurance": random.randint(1000, 5000),
            "other_deductions": random.randint(0, 5000),
        },
        "month": datetime.now().month,
        "year": datetime.now().year,
        "payment_date": f"{datetime.now().year}-{datetime.now().month:02d}-25",  # Last day of month
        "payment_method": random.choice(["B", "H"]),  # Bank or Hand payment
        "status": "processed",  # processed, pending, failed
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Calculate gross salary
    payvar["gross_salary"] = (
        payvar["basic_salary"]
        + payvar["housing_allowance"]
        + payvar["transport_allowance"]
        + payvar["medical_allowance"]
        + payvar["meal_allowance"]
        + payvar["utility_allowance"]
        + payvar["entertainment_allowance"]
        + payvar["leave_allowance"]
        + payvar["overtime_allowance"]
        + payvar["bonus"]
    )

    # Calculate total deductions
    payvar["total_deductions"] = sum(payvar["deductions"].values())

    # Calculate net salary
    payvar["net_salary"] = payvar["gross_salary"] - payvar["total_deductions"]

    payvar_data.append(payvar)

# Save to JSON file
with open("payvar_data.json", "w") as f:
    json.dump(payvar_data, f, indent=2)

print(
    f"Generated PayVar data for {len(payvar_data)} employees and saved to payvar_data.json"
)
