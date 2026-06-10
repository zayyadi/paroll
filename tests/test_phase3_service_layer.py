import ast
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings


class Phase3ServiceLayerTests(SimpleTestCase):
    def test_notification_signals_delegate_to_service_layer(self):
        from payroll import notification_signals

        iou = Mock(status="APPROVED")
        with override_settings(NOTIFICATION_SIGNALS_ENABLED=True), patch(
            "payroll.notification_signals.NotificationSignalService"
        ) as service_class:
            notification_signals.handle_iou_signal(
                sender=object,
                instance=iou,
                created=False,
            )

        service_class.return_value.handle_iou_saved.assert_called_once_with(
            iou,
            created=False,
        )

    def test_legacy_notification_dispatch_helpers_delegate_to_service_layer(self):
        from payroll import notification_signals

        iou = Mock(status="REJECTED")
        with patch(
            "payroll.notification_signals.NotificationSignalService"
        ) as service_class:
            notification_signals._dispatch_iou_rejected_event(iou)

        service_class.return_value.dispatch_iou_rejected.assert_called_once_with(iou)

    def test_all_service_functions_have_type_annotations(self):
        service_dir = Path("payroll/services")
        missing = []
        for path in sorted(service_dir.glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                missing_args = [
                    arg.arg
                    for arg in args
                    if arg.arg != "self" and arg.annotation is None
                ]
                if missing_args or node.returns is None:
                    missing.append(
                        f"{path}:{node.lineno}:{node.name}"
                        f" args={missing_args} return={node.returns is not None}"
                    )

        self.assertEqual(missing, [])
