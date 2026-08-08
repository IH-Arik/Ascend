# Frontend API Requirements Guide

This guide is based on the current code inside `wellness-superadmin-main`.

Goal:

- identify which frontend pages already need backend data
- list the exact APIs required for each page
- show which pages are still static and need wiring
- highlight current frontend gaps before integration starts

## 1. Current Frontend Reality

Current snapshot says:

- there is no shared API client file under `src/utils/api.js`
- `package.json` does not include `axios`
- most pages are still rendering mock arrays or hardcoded text
- `PrivateRoute.jsx` is not enforcing auth
- sidebar role logic uses `localStorage.getItem("role") || "admin"`

So this frontend is not API-integrated yet.

## 2. Route Map

Frontend routes from `src/router/Routes.jsx`:

- `/sign-in`
- `/sign-up`
- `/forgate-password`
- `/verify-code`
- `/new-password`
- `/`
- `/dashboard`
- `/dashboard/burnout-recommendations`
- `/dashboard/burnout-risk-details`
- `/team-members`
- `/team-profile`
- `/organization`
- `/users`
- `/audit-logs`
- `/ai-insights`
- `/report`
- `/risk-alerts`
- `/action-history`
- `/settings`

## 3. Recommended Base Client

Before any page integration, frontend needs:

### Environment variable

Create `.env` in `wellness-superadmin-main`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

### Shared client

Recommended file:

- `wellness-superadmin-main/src/lib/api.js`

Recommended behavior:

- base URL from `VITE_API_URL`
- attach `Authorization: Bearer <token>`
- read token from localStorage
- centralize `401` handling
- optionally add refresh-token retry

## 4. Auth APIs Needed

### Sign In page

File:

- `src/Pages/Auth/SignIn/SignIn.jsx`

Current state:

- static form
- no submit handler
- user is sent to `/dashboard` directly

API needed:

```http
POST /api/v1/auth/login
```

Body:

```json
{
  "email": "superadmin@example.com",
  "password": "password"
}
```

Store after success:

- `access_token`
- `refresh_token`
- `user`
- `user.role`

Frontend note:

- route should not navigate before successful login
- role should be stored from backend response, not hardcoded as `admin`

### Sign Up page

File:

- `src/Pages/Auth/SignUp/SignUp.jsx`

Current state:

- static form
- no submit handler

API needed:

```http
POST /api/v1/auth/register
```

Body:

```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "password123"
}
```

Optional fields:

```json
{
  "organization_name": "Dominion Wellness Solutions",
  "role": "Super Admin"
}
```

Possible next step after success:

- move to email verification
- or sign-in

### Forgot Password page

File:

- `src/Pages/Auth/ForgatePassword/ForgatePassword.jsx`

Current state:

- static email form
- always routes to `/verify-code`

API needed for superadmin flow:

```http
POST /api/v1/auth/superadmin-forgot-password
```

Body:

```json
{
  "email": "superadmin@example.com"
}
```

### Verify Code page

File:

- `src/Pages/Auth/VerifyCode/VerifyCode.jsx`

Current state:

- mock OTP entry
- resend is local alert
- verify is local redirect

APIs needed:

Verify:

```http
POST /api/v1/auth/superadmin-verify-reset-code
```

Body:

```json
{
  "email": "superadmin@example.com",
  "code": "1234"
}
```

Resend:

```http
POST /api/v1/auth/superadmin-resend-reset-code
```

Body:

```json
{
  "email": "superadmin@example.com"
}
```

### New Password page

File:

- `src/Pages/Auth/NewPass/NewPass.jsx`

Current state:

- simulated timeout
- no backend call

API needed:

```http
POST /api/v1/auth/superadmin-reset-password
```

Body:

```json
{
  "email": "superadmin@example.com",
  "code": "1234",
  "new_password": "new-password-123",
  "confirm_password": "new-password-123"
}
```

## 5. Dashboard APIs Needed

### Main Dashboard

File:

- `src/Pages/Dashboard/Dashboard.jsx`

Current state:

- fully hardcoded KPIs, charts, actions, and alerts

Required API:

```http
GET /api/v1/dashboard/superadmin
```

Query params frontend should support:

- `company`
- `department`
- `team`
- `range`
- `start_date`
- `end_date`

This page should consume:

- summary KPI cards
- top risk signal
- recommended actions
- 30-day snapshot
- OPS trend
- driver breakdown
- burnout alert box

### Burnout Recommendations

File:

- `src/Pages/Dashboard/BurnoutRecommendations.jsx`

Current state:

- fully static content

Required API:

```http
GET /api/v1/dashboard/superadmin/burnout-recommendations
```

Query params:

- `company`
- `department`
- `team`
- `range`

Expected content:

- priority focus
- grouped recommendation cards
- guidance note

### Burnout Risk Details

File:

- `src/Pages/Dashboard/BurnoutRiskDetails.jsx`

Current state:

- static trend chart
- static affected members

Required API:

```http
GET /api/v1/dashboard/superadmin/burnout-details
```

Query params:

- `company`
- `department`
- `team`
- `range`

Also needed:

