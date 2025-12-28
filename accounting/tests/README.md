# Accounting System Test Suite

This directory contains a comprehensive test suite for the accounting and auditing system. The test suite validates all aspects of the accounting system, ensuring data integrity, proper audit trails, and correct functioning of all features.

## Test Structure

The test suite is organized into the following files:

### Core Test Files

1. **fixtures.py** - Test data factories for creating sample data
   - User factory methods for different roles (auditor, accountant, payroll processor)
   - Chart of accounts creation with all account types
   - Fiscal year and period creation
   - Journal and entry creation with balanced entries
   - Large dataset factory for performance testing

2. **test_models.py** - Model tests for all accounting models
   - Account model tests (creation, string representation, balance calculation)
   - FiscalYear model tests (creation, validation, closure)
   - AccountingPeriod model tests (creation, validation, closure)
   - Journal model tests (creation, transaction numbers, validation, approval, posting, reversal)
   - JournalEntry model tests (creation, string representation, validation)
   - TransactionNumber model tests (number generation)
   - AccountingAuditTrail model tests (logging, ordering)

3. **test_utils.py** - Utility function tests
   - Transaction number utilities
   - Fiscal year and period utilities
   - Validation utilities for journal entries and periods
   - Journal creation and posting utilities
   - Journal reversal utilities (full, partial, with correction, batch)
   - Reporting utilities (trial balance, account balances)
   - Period closing utilities
   - Audit logging utilities

4. **test_views.py** - View tests for all accounting views
   - Dashboard view tests
   - Account view tests (list, detail, create)
   - Journal view tests (list, detail, create, approval)
   - Fiscal year view tests (list, detail)
   - Accounting period view tests (list, detail, close)
   - Audit trail view tests (list, detail)
   - Report view tests (trial balance, account activity)
   - PDF export view tests
   - Journal reversal view tests

5. **test_permissions.py** - Permission and access control tests
   - Role permission functions (is_auditor, is_accountant, is_payroll_processor)
   - Journal permission functions (can_approve_journal, can_reverse_journal)
   - Period permission functions (can_close_period)
   - Payroll permission functions (can_view_payroll_data, can_modify_payroll_data)
   - Permission decorator tests (auditor_required, accountant_required)
   - Permission mixin tests (AuditorRequiredMixin, AccountantRequiredMixin)
   - Integration tests for permissions with views

6. **test_signal_handlers.py** - Signal handler tests
   - Account signal handlers (create, update, delete)
   - Fiscal year signal handlers (create, update, delete, close)
   - Accounting period signal handlers (create, update, delete, close)
   - Journal signal handlers (create, update, delete, status changes)
   - Journal entry signal handlers (create, update, delete)
   - Custom logging functions (approval, posting, reversal, batch operations)

7. **test_integration.py** - Integration tests for complete workflows
   - Payroll transaction integration with accounting entries
   - Complete journal lifecycle (creation to reversal)
   - Period and fiscal year management workflows
   - Audit trail verification throughout workflows
   - Reporting functionality integration
   - Permission integration across workflows

8. **test_performance.py** - Performance tests with large datasets
   - Large dataset handling (100+ journals, 500+ accounts)
   - Report generation performance (trial balance, account activity)
   - Audit trail query performance
   - Database query optimization tests
   - Memory usage tests
   - Multi-period performance tests

9. **end_to_end_test.py** - End-to-end test script
   - Complete accounting system setup
   - Payroll transaction creation and verification
   - Double-entry bookkeeping validation
   - Audit trail functionality testing
   - Reporting capabilities testing
   - Transaction reversal mechanisms testing
   - Data integrity validation
   - Role-based permissions testing

## Running Tests

### Running All Tests

To run all accounting tests:

```bash
python manage.py test accounting.tests
```

### Running Specific Test Files

To run a specific test file:

```bash
# Model tests
python manage.py test accounting.tests.test_models

# Utility tests
python manage.py test accounting.tests.test_utils

# View tests
python manage.py test accounting.tests.test_views

# Permission tests
python manage.py test accounting.tests.test_permissions

# Signal handler tests
python manage.py test accounting.tests.test_signal_handlers

# Integration tests
python manage.py test accounting.tests.test_integration

# Performance tests
python manage.py test accounting.tests.test_performance
```

### Running End-to-End Tests

The end-to-end test script can be run directly:

```bash
python accounting/tests/end_to_end_test.py
```

### Running Specific Test Classes

To run a specific test class:

```bash
python manage.py test accounting.tests.test_models.AccountModelTest
python manage.py test accounting.tests.test_views.JournalViewTest
```

### Running Specific Test Methods

To run a specific test method:

```bash
python manage.py test accounting.tests.test_models.AccountModelTest.test_account_creation
python manage.py test accounting.tests.test_views.JournalViewTest.test_journal_list_view
```

## Test Coverage

The test suite provides comprehensive coverage of:

### Model Coverage
- All accounting models and their methods
- Model validation and constraints
- Model relationships and foreign keys
- Model string representations and properties

### Utility Function Coverage
- All utility functions in accounting/utils.py
- Transaction number generation
- Journal creation and posting
- Journal reversal mechanisms
- Report generation functions
- Period and fiscal year management

### View Coverage
- All accounting views and their responses
- Template rendering and context
- Form handling and validation
- Permission-based access control
- PDF generation and export

### Permission Coverage
- All permission functions and decorators
- Role-based access control
- Object-level permissions
- View-level permission enforcement

### Signal Handler Coverage
- All signal handlers and their triggers
- Audit trail logging functionality
- Model change tracking
- Custom logging functions

### Integration Coverage
- End-to-end workflows
- Cross-component integration
- Payroll and accounting integration
- Complete journal lifecycle
- Period and fiscal year workflows

### Performance Coverage
- Large dataset handling
- Report generation performance
- Database query optimization
- Memory usage efficiency
- Multi-period operations

## Test Data

The test suite uses factory methods in `fixtures.py` to create consistent test data:

- **Users**: Creates users with different roles (admin, accountant, auditor, payroll processor, regular user)
- **Accounts**: Creates a comprehensive chart of accounts with all account types
- **Fiscal Years and Periods**: Creates fiscal years with monthly accounting periods
- **Journals and Entries**: Creates balanced journal entries with proper debit/credit pairs
- **Payroll Data**: Creates employee profiles and payroll transactions (if payroll models are available)

## Performance Benchmarks

The performance tests include the following benchmarks:

- **Journal Creation**: Creating 100 journals should take less than 30 seconds
- **Trial Balance Generation**: Generating trial balance for 200 journals should take less than 5 seconds
- **Account Activity Report**: Generating account activity for 150 entries should take less than 3 seconds
- **Audit Trail Queries**: Querying audit trail should take less than 2 seconds
- **Large Account Chart**: Creating 500 accounts should take less than 10 seconds

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all required models and utilities are properly imported
2. **Database Issues**: Run migrations before running tests
3. **Permission Issues**: Ensure test users have proper roles assigned
4. **Performance Test Failures**: Performance benchmarks may need adjustment based on system capabilities

### Debugging Tests

To debug failing tests:

1. Run with verbose output:
   ```bash
   python manage.py test accounting.tests --verbosity=2
   ```

2. Run with debugging:
   ```bash
   python manage.py test accounting.tests --debug-mode
   ```

3. Stop on first failure:
   ```bash
   python manage.py test accounting.tests --failfast
   ```

### Test Database

The tests use a separate test database that is created and destroyed during testing. To keep the test database:

```bash
python manage.py test accounting.tests --keepdb
```

## Contributing

When adding new tests:

1. Follow the existing naming conventions
2. Use the factory methods in `fixtures.py` for test data
3. Include both positive and negative test cases
4. Add performance tests for new functionality
5. Include integration tests for new features
6. Update this README with new test descriptions

## Best Practices

1. **Test Isolation**: Each test should be independent and not rely on other tests
2. **Test Data**: Use factory methods for consistent test data
3. **Assertions**: Use specific assertions with clear error messages
4. **Mocking**: Use mocking for external dependencies and request context
5. **Cleanup**: Ensure tests clean up any created data
6. **Performance**: Include performance tests for critical operations
7. **Coverage**: Aim for high test coverage for new functionality

## Test Categories

### Unit Tests
- Individual model methods
- Utility functions
- Permission functions
- Signal handlers

### Integration Tests
- Component interactions
- Workflow processes
- Cross-module functionality

### Performance Tests
- Large dataset handling
- Query optimization
- Memory usage
- Response times

### End-to-End Tests
- Complete user workflows
- System-wide functionality
- Data integrity validation
- Business process verification