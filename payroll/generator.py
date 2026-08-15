from datetime import datetime
import random
import threading

time = datetime.today().strftime("%Y")


_used_emp_numbers = set()
_used_nin_numbers = set()
_used_tin_numbers = set()

# Serialize check-and-add: without a lock, two companies creating employees
# concurrently can both pass the ``not in`` check before either adds, and the
# shared generator hands both the same emp_id (a per-company-unique key).
_emp_id_lock = threading.Lock()


def emp_id():
    max_attempts = 1000
    with _emp_id_lock:
        for _ in range(max_attempts):
            number = random.randint(0, 9999)
            emp_id_value = f"EMP-{number}-{time}"
            if emp_id_value not in _used_emp_numbers:
                _used_emp_numbers.add(emp_id_value)
                return emp_id_value

        # Exhaustive ordered scan: the length-based fallback was not unique
        # (multiple concurrent fallbacks can read the same length), and a
        # ``len`` value can also collide with an already-used random number.
        # Scanning 0..9999 in order is guaranteed to find an unused value and
        # stays unique under the lock.
        for number in range(10000):
            emp_id_value = f"EMP-{number}-{time}"
            if emp_id_value not in _used_emp_numbers:
                _used_emp_numbers.add(emp_id_value)
                return emp_id_value

        raise RuntimeError("emp_id space exhausted (all 10000 values in use)")


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