```http
GET /api/v1/dashboard/superadmin/ops-trend
```

For deeper member links:

```http
GET /api/v1/dashboard/superadmin/members/{member_user_id}
```

## 6. Organization APIs Needed

### Organization list

File:

- `src/Pages/Organizations/Organizations.jsx`

Current state:

- static organization cards and table rows

Required API:

```http
GET /api/v1/dashboard/superadmin/organizations
```

Query params:

- `query`
- `risk_filter`
- `sort_by`
- `page`
- `page_size`

Frontend mapping needed:

- search input -> `query`
- show `All/High/Risk` -> `risk_filter`
- sort -> `sort_by`
- pagination -> `page`, `page_size`

### Organization detail dashboard

File:

- `src/Pages/CompanyDashboard/CompanyDashboard.jsx`

Current state:

- static company stats
- static members table

Required API:

```http
GET /api/v1/dashboard/superadmin/organizations/{company_name}
```

Query params:

- `query`
- `risk_filter`
- `sort_by`
- `page`
- `page_size`

### Organization member detail

File:

- `src/Pages/CompanyDashboard/MemberDetailAnalysis.jsx`

Current state:

- static detail page

Required API:

```http
GET /api/v1/dashboard/superadmin/organizations/{company_name}/members/{member_user_id}
```

Query params:

- `range`

## 7. User Management APIs Needed

### Users list

File:

- `src/Pages/Users/Users.jsx`

Current state:

- static user/member rows

Required APIs:

List:

```http
GET /api/v1/dashboard/superadmin/users
```

Query params:

- `query`
- `status_filter`
- `sort_by`
- `page`
- `page_size`

Detail:

```http
GET /api/v1/dashboard/superadmin/users/{user_id}
```

Update:

```http
PATCH /api/v1/dashboard/superadmin/users/{user_id}
```

Body:

```json
{
  "name": "Optional",
  "role": "Optional",
  "organization_name": "Optional"
}
```

Deactivate:

```http
DELETE /api/v1/dashboard/superadmin/users/{user_id}
```

### User detail page

File:

- `src/Pages/Users/UsersDetails.jsx`

Current state:

- static profile/detail UI

Required API:

```http
GET /api/v1/dashboard/superadmin/users/{user_id}
```

## 8. Team Member APIs Needed

### Team Members list

File:

- `src/Pages/TeamMembers/TeamMembers.jsx`

Current state:

- static member list

For superadmin view, required API:

```http
GET /api/v1/dashboard/superadmin/members
```

Query params:

- `company`
- `department`
- `team`
- `query`
- `risk_filter`
- `sort_by`
- `page`
- `page_size`

### Team Profile / Member detail

File:

- `src/Pages/TeamMembers/TeamProfileView.jsx`

Current state:

- static detail view
- action form not wired

Required API:

```http
GET /api/v1/dashboard/superadmin/members/{member_user_id}
```

Query params:

- `company`
- `department`
- `team`
- `range`

If leadership action logging must work from this page, current backend only has leader action endpoints:

```http
POST /api/v1/dashboard/leader/actions
```

Body:

```json
{
  "action": "Rebalance workload",
  "risk_key": "recovery_deficit",
  "note": "Optional",
  "selected_from_recommended": true,
  "department": "Engineering",
  "team": "Alpha"
}
```

Important:

- there is no superadmin action-create route in current backend
- if superadmin must log actions, backend needs a new route or policy change

## 9. AI Insights APIs Needed

File:

- `src/Pages/AiInsights/AiInsights.jsx`

Current state:

- fully static insights, patterns, forecasts, risk table

Required API:

```http
GET /api/v1/dashboard/superadmin/insights
```

Alias:

```http
GET /api/v1/dashboard/superadmin/ai-insights
```

Query params:

- `company`
- `department`
- `team`
- `range`
- `start_date`
- `end_date`

## 10. Report APIs Needed

File:

- `src/Pages/Report/Report.jsx`

Current state:

- fully static KPIs
- static chart
- static members table

Required API:

```http
GET /api/v1/dashboard/superadmin/report
```

Alias:

```http
GET /api/v1/dashboard/superadmin/reports
```

Query params:

- `company`
- `department`
- `team`
- `range`
- `start_date`
- `end_date`
- `page`
- `page_size`

## 11. Risk and Alert APIs Needed

### Risk & Alerts page

File:

- `src/Pages/RiskAlerts/RiskAlerts.jsx`

Current state:

- fully static top risk block
- static recommended actions
- static progress snapshot
- static action log summary

Required APIs:

Risk summary:

```http
GET /api/v1/dashboard/superadmin/alerts
```

Alias:

```http
GET /api/v1/dashboard/superadmin/risk-alerts
```

Recommendations:

```http
GET /api/v1/dashboard/superadmin/burnout-recommendations
```

Burnout details:

```http
GET /api/v1/dashboard/superadmin/burnout-details
```

Query params:

- `company`
- `department`
- `team`
- `range`

### Log Action modal

File:

- `src/Pages/RiskAlerts/LogActionModal.jsx`

Current state:

- modal is local only
- submit just closes modal

If backend remains unchanged:

