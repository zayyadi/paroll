# Mobile Integration Guide

This guide explains how a mobile application should integrate with the Payroll
SaaS Platform API. It covers startup, authentication, tenant context, endpoint
usage, permissions, pagination, errors, notifications, realtime features, and
deployment settings.

## Integration Goals

The mobile app should be a first-class client of the existing tenant-scoped API.
It should not scrape web pages or depend on Django sessions. Mobile clients
should use JSON APIs, token authentication when available, and the authenticated
context endpoint to decide what data and screens to show.

## Backend Additions For Mobile

The backend exposes two mobile-friendly discovery surfaces:

- `GET /api/v1/mobile/config/` is public and tells the app which API version,
  auth URLs, feature flags, support links, and pagination settings are active.
- `GET /api/v1/auth/context/` is authenticated and returns the current user,
  active company, memberships, linked employee profile, permission codes,
  enabled features, and recommended navigation entries.

These endpoints let the mobile app start safely across environments where JWT,
accounting, inventory, payroll, notifications, or other modules may be enabled
or disabled independently.

## Base API

API base path:

```text
/api/v1/
```

API documentation:

```text
GET /api/v1/schema/
GET /api/v1/docs/swagger/
GET /api/v1/docs/redoc/
```

Mobile bootstrap endpoint:

```text
GET /api/v1/mobile/config/
```

Authenticated user context:

```text
GET /api/v1/auth/context/
```

## Recommended App Startup Flow

1. Fetch public mobile config:

   ```text
   GET /api/v1/mobile/config/
   ```

2. Check API/app compatibility:

   - Read `app.min_supported_version`.
   - Read `app.current_version`.
   - If the installed app is older than `min_supported_version`, force an app
     update screen.

3. Check auth availability:

   - If `auth.grant_types` contains `token`, use JWT login.
   - If token URLs are `null`, the deployed backend does not expose JWT routes
     and the mobile app should not attempt token login.

4. If no token is stored, show login.

5. If an access token is stored, call:

   ```text
   GET /api/v1/auth/context/
   Authorization: Bearer <access_token>
   ```

6. Use the context response to build the app shell:

   - `user`
   - `active_company`
   - `memberships`
   - `employee_profile`
   - `permissions`
   - `features`
   - `navigation`

7. Load data for the active tab using the tenant-scoped API endpoints.

## Mobile Config Contract

Endpoint:

```text
GET /api/v1/mobile/config/
```

Authentication:

- Public.
- No token required.

Purpose:

- Allows the app to bootstrap without knowing every backend capability in
  advance.
- Gives mobile clients stable URLs for docs, auth, and compatibility checks.
- Exposes feature flags for screen availability.

Response shape:

```json
{
  "api": {
    "version": "v1",
    "schema_url": "https://example.com/api/v1/schema/",
    "swagger_url": "https://example.com/api/v1/docs/swagger/",
    "redoc_url": "https://example.com/api/v1/docs/redoc/"
  },
  "auth": {
    "grant_types": ["token", "refresh"],
    "token_url": "https://example.com/api/v1/auth/token/",
    "refresh_url": "https://example.com/api/v1/auth/token/refresh/",
    "context_url": "https://example.com/api/v1/auth/context/"
  },
  "app": {
    "min_supported_version": "1.0.0",
    "current_version": "1.0.0"
  },
  "features": {
    "employees": "Employee directory, profile, and self-service context.",
    "payroll": "Payroll records, payroll runs, payslips, leave, and IOUs.",
    "accounting": "Accounts, fiscal years, periods, journals, and reports.",
    "inventory": "Items, warehouses, suppliers, customers, purchase orders, and stock movements.",
    "standups": "Team standups, questions, check-ins, blockers, and follows.",
    "chat": "Company chat rooms, direct rooms, messages, and read state.",
    "notifications": "Notification inbox, preferences, and delivery state."
  },
  "links": {
    "support": "/support/",
    "privacy": "/legal/privacy/",
    "terms": "/legal/terms/",
    "support_email": ""
  },
  "pagination": {
    "style": "page-number",
    "default_page_size": 25,
    "page_query_param": "page"
  }
}
```

