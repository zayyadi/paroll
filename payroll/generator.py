from datetime import datetime
import random

time = datetime.today().strftime("%Y")


_used_emp_numbers = set()
_used_nin_numbers = set()
_used_tin_numbers = set()


def emp_id():
    max_attempts = 1000
    for _ in range(max_attempts):
        number = random.randint(0, 9999)
        emp_id_value = f"EMP-{number}-{time}"
        if emp_id_value not in _used_emp_numbers:
            _used_emp_numbers.add(emp_id_value)
            return emp_id_value

    return f"EMP-{len(_used_emp_numbers)}-{time}"


def nin_no():
    max_attempts = 1000
    for _ in range(max_attempts):
        num = random.randint(11111111111, 99999999999)
        nin_value = f"NG-{num}"
        if nin_value not in _used_nin_numbers:
            _used_nin_numbers.add(nin_value)
            return nin_value

    return f"NG-{11111111111 + len(_used_nin_numbers)}"


def tin_no():
    max_attempts = 1000
    for _ in range(max_attempts):
        num = random.randint(11111111111, 99999999999)
        tin_value = f"TIN-{num}"
        if tin_value not in _used_tin_numbers:
            _used_tin_numbers.add(tin_value)
            return tin_value

    return f"TIN-{11111111111 + len(_used_tin_numbers)}"