- superadmin cannot persist this action directly
- only leader action create route exists

Needed backend decision:

1. add `POST /api/v1/dashboard/superadmin/actions`
2. or allow superadmin to call leader action route

Recommended body:

```json
{
  "action": "Rebalance workload",
  "risk_key": "recovery_deficit",
  "note": "Optional note",
  "selected_from_recommended": true,
  "department": "Engineering",
  "team": "Alpha"
}
```

### Action History page

File:

- `src/Pages/RiskAlerts/ActionHistory.jsx`

Current state:

- fully static timeline

Backend situation:

- current backend has `GET /api/v1/dashboard/leader/actions/history`
- there is no superadmin action-history endpoint

So this page needs one of:

1. new backend route:

```http
GET /api/v1/dashboard/superadmin/actions/history
```

or

2. reuse audit logs if product accepts different semantics

Suggested query params:

- `company`
- `department`
- `team`
- `range`
- `outcome`
- `page`
- `page_size`

## 12. Audit Log APIs Needed

File:

- `src/Pages/AuditLogs/AuditLogs.jsx`

Current state:

- local `auditData` array
- detail modal uses local row object

Required APIs:

List:

```http
GET /api/v1/dashboard/superadmin/audit-logs
```

Query params:

- `company`
- `query`
- `time_filter`
- `user_filter`
- `status_filter`
- `page`
- `page_size`

Detail:

```http
GET /api/v1/dashboard/superadmin/audit-logs/{action_log_id}
```

Query params:

- `company`

## 13. Settings APIs Needed

File:

- `src/Pages/settings/Settings.jsx`

Current state:

- fully static forms
- no fetch
- no submit

Required APIs:

Settings menu:

```http
GET /api/v1/dashboard/superadmin/settings
```

Profile data:

```http
GET /api/v1/dashboard/superadmin/settings/profile
```

Profile update:

```http
PATCH /api/v1/dashboard/superadmin/settings/profile
```

Body:

```json
{
  "name": "Optional",
  "email": "Optional",
  "role": "Optional",
  "contact_number": "Optional",
  "employee_id": "Optional",
  "profile_image_url": "Optional"
}
```

Change password page metadata:

```http
GET /api/v1/dashboard/superadmin/settings/change-password
```

Change password submit:

```http
POST /api/v1/users/me/change-password
```

Body:

```json
{
  "current_password": "old",
  "new_password": "new-password-123",
  "confirm_password": "new-password-123"
}
```

Privacy policy:

```http
GET /api/v1/dashboard/superadmin/settings/privacy-policy
PATCH /api/v1/dashboard/superadmin/settings/privacy-policy
```

Terms:

```http
GET /api/v1/dashboard/superadmin/settings/terms-and-conditions
PATCH /api/v1/dashboard/superadmin/settings/terms-and-conditions
```

About us:

```http
GET /api/v1/dashboard/superadmin/settings/about-us
PATCH /api/v1/dashboard/superadmin/settings/about-us
```

Company settings update:

```http
PATCH /api/v1/dashboard/superadmin/settings/company
```

Body:

```json
{
  "company_name": "Optional",
  "company_address": "Optional",
  "company_logo_url": "Optional"
}
```

Scope settings update:

```http
PATCH /api/v1/dashboard/superadmin/settings/scope
```

Body:

```json
{
  "department": "Optional",
  "team": "Optional",
  "role": "Optional"
}
```

Important backend gap:

- current backend has no `GET /dashboard/superadmin/settings/company`
- current backend has no `GET /dashboard/superadmin/settings/scope`

If frontend needs separate hydration for those cards, backend must add them.

## 14. Auth Enforcement Gaps

### PrivateRoute gap

File:

- `src/router/PrivateRoute.jsx`

Current problem:

- redirect is commented out

Needed behavior:

- if no token or user, redirect to `/sign-in`

### Role mapping gap

File:

- `src/Components/Sidebar/Sidebar.jsx`

Current problem:

- frontend assumes `admin`
- backend superadmin access checks for:
  - `super admin`
  - `superadmin`
  - `platform admin`
  - `system admin`

Needed fix:

- derive menu from real backend role
- stop using `admin` as the backend-equivalent role

## 15. Priority Integration Order

Recommended order:

1. shared API client
2. login
3. protected route enforcement
4. dashboard
5. organizations
6. users
7. team members
8. audit logs
9. insights
10. report
11. risk alerts
12. settings
13. forgot-password flow

## 16. Minimal Done Definition

Frontend API integration is not done until:

- login persists token and user
- private routes block unauthenticated access
- all list pages fetch from backend
- all detail pages fetch by selected id or path param
- search, filter, sort, and pagination use query params
- settings forms submit to real PATCH endpoints
- error states show backend `message`
- loading states exist per page
- role-based sidebar uses real backend role

## 17. Short Gap Summary

Current frontend needs these backend groups:

- auth
- dashboard summary
- organizations
- users
- members
- insights
- reports
- alerts
- audit logs
- settings

Current backend gaps that matter for this frontend:

- no superadmin action-create route
- no superadmin action-history route
- no separate GET company settings route
- no separate GET scope settings route
