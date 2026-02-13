--- /dev/null
+++ b/opt/usr/devs/payroll/paroll/README.md
@@ -0,0 +1,209 @@
+# Django Payroll System
+
+## Description
+
+This project is a comprehensive Payroll Management System built with Django. It aims to provide functionalities for managing employees, processing payroll, handling leave requests, IOU (I Owe You) applications, performance reviews, and maintaining an audit trail of actions within the system. The system is designed with role-based access control to ensure data security and appropriate access levels for different user types (e.g., HR, regular employees, superusers).
+
+## Features
+
+*   **Employee Management:**
+    *   Add, update, view, and delete employee profiles.
+    *   Soft delete functionality for employee records.
+    *   Employee search and filtering by department.
+    *   Manage employee departments.
+    *   Store detailed employee information including personal details, job information, bank details, emergency contacts, and next of kin.
+*   **Payroll Processing:**
+    *   Define and manage payroll components (basic salary, allowances, deductions).
+    *   Calculate gross income, taxable income, and net pay.
+    *   Manage pay periods (PayrollRun).
+    *   Generate payslips for employees.
+    *   Generate various payroll reports (Bank reports, NHIS, NHF, PAYE, Pension).
+*   **Leave Management:**
+    *   Employees can apply for leave.
+    *   HR can manage (approve/reject) leave requests.
+    *   Define and view leave policies.
+    *   Employees can view their leave request history.
+*   **IOU (I Owe You) Management:**
+    *   Employees can request IOUs.
+    *   HR can manage (approve/reject) IOU applications.
+    *   Track IOU status (Pending, Approved, Rejected, Paid).
+    *   Employees can view their IOU history.
+*   **Performance Reviews:**
+    *   Add, update, view, and delete employee performance reviews.
+    *   Track review date, rating, and comments.
+*   **Dashboards:**
+    *   Admin dashboard for superusers.
+    *   HR dashboard with key metrics (total employees, pending approvals) and quick links to approval sections.
+    *   User-specific dashboard.
+*   **Security & Access Control:**
+    *   Login required for most views.
+    *   Permission-based access control for different functionalities (e.g., HR can manage employees, employees can view their own profiles).
+*   **Audit Trail:**
+    *   Log important actions performed by users (e.g., creating, updating, deleting records).
+    *   View and filter audit logs.
+*   **User Management:**
+    *   Integration with Django's `CustomUser` model.
+    *   Automatic creation of `EmployeeProfile` upon `CustomUser` creation.
+*   **Notification System V2:**
+    *   Enterprise-grade notification system with priority-based delivery
+    *   Multi-channel support (in-app, email, push, SMS)
+    *   User preferences for granular control
+    *   Asynchronous processing using Celery
+    *   Real-time updates via Django Channels
+    *   Intelligent aggregation to reduce notification fatigue
+    *   Performance optimization through Redis caching
+    *   Automated archiving for data retention
+    *   Comprehensive delivery tracking and monitoring
+    *   See [`NOTIFICATION_SYSTEM_V2_IMPLEMENTATION.md`](NOTIFICATION_SYSTEM_V2_IMPLEMENTATION.md) for complete documentation
+
+## Prerequisites
+
+*   Python (version 3.8+ recommended)
+*   Django (version 3.2+ or 4.x recommended - check `requirements.txt`)
+*   PostgreSQL or other relational database (configured in `settings.py`)
+*   Other dependencies as listed in `requirements.txt` (e.g., `django-autoslug`, `Pillow`, `django-monthyear-widget`)
+
+## Installation
+
+1.  **Clone the repository:**
+    ```bash
+    git clone <repository-url>
+    cd paroll # Or your project's root directory
+    ```
+
+2.  **Create and activate a virtual environment:**
+    ```bash
+    python -m venv venv
+    source venv/bin/activate  # On Windows: venv\Scripts\activate
+    ```
+
+3.  **Install dependencies:**
+    ```bash
+    pip install -r requirements.txt
+    ```
+    *(Note: A `requirements.txt` file would typically list all project dependencies. If not present, you'll need to install Django and other used packages manually or generate it.)*
+
+4.  **Configure your database:**
+    *   Update `core/settings.py` (or your project's settings file) with your database credentials.
+
+5.  **Apply migrations:**
+    ```bash
+    python manage.py makemigrations
+    python manage.py migrate
+    ```
+
+6.  **Create a superuser (admin):**
+    ```bash
+    python manage.py createsuperuser
+    ```
+
+7.  **Collect static files (for production):**
+    ```bash
+    python manage.py collectstatic
+    ```
+
+## Running the Application
+
+1.  **Start the development server:**
+    ```bash
+    python manage.py runserver
+    ```
+2.  Open your web browser and navigate to `http://127.0.0.1:8000/`.
+    *   Admin interface: `http://127.0.0.1:8000/admin/`
+
+## Key Application URLs (Namespace: `payroll`)
+
+*   `/` (`payroll:index`): Main index page.
+*   `/hr-dashboard/` (`payroll:hr_dashboard`): Dashboard for HR personnel.
+*   `/employees/` (`payroll:employee_list`): List of all employees.
+*   `/add_employee` (`payroll:add_employee`): Add a new employee.
+*   `/profile/<int:user_id>/` (`payroll:profile`): View employee profile.
+*   `/dashboard` (`payroll:dashboard`): General dashboard (redirects based on user type).
+*   `/list_payslip/<slug:emp_slug>/` (`payroll:list-payslip`): List payslips for an employee.
+*   `/payslip/<int:id>/` (`payroll:payslip`): View a specific payslip.
+*   `/pay-period/` (`payroll:pay_period_list`): List of pay periods.
+*   `/pay-period/create/` (`payroll:payday`): Create a new pay period.
+*   `/apply-leave/` (`payroll:apply_leave`): Apply for leave.
+*   `/leave-requests/` (`payroll:leave_requests`): View own leave requests.
+*   `/manage-leave-requests/` (`payroll:manage_leave_requests`): HR view to manage pending leave requests.
+*   `/request-iou/` (`payroll:request_iou`): Request an IOU.
+*   `/iou-history/` (`payroll:iou_history`): View own IOU history.
+*   `/iou/` (`payroll:iou_list`): HR view to list all IOUs.
+*   `/approve-iou/<int:iou_id>/` (`payroll:approve_iou`): Approve an IOU.
+*   `/performance-reviews/` (`payroll:performance_reviews`): List performance reviews (general).
+*   `/reviews/` (`payroll:performance_review_list`): List performance reviews (HR view).
+*   `/reviews/add/` (`payroll:add_performance_review`): Add a performance review.
+*   `/audit-trail/` (`payroll:audit_trail_list`): View audit trail logs.
+
+*(This is not an exhaustive list. Refer to `payroll/urls.py` for all defined paths.)*
+
+## Permissions and Roles
+
+The application uses Django's built-in permission system. Key roles and their typical permissions include:
+
+*   **Superuser:** Full access to all system functionalities, including the Django admin interface.
+*   **HR Personnel:**
+    *   View and manage employee profiles (`payroll.view_employeeprofile`, `payroll.add_employeeprofile`, `payroll.change_employeeprofile`, `payroll.delete_employeeprofile`).
+    *   Manage leave requests (`payroll.change_leaverequest`).
+    *   Manage IOU applications (`payroll.change_iou`).
+    *   Manage performance reviews (`payroll.view_performancereview`, `payroll.add_performancereview`, etc.).
+    *   Access to HR dashboard and various reports.
+*   **Regular Employee:**
+    *   View their own profile.
+    *   Apply for leave (`payroll.add_leaverequest`).
+    *   View their leave request history.
+    *   Request IOUs (`payroll.add_iou`).
+    *   View their IOU history.
+    *   View their own payslips.
+
+Permissions are enforced using `@permission_required` decorators for function-based views and `PermissionRequiredMixin` for class-based views.
+
+## Models Overview
+
+Key models in the `payroll` app include:
+
+*   `EmployeeProfile`: Stores detailed information about each employee, linked to a `CustomUser`.
+*   `Department`: Represents organizational departments.
+*   `Payroll`: Defines the salary structure and calculated payroll components for an employee.
+*   `Allowance`, `Deduction`: Define types of allowances and deductions.
+*   `PayrollRun` (Pay Period): Represents a specific payroll period (e.g., a month).
+*   `PayrollRunEntry`: Links employees' payroll entries to a specific payroll run.
+*   `LeavePolicy`: Defines types of leave and their maximum allowed days.
+*   `LeaveRequest`: Tracks leave applications from employees.
+*   `IOU`: Manages IOU requests, approvals, and details.
+*   `PerformanceReview`: Stores records of employee performance reviews.
+*   `AuditTrail`: Logs significant actions within the system.
+*   `SoftDeleteModel`: A base model providing soft delete functionality (records are marked as deleted instead of being physically removed from the database).
+
+*(Refer to `payroll/models/` directory for detailed model definitions.)*
+
+## Future Enhancements (Potential)
+
+*   More detailed reporting and analytics.
+*   Integration with external accounting systems.
+*   Automated email notifications for approvals, rejections, etc.
+*   Self-service password reset for users.
+*   Advanced search capabilities.
+*   Bulk import/export of employee data.
+
+## Contributing
+
+Contributions are welcome! Please follow these steps:
+
+1.  Fork the repository.
+2.  Create a new branch (`git checkout -b feature/your-feature-name`).
+3.  Make your changes.
+4.  Commit your changes (`git commit -m 'Add some feature'`).
+5.  Push to the branch (`git push origin feature/your-feature-name`).
+6.  Open a Pull Request.
+
+Please ensure your code adheres to the project's coding standards and includes tests where appropriate.
+
+## License
+
+This project is licensed under the MIT License - see the LICENSE.txt file for details (or choose an appropriate license).
+
+---
+
+*This README was generated based on the project structure and may require further customization and detail.*
+
+```

This README provides a solid foundation. You should:

1.  **Review and Customize:** Read through it carefully and adjust any details that might be specific to your project's current state or future plans.
2.  **Add `requirements.txt`:** If you don't have one, generate it using `pip freeze > requirements.txt` in your activated virtual environment.
3.  **Add a `LICENSE.txt` file:** If you choose the MIT license (or another), create the corresponding license file in your project root.
4.  **Verify URLs and Features:** Double-check the "Key Application URLs" and "Features" sections against your actual implementation.
5.  **Elaborate on Setup:** If there are any specific environment variables or configurations needed (e.g., email backend settings for notifications), add a section for them.
