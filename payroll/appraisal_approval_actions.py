"""Independent publication of reviewer-authored employee assessments."""
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import F
from approvals.registry import ApprovalAction, register_action


def review_snapshot(review):
    return {
        "appraisal": review.appraisal_id,
        "appraisal_name": review.appraisal.name,
        "company": review.company_id,
        "employee": review.employee_id,
        "employee_name": str(review.employee),
        "reviewer": review.reviewer_id,
        "reviewer_name": str(review.reviewer),
        "assessment": review.self_assessment,
        "status": review.status,
        "ratings": list(review.rating_set.order_by("metric_id").values("metric_id", "rating", "comments", metric_name=F("metric__name"), metric_description=F("metric__description"))),
    }


def validate_publication(review, payload):
    if review.status != "SUBMITTED":
        raise ValidationError("Only submitted reviews can be published.")
    review.full_clean()
    if not review.rating_set.exists():
        raise ValidationError("A review must contain ratings before publication.")


def publish_review(review, actor, payload):
    validate_publication(review, payload)
    review.status = "PUBLISHED"
    review.published_at = timezone.now()
    review.published_by = actor
    review.save(update_fields=["status", "published_at", "published_by"])


def return_to_draft(review, actor, payload):
    review.status = "DRAFT"
    review.save(update_fields=["status"])


register_action(ApprovalAction(
    key="appraisal.publish", model_label="payroll.Review", permission="payroll.publish_review",
    apply=publish_review, snapshot=review_snapshot, validate=validate_publication,
    requester=lambda review: review.reviewer.user,
    beneficiaries=lambda review: [review.employee.user_id],
    reject=return_to_draft,
    cancel=return_to_draft,
    source_visibility=lambda review, user: review.status == "PUBLISHED" or review.employee.user_id != user.pk,
))
