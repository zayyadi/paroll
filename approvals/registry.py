"""Explicit domain adapters; registration does not grant execution authority."""
from dataclasses import dataclass
from typing import Callable
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class ApprovalAction:
    key: str
    model_label: str
    permission: str
    apply: Callable
    snapshot: Callable | None = None
    validate: Callable | None = None
    requester: Callable | None = None
    beneficiaries: Callable | None = None
    amount: Callable | None = None
    default_stages: list | None = None
    company: Callable | None = None
    reject: Callable | None = None
    cancel: Callable | None = None
    source_visibility: Callable | None = None


_actions: dict[str, ApprovalAction] = {}


def register_action(action: ApprovalAction) -> None:
    if action.key in _actions and _actions[action.key] != action:
        raise ValidationError(f"Approval action already registered: {action.key}")
    _actions[action.key] = action


def get_action(key: str) -> ApprovalAction:
    try:
        return _actions[key]
    except KeyError as exc:
        raise ValidationError("Unknown approval action.") from exc


def registered_actions() -> dict[str, ApprovalAction]:
    return dict(_actions)
