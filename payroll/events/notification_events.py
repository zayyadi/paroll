"""
Event classes for the notification system.
These events are dispatched by the EventDispatcher and handled by notification handlers.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict
from enum import Enum


class EventType(Enum):
    """Enumeration of event types"""

    LEAVE_REQUEST_CREATED = "leave.request.created"
    LEAVE_REQUEST_APPROVED = "leave.request.approved"
    LEAVE_REQUEST_REJECTED = "leave.request.rejected"
    IOU_CREATED = "iou.created"
    IOU_APPROVED = "iou.approved"
    IOU_REJECTED = "iou.rejected"
    PAYROLL_CREATED = "payroll.created"
    PAYROLL_PROCESSED = "payroll.processed"
    APPRAISAL_ASSIGNED = "appraisal.assigned"


@dataclass
class BaseEvent:
    """
    Base event class for all notification events.

    Attributes:
        event_type: The type of event from EventType enum
        timestamp: When the event occurred
        metadata: Additional event-specific data
    """

    event_type: Optional[EventType] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Set timestamp if not provided"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class LeaveRequestEvent(BaseEvent):
    """
    Event for leave request operations.

    Attributes:
        leave_request: The LeaveRequest instance
        event_type: Specific leave event type
        actor: User who triggered the event (optional)
    """

    leave_request: Optional[Any] = None
    event_type: Optional[EventType] = None
    actor: Optional[Any] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize metadata and timestamp"""
        if self.metadata is None:
            self.metadata = {}

        # Add leave request details to metadata
        self.metadata.update(
            {
                "leave_request_id": (
                    str(self.leave_request.id)
                    if hasattr(self.leave_request, "id")
                    else None
                ),
                "employee_id": (
                    str(self.leave_request.employee.id)
                    if hasattr(self.leave_request, "employee")
                    else None
                ),
                "leave_type": getattr(self.leave_request, "leave_type", None),
                "start_date": str(getattr(self.leave_request, "start_date", None)),
                "end_date": str(getattr(self.leave_request, "end_date", None)),
                "status": getattr(self.leave_request, "status", None),
                "actor_id": (
                    str(self.actor.id)
                    if self.actor and hasattr(self.actor, "id")
                    else None
                ),
            }
        )

        super().__post_init__()


@dataclass
class IOUEvent(BaseEvent):
    """
    Event for IOU (I Owe You) operations.

    Attributes:
        iou: The IOU instance
        event_type: Specific IOU event type
        actor: User who triggered the event (optional)
    """

    iou: Optional[Any] = None
    event_type: Optional[EventType] = None
    actor: Optional[Any] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize metadata and timestamp"""
        if self.metadata is None:
            self.metadata = {}

        # Add IOU details to metadata
        self.metadata.update(
            {
                "iou_id": str(self.iou.id) if hasattr(self.iou, "id") else None,
                "employee_id": (
                    str(self.iou.employee_id.id)
                    if hasattr(self.iou, "employee_id")
                    else None
                ),
                "amount": float(getattr(self.iou, "amount", 0)),
                "tenor": getattr(self.iou, "tenor", None),
                "status": getattr(self.iou, "status", None),
                "actor_id": (
                    str(self.actor.id)
                    if self.actor and hasattr(self.actor, "id")
                    else None
                ),
            }
        )

        super().__post_init__()


@dataclass
class PayrollEvent(BaseEvent):
    """
    Event for payroll operations.

    Attributes:
        payroll: The PayT instance
        event_type: Specific payroll event type
        payday_records: Related Payday records (optional)
    """

    payroll: Optional[Any] = None
    event_type: Optional[EventType] = None
    payday_records: Optional[Any] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize metadata and timestamp"""
        if self.metadata is None:
            self.metadata = {}

        # Add payroll details to metadata
        self.metadata.update(
            {
                "payroll_id": (
                    str(self.payroll.id) if hasattr(self.payroll, "id") else None
                ),
                "pay_period": getattr(self.payroll, "paydays", None),
                "is_active": getattr(self.payroll, "is_active", False),
                "payday_count": len(self.payday_records) if self.payday_records else 0,
            }
        )

        super().__post_init__()


@dataclass
class AppraisalEvent(BaseEvent):
    """
    Event for appraisal operations.

    Attributes:
        appraisal_assignment: The AppraisalAssignment instance
        event_type: Specific appraisal event type
    """

    appraisal_assignment: Optional[Any] = None
    event_type: Optional[EventType] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize metadata and timestamp"""
        if self.metadata is None:
            self.metadata = {}

        # Add appraisal details to metadata
        self.metadata.update(
            {
                "assignment_id": (
                    str(self.appraisal_assignment.id)
                    if hasattr(self.appraisal_assignment, "id")
                    else None
                ),
                "appraisee_id": (
                    str(self.appraisal_assignment.appraisee.id)
                    if hasattr(self.appraisal_assignment, "appraisee")
                    else None
                ),
                "appraiser_id": (
                    str(self.appraisal_assignment.appraiser.id)
                    if hasattr(self.appraisal_assignment, "appraiser")
                    else None
                ),
                "appraisal_id": (
                    str(self.appraisal_assignment.appraisal.id)
                    if hasattr(self.appraisal_assignment, "appraisal")
                    else None
                ),
                "appraisal_name": (
                    getattr(self.appraisal_assignment.appraisal, "name", None)
                    if hasattr(self.appraisal_assignment, "appraisal")
                    else None
                ),
            }
        )

        super().__post_init__()
