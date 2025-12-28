"""
Performance tests for large datasets.
Tests system performance with substantial amounts of data.
"""

import time
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test.utils import override_settings
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.utils import (
    get_trial_balance,
    get_account_balance,
    get_general_ledger,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
    LargeDatasetFactory,
)

User = get_user_model()


class LargeDatasetPerformanceTest(TestCase):
    """Performance tests with large datasets"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()

    def test_large_journal_creation_performance(self):
        """Test performance of creating many journals"""
        # Time journal creation
        start_time = time.time()
        reset_queries()

        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=100, entries_per_journal=4
        )

        end_time = time.time()
        creation_time = end_time - start_time

        # Check performance metrics
        self.assertEqual(len(journals), 100)
        self.assertLess(creation_time, 10.0)  # Should complete in under 10 seconds

        # Check query count
        self.assertLess(len(connection.queries), 500)  # Reasonable query count

    def test_large_chart_of_accounts_performance(self):
        """Test performance with large chart of accounts"""
        # Time account creation
        start_time = time.time()
        reset_queries()

        accounts = LargeDatasetFactory.create_large_account_chart(num_accounts=500)

        end_time = time.time()
        creation_time = end_time - start_time

        # Check performance metrics
        self.assertEqual(len(accounts), 500)
        self.assertLess(creation_time, 5.0)  # Should complete in under 5 seconds

        # Check query count
        self.assertLess(len(connection.queries), 50)  # Reasonable query count

    def test_trial_balance_performance_large_dataset(self):
        """Test trial balance performance with large dataset"""
        # Create large dataset
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=200, entries_per_journal=6
        )

        # Post all journals
        for journal in journals:
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Time trial balance generation
        start_time = time.time()
        reset_queries()

        trial_balance = get_trial_balance()

        end_time = time.time()
        query_time = end_time - start_time

        # Check performance metrics
        self.assertGreater(len(trial_balance), 0)
        self.assertLess(query_time, 5.0)  # Should complete in under 5 seconds

        # Check query count
        self.assertLess(len(connection.queries), 20)  # Should be efficient

    def test_account_balance_performance_large_dataset(self):
        """Test account balance calculation performance"""
        # Create large dataset
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=150, entries_per_journal=4
        )

        # Post all journals
        for journal in journals:
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Get an account with many entries
        account = Account.objects.first()

        # Time balance calculation
        start_time = time.time()
        reset_queries()

        balance = get_account_balance(account)

        end_time = time.time()
        query_time = end_time - start_time

        # Check performance metrics
        self.assertIsInstance(balance, Decimal)
        self.assertLess(query_time, 2.0)  # Should complete in under 2 seconds

        # Check query count
        self.assertLess(len(connection.queries), 5)  # Should be very efficient

    def test_general_ledger_performance_large_dataset(self):
        """Test general ledger performance with large dataset"""
        # Create large dataset
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=100, entries_per_journal=4
        )

        # Post all journals
        for journal in journals:
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Get an account with many entries
        account = Account.objects.first()

        # Time ledger generation
        start_time = time.time()
        reset_queries()

        ledger = get_general_ledger(account)

        end_time = time.time()
        query_time = end_time - start_time

        # Check performance metrics
        self.assertGreater(len(ledger), 0)
        self.assertLess(query_time, 3.0)  # Should complete in under 3 seconds

        # Check query count
        self.assertLess(len(connection.queries), 10)  # Should be efficient

    def test_audit_trail_query_performance(self):
        """Test audit trail query performance"""
        # Create many audit trail entries
        account = AccountFactory.create_account(
            "Performance Test", "9999", Account.AccountType.ASSET
        )

        # Create many journals to generate audit trail entries
        for i in range(50):
            journal = JournalFactory.create_journal(f"Test Journal {i}")
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Time audit trail query
        start_time = time.time()
        reset_queries()

        audit_trail = AccountingAuditTrail.objects.filter(
            content_type__model="journal"
        ).order_by("-timestamp")[:50]

        # Force evaluation
        list(audit_trail)

        end_time = time.time()
        query_time = end_time - start_time

        # Check performance metrics
        self.assertLess(query_time, 2.0)  # Should complete in under 2 seconds

        # Check query count
        self.assertLess(len(connection.queries), 5)  # Should be efficient

    def test_journal_reversal_performance_large_dataset(self):
        """Test journal reversal performance with large dataset"""
        # Create many posted journals
        journals = []
        for i in range(20):
            journal = JournalFactory.create_journal_with_entries(
                f"Reversal Test {i}", 1000
            )
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)
            journals.append(journal)

        # Time batch reversal
        start_time = time.time()
        reset_queries()

        from accounting.utils import reverse_batch_journals

        results = reverse_batch_journals(
            journals, self.user, "Performance test reversal"
        )

        end_time = time.time()
        reversal_time = end_time - start_time

        # Check performance metrics
        self.assertEqual(len(results["reversal_journals"]), 20)
        self.assertEqual(len(results["failed_journals"]), 0)
        self.assertLess(reversal_time, 10.0)  # Should complete in under 10 seconds

        # Check query count
        self.assertLess(len(connection.queries), 200)  # Reasonable for batch operation

    def test_multi_period_reporting_performance(self):
        """Test multi-period reporting performance"""
        # Create journals across multiple periods
        periods = list(self.fiscal_year.periods.all()[:6])  # 6 periods

        for period in periods:
            # Create journals in each period
            for i in range(10):
                journal = JournalFactory.create_journal_with_entries(
                    f"Period {period.period_number} Journal {i}", 1000
                )
                journal.period = period
                journal.save()
                journal.status = Journal.JournalStatus.APPROVED
                journal.save()
                journal.post(self.user)

        # Time multi-period trial balance
        start_time = time.time()
        reset_queries()

        trial_balance = get_trial_balance()  # All periods

        end_time = time.time()
        query_time = end_time - start_time

        # Check performance metrics
        self.assertGreater(len(trial_balance), 0)
        self.assertLess(query_time, 5.0)  # Should complete in under 5 seconds

        # Check query count
        self.assertLess(len(connection.queries), 25)  # Should be efficient


class MemoryUsageTest(TestCase):
    """Test memory usage with large datasets"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()

    def test_memory_usage_large_dataset(self):
        """Test memory usage with large dataset"""
        import gc
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create large dataset
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=100, entries_per_journal=4
        )

        # Post all journals
        for journal in journals:
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Generate reports
        trial_balance = get_trial_balance()

        for account in Account.objects.all()[:10]:  # Test first 10 accounts
            balance = get_account_balance(account)
            ledger = get_general_ledger(account)

        # Force garbage collection
        gc.collect()

        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Check memory usage is reasonable (less than 100MB increase)
        self.assertLess(
            memory_increase,
            100,
            f"Memory usage increased by {memory_increase:.2f}MB, which is too high",
        )

    def test_memory_usage_audit_trail(self):
        """Test memory usage with large audit trail"""
        import gc
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many audit trail entries
        for i in range(100):
            journal = JournalFactory.create_journal(f"Memory Test {i}")
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        # Query audit trail
        audit_trail = AccountingAuditTrail.objects.all().order_by("-timestamp")

        # Force evaluation
        list(audit_trail)

        # Force garbage collection
        gc.collect()

        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Check memory usage is reasonable (less than 50MB increase)
        self.assertLess(
            memory_increase,
            50,
            f"Memory usage increased by {memory_increase:.2f}MB, which is too high",
        )


