from typing import Any

from payroll.models import AttendanceRecord


def populate_attendance_for_leave(leave_request: Any) -> int:
    if leave_request.status != "APPROVED":
        return 0

    created = 0
    # Weekends and public holidays are not leave days.
    for work_date in leave_request.working_dates():
        _, was_created = AttendanceRecord.objects.update_or_create(
            company=leave_request.employee.company,
            employee=leave_request.employee,
            work_date=work_date,
            defaults={
                "status": AttendanceRecord.Status.LEAVE,
                "hours_worked": 0,
                "notes": f"{leave_request.leave_type} leave",
            },
        )
        created += int(was_created)
    return created
