# Notification System

The notification system uses server-rendered HTML plus small, delegated JavaScript
actions. Notification fragments must not ship their own inline click handlers or
embedded scripts because the header dropdown is loaded with `innerHTML`.

## Backend Contract

Notification pages and fragments are served by `payroll.views.notification_view`.

- `GET /notifications/` renders the full notification center.
- `GET /notifications/dropdown/` renders the header dropdown fragment.
- `GET /notifications/aggregated/` renders grouped notifications.
- `GET /notifications/digests/` renders digest settings and history.
- `GET /notifications/count/` returns `{ "unread_count": number }`.
- `POST /notifications/<uuid>/mark-read/` marks one notification as read.
- `POST /notifications/<uuid>/mark-unread/` marks one notification as unread.
- `POST /notifications/<uuid>/delete/` soft deletes one notification.
- `POST /notifications/mark-all-read/` marks all visible user notifications as read.
- `POST /notifications/delete-all-read/` soft deletes all read notifications.
- `POST /notifications/digest/trigger/` creates a manual digest and redirects for
  normal form posts, or returns JSON for AJAX posts.

All mutation endpoints return JSON and require CSRF protection. Each endpoint is
scoped to `request.user.employee_user`, so users cannot mutate another employee's
notifications.

`NotificationService.get_notifications()` supports these filters:

- `notification_type`: optional notification type.
- `priority`: optional priority.
- `read_status`: `all`, `read`, or `unread`.
- `limit` and `offset`: pagination controls.

The cache key includes the read status, notification type, priority, limit, and
offset. This prevents a cached `all` result from being reused for the `read` or
`unread` filters.

## Frontend Contract

Notification UI actions are declarative. Use `data-notification-action` and
`data-notification-url` on buttons or links:

```html
<button
  type="button"
  data-notification-action="mark-read"
  data-notification-url="/notifications/<uuid>/mark-read/">
  ...
</button>
```

Supported actions:

- `open`: POSTs the mark-read URL, then redirects to the link target.
- `mark-read`: POSTs the mark-read URL and refreshes the notification UI.
- `mark-unread`: POSTs the mark-unread URL and refreshes the notification UI.
- `delete`: POSTs the delete URL and refreshes the notification UI.
- `mark-all-read`: POSTs the bulk read URL and refreshes the notification UI.

Optional confirmations use `data-notification-confirm`.
Detail-page deletes may add `data-notification-redirect` so the browser leaves
the deleted detail page after a successful soft delete.

The shared JavaScript lives in `templates/base_new.html` and listens at the
document level, so it works for both the initial notification page and the
dynamically loaded dropdown. The dropdown template must stay script-free.

## Implementation Rules

- Use Django `{% url %}` tags for all notification action URLs.
- Do not hardcode `/payroll/notifications/...`; the app may be mounted at a
  different prefix in tests or deployment.
- Do not add inline `onclick`, `onchange`, or `onkeyup` handlers in notification
  templates.
- Keep dropdown fragments HTML-only. Any behavior belongs in the shared base
  script.
- Use normal POST forms for non-notification commands such as digest generation.
- Preserve soft-delete semantics by filtering on `is_deleted=False`.

## Verification

Run the focused notification regression tests:

```bash
venv/bin/python manage.py test payroll.tests_notification_mark_read --settings=core.settings_test
```

Run the Django system check:

```bash
venv/bin/python manage.py check --settings=core.settings_test
```