## Authentication

The project supports JWT when `djangorestframework-simplejwt` is installed.

Token login:

```text
POST /api/v1/auth/token/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

Typical response:

```json
{
  "refresh": "<refresh_token>",
  "access": "<access_token>"
}
```

Token refresh:

```text
POST /api/v1/auth/token/refresh/
Content-Type: application/json

{
  "refresh": "<refresh_token>"
}
```

Authenticated requests:

```text
Authorization: Bearer <access_token>
```

Recommended token storage:

- iOS: Keychain.
- Android: EncryptedSharedPreferences or Android Keystore-backed storage.
- React Native: secure storage library backed by Keychain/Keystore.
- Flutter: `flutter_secure_storage` or platform-secure equivalent.

Recommended token lifecycle:

1. Store access and refresh token after login.
2. Attach access token to every API request.
3. On `401`, try one refresh.
4. Retry the failed request once with the new access token.
5. If refresh fails, clear tokens and show login.

Security rules:

- Do not store tokens in plain AsyncStorage, SharedPreferences, localStorage, or
  SQLite.
- Do not log tokens.
- Do not send password to any endpoint except the token endpoint.
- Use HTTPS in every non-local environment.

## Auth Context Contract

Endpoint:

```text
GET /api/v1/auth/context/
Authorization: Bearer <access_token>
```

Purpose:

- Tells the mobile app who the user is.
- Provides the active tenant.
- Provides all accessible company memberships.
- Provides linked employee profile metadata.
- Provides permission codes and suggested navigation entries.

Response shape:

```json
{
  "user": {
    "id": 1,
    "email": "owner@example.com",
    "first_name": "Owner",
    "last_name": "User"
  },
  "active_company": {
    "id": 1,
    "name": "Acme Inc",
    "slug": "acme-inc"
  },
  "memberships": [],
  "employee_profile": {
    "id": 1,
    "emp_id": "EMP-0001",
    "full_name": "Owner User"
  },
  "permissions": [
    "payroll.view_employeeprofile",
    "payroll.view_payrollrun"
  ],
  "features": {
    "employees": "Employee directory, profile, and self-service context.",
    "payroll": "Payroll records, payroll runs, payslips, leave, and IOUs."
  },
  "navigation": [
    "home",
    "profile",
    "notifications",
    "payroll",
    "leave"
  ]
}
```

How mobile should use it:

- Show the active company in the app header.
- Render company switcher only when `memberships.length > 1`.
- Use `navigation` as a backend-recommended default tab list.
- Use `permissions` for finer action-level controls.
- Use `employee_profile` for self-service routes such as profile, payslips,
  leave, IOU, chat, attendance, benefits, learning, and surveys.

## Company Switching

List companies:

```text
GET /api/v1/auth/companies/
Authorization: Bearer <access_token>
```

Switch active company:

```text
POST /api/v1/auth/switch-company/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "company_id": 2
}
```

After switching:

1. Clear tenant-scoped caches.
2. Call `/api/v1/auth/context/` again.
3. Reload visible lists for the new active company.

Important:

- The backend scopes most resources to the active company.
- Data shown before switching should not remain visible after switching.

## Pagination, Search, And Ordering

The API uses DRF page-number pagination.

Default page size:

```text
API_PAGE_SIZE=25
```

Typical list response:

```json
{
  "count": 120,
  "next": "https://example.com/api/v1/employees/?page=2",
  "previous": null,
  "results": []
}
```

Usage:

- Use `next` and `previous` URLs directly where possible.
- Cache by endpoint + query + active company.
- Reset pagination when filters change.

Search:

```text
GET /api/v1/employees/?search=ada
```

Ordering:

```text
GET /api/v1/employees/?ordering=first_name
GET /api/v1/employees/?ordering=-created
```

## Error Handling

Common statuses:

- `200`: success.
- `201`: created.
- `204`: deleted/no content.
- `400`: validation error.
- `401`: missing/expired/invalid auth.
- `403`: authenticated but not allowed.
- `404`: object not found or hidden by tenant boundary.
- `429`: throttled.
- `500`: server error.

Recommended mobile behavior:

- `400`: show field-level validation messages.
- `401`: refresh token once; otherwise log out.
- `403`: show "You do not have permission".
- `404`: show "Not found or no longer accessible".
- `429`: show retry message and backoff.
- `500`: show a generic retry screen and report diagnostics.

## Endpoint Map For Mobile Screens

### Home / App Shell

Use:

```text
GET /api/v1/mobile/config/
GET /api/v1/auth/context/
```

Purpose:

- Bootstrap app.
- Build navigation.
- Load user and tenant state.

### Employee Profile

Use:

```text
GET /api/v1/employees/me/
GET /api/v1/employees/
GET /api/v1/employees/<id>/
PATCH /api/v1/employees/<id>/
```

Purpose:

- Show self profile.
- Show employee directory where permitted.
- Update editable employee details where permitted.

### Departments

Use:

```text
GET /api/v1/departments/
POST /api/v1/departments/
PATCH /api/v1/departments/<id>/
DELETE /api/v1/departments/<id>/
```

Purpose:

- Department list and management.

### Payroll

Use:

```text
GET /api/v1/payrolls/
GET /api/v1/payroll-entries/
GET /api/v1/payroll-runs/
POST /api/v1/payroll-runs/<id>/close/
GET /api/v1/payroll-run-entries/
```

Purpose:

- Payroll overview.
- Pay period list/detail.
- Payroll run close action for authorized users.

### Leave

Use:

```text
GET /api/v1/leave-policies/
GET /api/v1/leave-requests/
POST /api/v1/leave-requests/
POST /api/v1/leave-requests/<id>/approve/
POST /api/v1/leave-requests/<id>/reject/
```

Purpose:

- Employee leave requests.
- Manager/HR approval.
- Leave policy reference.

### IOU / Salary Advance

Use:

```text
GET /api/v1/ious/
POST /api/v1/ious/
POST /api/v1/ious/<id>/approve/
POST /api/v1/ious/<id>/mark-paid/
```

Purpose:

- Employee advance requests.
- Approval and payment workflows.

### Chat

Use:

```text
GET /api/v1/company-chat/rooms/
POST /api/v1/company-chat/rooms/
POST /api/v1/company-chat/rooms/direct/
POST /api/v1/company-chat/rooms/<id>/members/
GET /api/v1/company-chat/messages/
POST /api/v1/company-chat/messages/
POST /api/v1/company-chat/messages/mark-read/
```

Purpose:

- Company chat.
- Room/direct chat.
- Message read state.

### Accounting

Use:

```text
GET /api/v1/accounts/
GET /api/v1/fiscal-years/
GET /api/v1/accounting-periods/
GET /api/v1/journals/
POST /api/v1/journals/<id>/submit/
POST /api/v1/journals/<id>/approve/
POST /api/v1/journals/<id>/post/
GET /api/v1/journal-entries/
```

Purpose:

- Accounting dashboards.
- Journal approvals.
- Account and period references.

Note:

- Accounting API access may be restricted by deployment hardening settings.

### Inventory

Use:

```text
GET /api/v1/inventory/units/
GET /api/v1/inventory/categories/
GET /api/v1/inventory/items/
GET /api/v1/inventory/warehouses/
GET /api/v1/inventory/locations/
GET /api/v1/inventory/suppliers/
GET /api/v1/inventory/customers/
GET /api/v1/inventory/purchase-orders/
POST /api/v1/inventory/purchase-orders/<id>/receive/
GET /api/v1/inventory/documents/
GET /api/v1/inventory/movements/
```

Purpose:

- Inventory catalog.
- Warehouse/location lookups.
- Supplier/customer lookups.
- Purchase order and receiving.
- Stock document and movement history.

### Standups

Use:

```text
GET /api/v1/standup-teams/
GET /api/v1/standup-team-members/
GET /api/v1/standup-questions/
GET /api/v1/standup-checkins/
POST /api/v1/standup-checkins/
POST /api/v1/standup-checkins/<id>/submit/
GET /api/v1/standup-follows/
POST /api/v1/standup-follows/
```

Purpose:

- Team check-ins.
- Question answering.
- Blockers and follow-ups.

## Offline And Sync Guidance

Recommended offline cache:

- Auth context.
- Active company metadata.
- Employee profile.
- Recent payroll runs and payslips metadata.
- Leave requests.
- IOU list.
- Chat room list and recent messages.
- Inventory item list for lookup-heavy screens.

Do not allow offline writes for:

- Payroll close.
- Journal approval/posting.
- Inventory posting actions.
- Company switching.

Safe offline draft candidates:

- Leave request draft.
- IOU request draft.
- Standup check-in draft.
- Chat message pending send.

Sync rules:

1. Store pending writes with endpoint, method, body, and active company ID.
2. On reconnect, call `/api/v1/auth/context/`.
3. If active company changed, do not replay old tenant writes automatically.
4. Replay safe drafts one at a time.
5. On validation error, keep draft and show user-editable errors.

## Realtime Guidance

The backend includes Django Channels and Redis support. Mobile clients can use
WebSocket features where the deployed ASGI server exposes them.

Recommended realtime use:

- Chat messages.
- Notification count/inbox changes.
- Standup reminders.

Fallback:

- Poll notification count.
- Poll chat messages by room.
- Poll standup check-in state.

## Push Notifications

The backend notification model supports channel preferences and delivery logs,
but mobile push provider registration should be implemented as a dedicated API
before shipping push notifications.

Recommended future endpoint:

```text
POST /api/v1/mobile/devices/
DELETE /api/v1/mobile/devices/<id>/
```

Suggested device fields:

- User.
- Active company.
- Platform: `ios` or `android`.
- Device token.
- App version.
- Device model.
- Last seen timestamp.
- Is active.

## Deployment Settings For Mobile

Required:

```text
ALLOWED_HOSTS=api.example.com
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
JWT_ACCESS_MINUTES=30
JWT_REFRESH_DAYS=7
API_PAGE_SIZE=25
```

Mobile config:

```text
MOBILE_API_VERSION=v1
MOBILE_MIN_SUPPORTED_APP_VERSION=1.0.0
MOBILE_CURRENT_APP_VERSION=1.0.0
MOBILE_SUPPORT_EMAIL=support@example.com
MOBILE_SUPPORT_URL=/support/
MOBILE_PRIVACY_URL=/legal/privacy/
MOBILE_TERMS_URL=/legal/terms/
MOBILE_ENABLE_PAYROLL=true
MOBILE_ENABLE_ACCOUNTING=true
MOBILE_ENABLE_STANDUPS=true
MOBILE_ENABLE_CHAT=true
MOBILE_ENABLE_NOTIFICATIONS=true
```

Notes:

- Native mobile apps do not require browser CORS.
- If building a browser-based mobile shell or webview that makes cross-origin
  API calls, add a CORS strategy before release.
- Keep Swagger/Redoc available in staging for mobile development.
- Consider disabling public docs in production if required by policy.

## Mobile QA Checklist

Authentication:

- Login succeeds with valid email/password.
- Invalid password shows validation message.
- Access token refresh works.
- Expired refresh token logs out.

Tenant:

- Active company displays correctly.
- Company switch reloads all tenant data.
- Data from company A never appears under company B.

Permissions:

- Unauthorized screens are hidden.
- Direct API calls to forbidden actions return `403` or `404`.

Payroll:

- Payroll run lists load.
- Payslip details load only for authorized employee/user.
- Payroll close is hidden from unauthorized users.

Leave:

- Employee can submit leave request.
- Manager/HR can approve/reject where permitted.

IOU:

- Employee can submit IOU request.
- Approver can approve.
- Outstanding amount displays correctly.

Inventory:

- Item list loads.
- Purchase order receive works for authorized users.
- Stock movements update after posting.

Accounting:

- Journal list loads for authorized users.
- Approval/post actions respect permissions.

Resilience:

- App handles `401`, `403`, `404`, `429`, and `500`.
- App handles no network.
- App handles forced minimum-version update.
