from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.utils import timezone

User = get_user_model()


@staff_member_required
def logged_in_users_view(request):
    # Get all active sessions
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    user_ids = []

    # Extract user IDs from sessions
    for session in sessions:
        data = session.get_decoded()
        user_ids.append(data.get("_auth_user_id", None))

    # Get user objects
    users = User.objects.filter(id__in=user_ids)

    return render(request, "admin/logged_in_users.html", {"users": users})
