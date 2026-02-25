from django.core.management.base import BaseCommand
from payroll.models import (
    Payroll,
    PayrollEntry,
    PayrollRun,
    PayrollRunEntry,
    Allowance,
    Deduction,
    IOU,
    IOUDeduction,
    LeaveRequest,
    LeavePolicy,
    EmployeeProfile,
)
from monthyear.models import MonthField
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random
from faker import Faker

fake = Faker()


class Command(BaseCommand):
    help = "Creates fake payroll data for testing the payroll system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=12,
            help="Number of months to generate payroll for (default: 12)",
        )
        parser.add_argument(
            "--include-allowances",
            action="store_true",
            help="Generate allowances for employees",
        )
        parser.add_argument(
            "--include-deductions",
            action="store_true",
            help="Generate deductions for employees",
        )
        parser.add_argument(
            "--include-iou",
            action="store_true",
            help="Generate IOU records for employees",
        )
        parser.add_argument(
            "--include-leave",
            action="store_true",
            help="Generate leave requests and policies",
        )

    def handle(self, *args, **options):
        months_count = options["count"]
        include_allowances = options["include_allowances"]
        include_deductions = options["include_deductions"]
        include_iou = options["include_iou"]
        include_leave = options["include_leave"]

        self.stdout.write("Creating fake payroll data...")

        # Get all active employees
        employees = EmployeeProfile.objects.filter(status="active")

        if not employees.exists():
            self.stdout.write(
                self.style.ERROR(
                    "No active employees found. Run create_fake_employees first."
                )
            )
            return

        # Create payroll records for each employee
        payroll_records = self._create_payroll_records(employees)

        # Create pay periods
        pay_periods = self._create_pay_periods(months_count)

        # Create PayrollEntry records and link to pay periods
        self._create_pay_var_records(employees, payroll_records, pay_periods)

        # Create allowances if requested
        if include_allowances:
            self._create_allowances(employees, pay_periods)

        # Create deductions if requested
        if include_deductions:
            self._create_deductions(employees, pay_periods)

        # Create IOU records if requested
        if include_iou:
            ious = self._create_iou_records(employees)
            self._create_iou_deductions(ious, pay_periods)

        # Create leave policies and requests if requested
        if include_leave:
            self._create_leave_policies()
            self._create_leave_requests(employees)

        self.stdout.write(self.style.SUCCESS("Fake payroll data generation complete!"))

    def _create_payroll_records(self, employees):
        """Create payroll records for employees"""
        self.stdout.write("Creating payroll records...")

        payroll_records = {}

        for employee in employees:
            # Generate realistic salary based on job title
            salary_ranges = {
                "C": (30000, 60000),  # Casual
                "JS": (60000, 120000),  # Junior Staff
                "OP": (120000, 200000),  # Operator
                "SU": (200000, 350000),  # Supervisor
                "M": (350000, 500000),  # Manager
                "COO": (500000, 800000),  # COO
            }

            job_title = employee.job_title or "C"
            min_salary, max_salary = salary_ranges.get(job_title, (30000, 60000))
            basic_salary = Decimal(str(random.randint(min_salary, max_salary)))

            payroll, created = Payroll.objects.get_or_create(
                basic_salary=basic_salary,
                defaults={
                    "status": "active",
                },
            )

            payroll_records[employee] = payroll

            # Link to employee
            employee.employee_pay = payroll
            employee.save()

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created payroll for {employee.first_name} {employee.last_name}: ₦{basic_salary}"
                    )
                )

        return payroll_records

    def _create_pay_periods(self, months_count):
        """Create pay periods for the specified number of months"""
        self.stdout.write(f"Creating pay periods for {months_count} months...")

        pay_periods = []
        current_date = timezone.now().date()

        for i in range(months_count):
            # Calculate month and year for this period
            period_date = current_date - timedelta(days=30 * i)
            month = period_date.month
            year = period_date.year

            # Create PayrollRun record
            pay_period, created = PayrollRun.objects.get_or_create(
                paydays=date(year, month, 1),
                defaults={
                    "name": f"Payroll {month:02d}/{year}",
                    "is_active": month == current_date.month,
                    "closed": i > 2,  # Close older periods
                },
            )

            pay_periods.append(pay_period)

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created pay period: {month:02d}/{year}")
                )

        return pay_periods

    def _create_pay_var_records(self, employees, payroll_records, pay_periods):
        """Create PayrollEntry records and link to pay periods"""
        self.stdout.write("Creating PayrollEntry records...")

        for employee in employees:
            payroll = payroll_records[employee]

            # Create one PayrollEntry per employee, then link to all pay periods
            pay_var, created = PayrollEntry.objects.get_or_create(
                pays=employee,
                defaults={
                    "is_housing": random.choice([True, False]),
                    "is_nhif": random.choice([True, False]),
                    "status": "active",
                },
            )

            # Link this PayrollEntry to all pay periods
            for pay_period in pay_periods:
                # Create PayrollRunEntry linkage with unique constraint
                payday, created = PayrollRunEntry.objects.get_or_create(
                    payroll_run=pay_period,
                    payroll_entry=pay_var,
                )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created PayrollEntry for {employee.first_name} {employee.last_name}"
                    )
                )

    def _create_allowances(self, employees, pay_periods):
        """Create allowances for employees"""
        self.stdout.write("Creating allowances...")

        allowance_types = [
            ("LV", "Leave Allowance"),
            ("13th", "13th Month"),
            ("Ovr", "Overtime"),
            ("NULL", "Other"),
        ]

        for employee in employees:
            for pay_period in pay_periods:
                # Randomly decide if this employee gets an allowance this period
                if random.random() < 0.3:  # 30% chance
                    allowance_type, description = random.choice(allowance_types)

                    # Generate allowance amount based on salary
                    base_salary = employee.employee_pay.basic_salary
                    allowance_amount = Decimal(
                        str(
                            random.uniform(
                                base_salary * 0.05,  # 5% of salary
                                base_salary * 0.15,  # 15% of salary
                            )
                        )
                    )

                    allowance = Allowance.objects.create(
                        employee=employee,
                        allowance_type=allowance_type,
                        amount=allowance_amount,
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created {description} of ₦{allowance_amount} for {employee.first_name}"
                        )
                    )

    def _create_deductions(self, employees, pay_periods):
        """Create deductions for employees"""
        self.stdout.write("Creating deductions...")

        deduction_types = [
            ("LT", "Lateness"),
            ("AB", "Absence"),
            ("DM", "Damages"),
            ("MISC", "Miscellaneous"),
        ]

        for employee in employees:
            for pay_period in pay_periods:
                # Randomly decide if this employee gets a deduction this period
                if random.random() < 0.2:  # 20% chance
                    deduction_type, description = random.choice(deduction_types)

                    # Generate deduction amount
                    deduction_amount = Decimal(str(random.uniform(1000, 10000)))

                    deduction = Deduction.objects.create(
                        employee=employee,
                        deduction_type=deduction_type,
                        amount=deduction_amount,
                        reason=f"Auto-generated {description.lower()} deduction",
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created {description} deduction of ₦{deduction_amount} for {employee.first_name}"
                        )
                    )

    def _create_iou_records(self, employees):
        """Create IOU records for employees"""
        self.stdout.write("Creating IOU records...")

        ious = []

        for employee in employees:
            # Randomly decide if this employee has an IOU
            if random.random() < 0.3:  # 30% chance
                amount = Decimal(str(random.uniform(10000, 100000)))
                tenor = random.randint(3, 12)  # 3 to 12 months
                interest_rate = Decimal(str(random.uniform(0, 10)))  # 0% to 10%

                iou = IOU.objects.create(
                    employee_id=employee,
                    amount=amount,
                    tenor=tenor,
                    interest_rate=interest_rate,
                    reason=f"Auto-generated IOU for {employee.first_name}",
                    status=random.choice(["PENDING", "APPROVED"]),
                    created_at=fake.date_between(start_date="-6y", end_date="today"),
                )

                if iou.status == "APPROVED":
                    iou.approved_at = fake.date_between(
                        start_date=iou.created_at, end_date="today"
                    )
                    iou.save()

                ious.append(iou)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created IOU of ₦{amount} for {employee.first_name} ({tenor} months)"
                    )
                )

        return ious

    def _create_iou_deductions(self, ious, pay_periods):
        """Create IOU deductions for approved IOUs"""
        self.stdout.write("Creating IOU deductions...")

        for iou in ious:
            if iou.status == "APPROVED":
                # Calculate monthly installment
                monthly_installment = iou.total_amount / iou.tenor

                # Create deductions for each pay period until IOU is paid off
                for i, pay_period in enumerate(pay_periods):
                    if i >= iou.tenor:
                        break

                    IOUDeduction.objects.get_or_create(
                        iou=iou,
                        employee=iou.employee_id,
                        payday=pay_period,
                        defaults={
                            "amount": monthly_installment,
                        },
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created IOU deduction of ₦{monthly_installment:.2f} for {iou.employee_id.first_name}"
                        )
                    )

    def _create_leave_policies(self):
        """Create leave policies"""
        self.stdout.write("Creating leave policies...")

        leave_policies = [
            ("CASUAL", 5),
            ("SICK", 10),
            ("ANNUAL", 21),
            ("MATERNITY", 90),
            ("PATERNITY", 10),
        ]

        companies = (
            EmployeeProfile.objects.exclude(company__isnull=True)
            .values_list("company_id", flat=True)
            .distinct()
        )

        for company_id in companies:
            for leave_type, max_days in leave_policies:
                policy, created = LeavePolicy.objects.get_or_create(
                    company_id=company_id,
                    leave_type=leave_type,
                    defaults={"max_days": max_days},
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created {leave_type} leave policy: {max_days} days (company={company_id})"
                        )
                    )

    def _create_leave_requests(self, employees):
        """Create leave requests for employees"""
        self.stdout.write("Creating leave requests...")

        leave_types = ["CASUAL", "SICK", "ANNUAL", "MATERNITY", "PATERNITY"]
        statuses = ["PENDING", "APPROVED", "REJECTED"]

        for employee in employees:
            # Randomly decide if this employee has leave requests
            if random.random() < 0.4:  # 40% chance
                num_requests = random.randint(1, 3)

                for _ in range(num_requests):
                    start_date = fake.date_between(start_date="-6y", end_date="+6y")
                    duration = random.randint(1, 14)  # 1 to 14 days
                    end_date = start_date + timedelta(days=duration)

                    leave_request = LeaveRequest.objects.create(
                        employee=employee,
                        leave_type=random.choice(leave_types),
                        start_date=start_date,
                        end_date=end_date,
                        reason=f"Auto-generated leave request for {employee.first_name}",
                        status=random.choice(statuses),
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created {leave_request.leave_type} leave request for {employee.first_name} "
                            f"({duration} days, {leave_request.status})"
                        )
                    )
