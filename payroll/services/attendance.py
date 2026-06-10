from datetime import timedelta
from typing import Any

from payroll.models import AttendanceRecord


def populate_attendance_for_leave(leave_request: Any) -> int:
    if leave_request.status != "APPROVED":
        return 0

    created = 0
    current = leave_request.start_date
    while current <= leave_request.end_date:
        if current.weekday() < 5:
            _, was_created = AttendanceRecord.objects.update_or_create(
                company=leave_request.employee.company,
                employee=leave_request.employee,
                work_date=current,
                defaults={
                    "status": AttendanceRecord.Status.LEAVE,
                    "hours_worked": 0,
                    "notes": f"{leave_request.leave_type} leave",
                },
            )
            created += int(was_created)
        current += timedelta(days=1)
    return created
