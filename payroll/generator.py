from datetime import datetime
import random

time = datetime.today().strftime("%Y")


def emp_id():
    number = random.randint(0, 9999)
    return f"EMP-{number}-{time}"


def nin_no():
    num = random.randint(11111111111, 99999999999)
    return f"NG-{num}"


def tin_no():
    num = random.randint(11111111111, 99999999999)
    return f"TIN-{num}"


# print(nin_no())
