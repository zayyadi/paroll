"""payroll 0095 / accounting 0022 move the disciplinary models without data loss."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

# projects builds on payroll 0095, so it is unapplied while rolled back.
BEFORE = [
    ("payroll", "0094_recompute_payroll_figures"),
    ("accounting", "0021_workflow_base_managers"),
    ("projects", None),
]
AFTER = [("payroll", "0095_move_discipline_models"), ("accounting", "0022_move_discipline_models")]


class DisciplineMoveMigrationTests(TransactionTestCase):
    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        # Every other app stays at its latest migration, so the historical
        # models match the database.
        moved = {app for app, _ in targets}
        targets = targets + [
            node for node in executor.loader.graph.leaf_nodes() if node[0] not in moved
        ]
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor.loader.project_state([t for t in targets if t[1]]).apps

    def tearDown(self):
        self._migrate(executor_leaf_nodes())

    def test_rows_permissions_and_policies_follow_the_models(self):
        old = self._migrate(BEFORE)
        ContentType = old.get_model("contenttypes", "ContentType")
        Permission = old.get_model("auth", "Permission")
        Group = old.get_model("auth", "Group")
        Company = old.get_model("company", "Company")
        User = old.get_model("users", "CustomUser")
        Case = old.get_model("accounting", "DisciplinaryCase")
        Policy = old.get_model("approvals", "ApprovalPolicy")

        company = Company.objects.create(name="Move Co")
        respondent = User.objects.create(email="respondent@move.test", company=company)
        case = Case.objects.create(
            company=company,
            respondent=respondent,
            allegation_summary="Lateness",
            allegation_details="Logged",
            case_number="DC-1",
        )
        case_ct, _ = ContentType.objects.get_or_create(app_label="accounting", model="disciplinarycase")
        permission, _ = Permission.objects.get_or_create(
            content_type=case_ct, codename="change_disciplinarycase", defaults={"name": "Can change"}
        )
        group = Group.objects.create(name="Move HR")
        group.permissions.add(permission)
        policy = Policy.objects.create(
            company=company,
            action="discipline.decide",
            stages=[{"permission": "accounting.change_disciplinarycase"}, {"permission": "accounting.change_journal"}],
        )

        new = self._migrate(AFTER)
        NewCase = new.get_model("payroll", "DisciplinaryCase")
        self.assertEqual(NewCase.objects.get(pk=case.pk).case_number, "DC-1")
        ContentType = new.get_model("contenttypes", "ContentType")
        moved = ContentType.objects.get(pk=case_ct.pk)
        self.assertEqual((moved.app_label, moved.model), ("payroll", "disciplinarycase"))
        Group = new.get_model("auth", "Group")
        self.assertTrue(
            Group.objects.get(pk=group.pk).permissions.filter(
                content_type__app_label="payroll", codename="change_disciplinarycase"
            ).exists()
        )
        Policy = new.get_model("approvals", "ApprovalPolicy")
        self.assertEqual(
            Policy.objects.get(pk=policy.pk).stages,
            [{"permission": "payroll.change_disciplinarycase"}, {"permission": "accounting.change_journal"}],
        )

        # And back again.
        old = self._migrate(BEFORE)
        ContentType = old.get_model("contenttypes", "ContentType")
        self.assertEqual(ContentType.objects.get(pk=case_ct.pk).app_label, "accounting")
        Policy = old.get_model("approvals", "ApprovalPolicy")
        self.assertEqual(Policy.objects.get(pk=policy.pk).stages[0]["permission"], "accounting.change_disciplinarycase")


def executor_leaf_nodes():
    executor = MigrationExecutor(connection)
    return executor.loader.graph.leaf_nodes()