class DatabaseQueryOptimizationTest(TestCase):
    """Test database query optimization"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()

    def test_select_related_optimization(self):
        """Test select_related optimization"""
        # Create journals with entries
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=50, entries_per_journal=4
        )

        # Test without select_related
        reset_queries()
        start_time = time.time()

        journals_without_optimization = Journal.objects.all()[:20]
        for journal in journals_without_optimization:
            # Access related objects
            _ = journal.period.fiscal_year.name
            _ = journal.created_by.username

        end_time = time.time()
        time_without_optimization = end_time - start_time
        queries_without = len(connection.queries)

        # Test with select_related
        reset_queries()
        start_time = time.time()

        journals_with_optimization = Journal.objects.select_related(
            "period__fiscal_year", "created_by"
        ).all()[:20]
        for journal in journals_with_optimization:
            # Access related objects
            _ = journal.period.fiscal_year.name
            _ = journal.created_by.username

        end_time = time.time()
        time_with_optimization = end_time - start_time
        queries_with = len(connection.queries)

        # Check optimization results
        self.assertLess(time_with_optimization, time_without_optimization)
        self.assertLess(queries_with, queries_without)
        self.assertLess(queries_with, 5)  # Should be very few queries

    def test_prefetch_related_optimization(self):
        """Test prefetch_related optimization"""
        # Create journals with many entries
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=30, entries_per_journal=6
        )

        # Test without prefetch_related
        reset_queries()
        start_time = time.time()

        journals_without_optimization = Journal.objects.all()[:10]
        for journal in journals_without_optimization:
            # Access related entries
            entries = journal.entries.all()
            for entry in entries:
                _ = entry.account.name

        end_time = time.time()
        time_without_optimization = end_time - start_time
        queries_without = len(connection.queries)

        # Test with prefetch_related
        reset_queries()
        start_time = time.time()

        journals_with_optimization = Journal.objects.prefetch_related(
            "entries__account"
        ).all()[:10]
        for journal in journals_with_optimization:
            # Access related entries
            entries = journal.entries.all()
            for entry in entries:
                _ = entry.account.name

        end_time = time.time()
        time_with_optimization = end_time - start_time
        queries_with = len(connection.queries)

        # Check optimization results
        self.assertLess(time_with_optimization, time_without_optimization)
        self.assertLess(queries_with, queries_without)
        self.assertLess(queries_with, 10)  # Should be much fewer queries

    def test_bulk_operations_performance(self):
        """Test bulk operations performance"""
        # Create many accounts
        accounts_data = []
        for i in range(100):
            accounts_data.append(
                Account(
                    name=f"Bulk Account {i}",
                    account_number=f"9{i:03d}",
                    type=Account.AccountType.ASSET,
                    description=f"Bulk created account {i}",
                )
            )

        # Time bulk create
        reset_queries()
        start_time = time.time()

        Account.objects.bulk_create(accounts_data)

        end_time = time.time()
        bulk_time = end_time - start_time
        bulk_queries = len(connection.queries)

        # Compare with individual creates
        Account.objects.all().delete()
        reset_queries()
        start_time = time.time()

        for account_data in accounts_data:
            account_data.save()

        end_time = time.time()
        individual_time = end_time - start_time
        individual_queries = len(connection.queries)

        # Check bulk operation is faster
        self.assertLess(bulk_time, individual_time)
        self.assertLess(bulk_queries, individual_queries)
        self.assertLess(bulk_queries, 5)  # Should be very few queries


class ConcurrentAccessTest(TestCase):
    """Test concurrent access performance"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()

    def test_concurrent_journal_creation(self):
        """Test concurrent journal creation performance"""
        import threading
        import queue

        results = queue.Queue()

        def create_journals(thread_id):
            """Create journals in a thread"""
            thread_journals = []
            for i in range(10):
                journal = JournalFactory.create_journal_with_entries(
                    f"Thread {thread_id} Journal {i}", 1000
                )
                thread_journals.append(journal)
            results.put(thread_journals)

        # Create multiple threads
        threads = []
        start_time = time.time()
        reset_queries()

        for i in range(5):  # 5 threads
            thread = threading.Thread(target=create_journals, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()
        concurrent_time = end_time - start_time

        # Collect results
        all_journals = []
        while not results.empty():
            all_journals.extend(results.get())

        # Check results
        self.assertEqual(len(all_journals), 50)  # 5 threads * 10 journals

        # Check performance (should be faster than sequential)
        self.assertLess(concurrent_time, 20.0)  # Should complete in under 20 seconds

        # Check database integrity
        for journal in all_journals:
            self.assertIsNotNone(journal.pk)
            self.assertEqual(journal.entries.count(), 2)

    def test_concurrent_reporting(self):
        """Test concurrent reporting performance"""
        import threading
        import queue

        # Create test data
        journals = LargeDatasetFactory.create_large_dataset(
            num_journals=50, entries_per_journal=4
        )
        for journal in journals:
            journal.status = Journal.JournalStatus.APPROVED
            journal.save()
            journal.post(self.user)

        results = queue.Queue()

        def generate_reports(thread_id):
            """Generate reports in a thread"""
            thread_results = []
            for i in range(5):
                trial_balance = get_trial_balance()
                thread_results.append(len(trial_balance))
            results.put(thread_results)

        # Create multiple threads
        threads = []
        start_time = time.time()
        reset_queries()

        for i in range(3):  # 3 threads
            thread = threading.Thread(target=generate_reports, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()
        concurrent_time = end_time - start_time

        # Collect results
        all_results = []
        while not results.empty():
            all_results.extend(results.get())

        # Check results
        self.assertEqual(len(all_results), 15)  # 3 threads * 5 reports

        # Check performance
        self.assertLess(concurrent_time, 15.0)  # Should complete in under 15 seconds

        # Check all reports are consistent
        first_result = all_results[0]
        for result in all_results:
            self.assertEqual(result, first_result)  # All should be same


class PerformanceBenchmarkTest(TestCase):
    """Performance benchmark tests"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()

    def test_performance_benchmarks(self):
        """Test performance against established benchmarks"""
        benchmarks = {
            "journal_creation": 0.1,  # 100ms per journal
            "trial_balance": 2.0,  # 2 seconds for trial balance
            "account_balance": 0.5,  # 500ms for account balance
            "general_ledger": 1.0,  # 1 second for general ledger
            "journal_reversal": 0.5,  # 500ms per journal reversal
        }

        # Test journal creation benchmark
        start_time = time.time()
        journal = JournalFactory.create_journal_with_entries("Benchmark Test", 1000)
        end_time = time.time()
        journal_creation_time = end_time - start_time

        self.assertLess(
            journal_creation_time,
            benchmarks["journal_creation"],
            f"Journal creation took {journal_creation_time:.3f}s, benchmark is {benchmarks['journal_creation']}s",
        )

        # Post journal for other tests
        journal.status = Journal.JournalStatus.APPROVED
        journal.save()
        journal.post(self.user)

        # Test trial balance benchmark
        start_time = time.time()
        trial_balance = get_trial_balance()
        end_time = time.time()
        trial_balance_time = end_time - start_time

        self.assertLess(
            trial_balance_time,
            benchmarks["trial_balance"],
            f"Trial balance took {trial_balance_time:.3f}s, benchmark is {benchmarks['trial_balance']}s",
        )

        # Test account balance benchmark
        account = journal.entries.first().account
        start_time = time.time()
        balance = get_account_balance(account)
        end_time = time.time()
        account_balance_time = end_time - start_time

        self.assertLess(
            account_balance_time,
            benchmarks["account_balance"],
            f"Account balance took {account_balance_time:.3f}s, benchmark is {benchmarks['account_balance']}s",
        )

        # Test general ledger benchmark
        start_time = time.time()
        ledger = get_general_ledger(account)
        end_time = time.time()
        general_ledger_time = end_time - start_time

        self.assertLess(
            general_ledger_time,
            benchmarks["general_ledger"],
            f"General ledger took {general_ledger_time:.3f}s, benchmark is {benchmarks['general_ledger']}s",
        )

        # Test journal reversal benchmark
        start_time = time.time()
        reversal_journal = journal.reverse(self.user, "Benchmark reversal")
        end_time = time.time()
        reversal_time = end_time - start_time

        self.assertLess(
            reversal_time,
            benchmarks["journal_reversal"],
            f"Journal reversal took {reversal_time:.3f}s, benchmark is {benchmarks['journal_reversal']}s",
        )
