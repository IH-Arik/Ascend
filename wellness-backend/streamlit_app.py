"""Streamlit client for testing the Dominion Wellness Solutions backend."""

from calendar import month_name
from datetime import datetime
from typing import Any
from html import escape

import httpx
import streamlit as st


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
SUGGESTED_PROMPTS = [
    "Why is my recovery score low?",
    "How can I improve sleep?",
    "What affects my OPS score?",
]

STATUS_COLORS = {
    "Optimal": "#27C86D",
    "Stable": "#14B8C4",
    "Strained": "#F5B800",
    "High Risk": "#FF7A59",
    "Critical": "#FF5A5F",
}


def init_session_state() -> None:
    """Initialize Streamlit session state values."""
    st.session_state.setdefault("api_base_url", DEFAULT_API_BASE_URL)
    st.session_state.setdefault("access_token", "")
    st.session_state.setdefault("refresh_token", "")
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("assessment_page", 0)
    st.session_state.setdefault("onboarding_answers", {})


def api_request(
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    require_auth: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Send an API request and return a success flag with parsed JSON."""
    headers: dict[str, str] = {}
    if require_auth and st.session_state.access_token:
        headers["Authorization"] = f"Bearer {st.session_state.access_token}"

    url = f"{st.session_state.api_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.request(method, url, json=json_data, headers=headers)
        payload = response.json()
    except httpx.HTTPError as exc:
        return False, {"message": f"Request failed: {exc}"}
    except ValueError:
        return False, {"message": f"Non-JSON response returned from {url}"}

    return response.is_success, payload


def save_auth_payload(payload: dict[str, Any]) -> None:
    """Persist auth tokens and user data into session state."""
    data = payload.get("data", {})
    st.session_state.access_token = data.get("access_token", "")
    st.session_state.refresh_token = data.get("refresh_token", "")
    st.session_state.current_user = data.get("user")


def fetch_data(
    path: str,
    require_auth: bool = False,
    data_key: str | None = None,
) -> Any:
    """Fetch JSON data from the backend and return the requested segment."""
    ok, payload = api_request("GET", path, require_auth=require_auth)
    if not ok:
        st.error(payload.get("message", f"Failed to fetch {path}."))
        return None
    data = payload.get("data", {})
    return data.get(data_key) if data_key else data


def fetch_organization_options() -> list[str]:
    """Fetch organization dropdown options from the backend."""
    data = fetch_data("meta/organizations", data_key="organizations") or []
    return [item.get("value", "") for item in data]


def fetch_role_options(organization_name: str | None = None) -> list[str]:
    """Fetch role dropdown options from the backend."""
    query = f"?organization_name={organization_name}" if organization_name else ""
    data = fetch_data(f"meta/roles{query}", data_key="roles") or []
    return [item.get("value", "") for item in data]


def render_api_result(ok: bool, payload: dict[str, Any], success_message: str) -> None:
    """Render a standard API result."""
    if ok:
        st.success(payload.get("message", success_message))
        st.json(payload.get("data", {}))
    else:
        st.error(payload.get("message", "Request failed."))
        st.json(payload)


def build_query_path(path: str, params: dict[str, Any]) -> str:
    """Return a GET path with simple query parameters."""
    active = [
        f"{key}={value}"
        for key, value in params.items()
        if value not in (None, "", [])
    ]
    if not active:
        return path
    return f"{path}?{'&'.join(active)}"


def render_simple_list_card(title: str, items: list[str], empty_text: str) -> None:
    """Render a short list inside a dashboard card."""
    if items:
        body = "".join(f"<li>{escape(str(item))}</li>" for item in items)
        content = f"<ul style='margin:0; padding-left:18px; color:#183b63; line-height:1.7;'>{body}</ul>"
    else:
        content = f"<div class='dws-metric-subtext'>{escape(empty_text)}</div>"
    st.markdown(
        f"""
        <div class="dws-report-card">
            <div class="dws-driver-title" style="margin-bottom:12px;">{escape(title)}</div>
            {content}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    """Render app configuration and session summary."""
    st.sidebar.title("Backend Test Client")
    st.sidebar.text_input(
        "API Base URL",
        key="api_base_url",
        help="Base URL for the FastAPI API.",
    )

    user = st.session_state.current_user
    if user:
        st.sidebar.success(f"Signed in as {user.get('name')}")
        st.sidebar.write(user)
        if st.sidebar.button("Clear Session", use_container_width=True):
            st.session_state.access_token = ""
            st.session_state.refresh_token = ""
            st.session_state.current_user = None
            st.session_state.chat_history = []
            st.rerun()
    else:
        st.sidebar.info("No active session.")


def render_global_styles() -> None:
    """Inject global styles for the visual dashboard sections."""
    st.markdown(
        """
        <style>
        .dws-metric-card {
            border: 1px solid #d7e5f2;
            border-radius: 18px;
            padding: 18px 20px;
            background: #ffffff;
            min-height: 160px;
            box-shadow: 0 8px 24px rgba(13, 52, 104, 0.06);
        }
        .dws-metric-label {
            color: #637b96;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 12px;
        }
        .dws-metric-value {
            color: #0d3470;
            font-size: 2.1rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .dws-metric-subtext {
            color: #6f86a2;
            font-size: 0.95rem;
            margin-top: 10px;
        }
        .dws-insight-box {
            border: 1px dashed #c9daed;
            border-radius: 22px;
            padding: 22px;
            background: #f8fbff;
            margin-top: 8px;
        }
        .dws-driver-card {
            border-radius: 18px;
            background: #ffffff;
            border: 1px solid #e4eef7;
            box-shadow: 0 8px 24px rgba(13, 52, 104, 0.05);
            padding: 18px 18px 16px 18px;
            margin-bottom: 14px;
        }
        .dws-driver-header {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
        }
        .dws-driver-title {
            color: #0d3470;
            font-size: 1.1rem;
            font-weight: 700;
        }
        .dws-driver-key {
            color: #8ea3bc;
            font-size: 0.8rem;
            margin-left: 4px;
        }
        .dws-driver-score {
            color: #0d3470;
            font-size: 2rem;
            font-weight: 700;
            line-height: 1;
        }
        .dws-driver-tag {
            display: inline-block;
            border-radius: 999px;
            padding: 3px 10px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-top: 6px;
        }
        .dws-action-card {
            border-radius: 18px;
            padding: 18px 20px;
            background: linear-gradient(135deg, #11aeb3, #0d3470);
            color: white;
            margin-bottom: 14px;
            box-shadow: 0 8px 24px rgba(17, 174, 179, 0.18);
        }
        .dws-action-card.alt {
            background: #0d3470;
        }
        .dws-report-card {
            border: 1px solid #dfeaf4;
            border-radius: 22px;
            padding: 22px;
            background: #ffffff;
            box-shadow: 0 8px 24px rgba(13, 52, 104, 0.05);
            margin-bottom: 18px;
        }
        .dws-report-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
        }
        .dws-report-badge {
            background: #dff9f8;
            color: #0ea5a6;
            border-radius: 999px;
            padding: 4px 12px;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .dws-bar-row {
            display: flex;
            align-items: flex-end;
            gap: 10px;
            min-height: 170px;
            margin-top: 18px;
        }
        .dws-bar-item {
            flex: 1;
            text-align: center;
        }
        .dws-bar {
            width: 16px;
            margin: 0 auto 10px auto;
            border-radius: 10px 10px 0 0;
            background: #10b7bc;
        }
        .dws-mini-bars {
            display: flex;
            gap: 4px;
            align-items: flex-end;
            justify-content: flex-end;
        }
        .dws-mini-bar {
            width: 14px;
            border-radius: 4px 4px 0 0;
        }
        .dws-behavior-bars {
            display: flex;
            gap: 4px;
            margin-top: 8px;
        }
        .dws-behavior-bar {
            flex: 1;
            border-radius: 4px;
            height: 20px;
        }
        .dws-summary-panel {
            border-radius: 22px;
            padding: 24px;
            background: #0d3470;
            color: white;
            box-shadow: 0 12px 28px rgba(13, 52, 104, 0.16);
        }
        .dws-account-card {
            border-radius: 22px;
            background: #ffffff;
            border: 1px solid #e2ecf6;
            padding: 24px;
            box-shadow: 0 8px 24px rgba(13, 52, 104, 0.05);
            margin-bottom: 18px;
        }
        .dws-account-avatar {
            width: 92px;
            height: 92px;
            border-radius: 999px;
            background: linear-gradient(135deg, #e7be93, #dfb58a);
            margin: 0 auto 16px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 2rem;
            font-weight: 700;
            border: 4px solid #dff7fb;
        }
        .dws-button-outline {
            border: 1px solid #c7d9e8;
            border-radius: 16px;
            padding: 14px 18px;
            text-align: center;
            color: #0d3470;
            font-weight: 700;
            background: #ffffff;
        }
        .dws-list-row {
            border-radius: 18px;
            background: #ffffff;
            border: 1px solid #e2ecf6;
            padding: 18px 20px;
            margin-bottom: 12px;
            box-shadow: 0 8px 24px rgba(13, 52, 104, 0.04);
        }
        .dws-legal-card {
            border-radius: 20px;
            background: #ffffff;
            border: 1px solid #e2ecf6;
            padding: 20px 22px;
            margin-bottom: 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_auth_section() -> None:
    """Render authentication forms."""
    st.subheader("Authentication")

    register_tab, login_tab, verify_tab, reset_tab = st.tabs(
        ["Register", "Login", "Verify Email", "Password Reset"]
    )

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            organization_name = st.text_input("Organization Name")
            role = st.text_input("Role")
            submitted = st.form_submit_button("Register", use_container_width=True)

        if submitted:
            ok, payload = api_request(
                "POST",
                "auth/register",
                {
                    "name": name,
                    "email": email,
                    "password": password,
                    "organization_name": organization_name or None,
                    "role": role or None,
                },
            )
            if ok:
                save_auth_payload(payload)
            render_api_result(ok, payload, "Registered successfully.")

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Login Email")
            password = st.text_input("Login Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            ok, payload = api_request(
                "POST",
                "auth/login",
                {"email": email, "password": password},
            )
            if ok:
                save_auth_payload(payload)
            render_api_result(ok, payload, "Login successful.")

    with verify_tab:
        with st.form("verify_email_form"):
            email = st.text_input("Verification Email")
            code = st.text_input("4-digit Code", max_chars=4)
            submitted = st.form_submit_button("Verify Email", use_container_width=True)

        if submitted:
            ok, payload = api_request(
                "POST",
                "auth/verify-email",
                {"email": email, "code": code},
            )
            render_api_result(ok, payload, "Email verified.")

    with reset_tab:
        forgot_col, verify_col, password_col = st.columns(3)

        with forgot_col:
            with st.form("forgot_password_form"):
                email = st.text_input("Reset Email")
                submitted = st.form_submit_button("Send Code", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "POST",
                    "auth/forgot-password",
                    {"email": email},
                )
                render_api_result(ok, payload, "Reset code sent.")

        with verify_col:
            with st.form("verify_reset_code_form"):
                email = st.text_input("Email for Code Check")
                code = st.text_input("Reset Code", max_chars=4)
                submitted = st.form_submit_button("Verify Code", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "POST",
                    "auth/verify-reset-code",
                    {"email": email, "code": code},
                )
                render_api_result(ok, payload, "Code verified.")

        with password_col:
            with st.form("reset_password_form"):
                email = st.text_input("Email for Password Reset")
                code = st.text_input("Verification Code", max_chars=4)
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                submitted = st.form_submit_button("Reset Password", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "POST",
                    "auth/reset-password",
                    {
                        "email": email,
                        "code": code,
                        "new_password": new_password,
                        "confirm_password": confirm_password,
                    },
                )
                render_api_result(ok, payload, "Password reset successful.")


def render_account_section() -> None:
    """Render account and onboarding management forms."""
    st.subheader("Account")
    if not st.session_state.access_token:
        st.info("Login first to manage account data.")
        return

    view_tab, update_tab, onboarding_tab = st.tabs(
        ["Current User", "Update Account", "Update Onboarding"]
    )

    with view_tab:
        if st.button("Refresh /users/me", use_container_width=True):
            ok, payload = api_request("GET", "users/me", require_auth=True)
            if ok:
                st.session_state.current_user = payload.get("data", {})
            render_api_result(ok, payload, "User fetched.")

    with update_tab:
        current_user = st.session_state.current_user or {}
        with st.form("update_me_form"):
            name = st.text_input("Name", value=current_user.get("name", ""))
            organization_name = st.text_input(
                "Organization Name",
                value=current_user.get("organization_name") or "",
            )
            role = st.text_input("Role", value=current_user.get("role") or "")
            submitted = st.form_submit_button("Update Account", use_container_width=True)

        if submitted:
            ok, payload = api_request(
                "PATCH",
                "users/me",
                {
                    "name": name or None,
                    "organization_name": organization_name or None,
                    "role": role or None,
                },
                require_auth=True,
            )
            if ok:
                st.session_state.current_user = payload.get("data", {})
            render_api_result(ok, payload, "User updated.")

    with onboarding_tab:
        current_user = st.session_state.current_user or {}
        organizations = fetch_organization_options()
        selected_org = (
            current_user.get("organization_name")
            if current_user.get("organization_name") in organizations
            else (organizations[0] if organizations else "")
        )
        roles = fetch_role_options(selected_org)
        selected_role = (
            current_user.get("role")
            if current_user.get("role") in roles
            else (roles[0] if roles else "")
        )
        with st.form("update_onboarding_form"):
            organization_name = st.selectbox(
                "Onboarding Organization Name",
                options=organizations or [""],
                index=(organizations.index(selected_org) if selected_org in organizations else 0),
            )
            role = st.selectbox(
                "Onboarding Role",
                options=roles or [""],
                index=(roles.index(selected_role) if selected_role in roles else 0),
            )
            onboarding_completed = st.checkbox(
                "Onboarding Completed",
                value=bool(current_user.get("onboarding_completed", False)),
            )
            submitted = st.form_submit_button("Update Onboarding", use_container_width=True)

        if submitted:
            ok, payload = api_request(
                "PATCH",
                "users/me/onboarding",
                {
                    "organization_name": organization_name or None,
                    "role": role or None,
                    "onboarding_completed": onboarding_completed,
                },
                require_auth=True,
            )
            if ok:
                st.session_state.current_user = payload.get("data", {})
            render_api_result(ok, payload, "Onboarding updated.")


def render_account_screen() -> None:
    """Render a visual account screen using the account summary endpoint."""
    st.subheader("Account View")
    if not st.session_state.access_token:
        st.info("Login first to load the account screen.")
        return

    ok, payload = api_request("GET", "users/me/account-summary", require_auth=True)
    if not ok:
        st.error(payload.get("message", "Failed to load account summary."))
        st.json(payload)
        return

    data = payload.get("data", {})
    profile = data.get("profile", {})
    organization = data.get("organization", {})
    performance = data.get("performance_profile", {})
    settings_items = data.get("settings_support", [])

    initials = "".join(part[0] for part in profile.get("name", "User").split()[:2]).upper()
    age_badge = f"Age: {profile.get('age')}" if profile.get("age") is not None else "Age unavailable"

    st.markdown(
        f"""
        <div class="dws-account-card" style="text-align:center;">
            <div class="dws-account-avatar">{escape(initials)}</div>
            <div class="dws-driver-title" style="font-size:2rem;">{escape(profile.get("name", ""))}</div>
            <div class="dws-metric-subtext">{escape(profile.get("email", ""))}</div>
            <div style="margin:14px auto 18px auto; display:inline-block; background:#eef4fb; color:#0d3470; border-radius:999px; padding:6px 14px; font-weight:600;">
                {escape(age_badge)}
            </div>
            <div class="dws-button-outline">Edit Profile</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Organization")
    st.markdown(
        f"""
        <div class="dws-account-card">
            <div class="dws-driver-title">{escape(organization.get("organization_name") or "No organization")}</div>
            <div class="dws-metric-subtext">{escape(organization.get("subtitle") or "Profile details not completed")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Performance Profile")
    st.markdown(
        f"""
        <div class="dws-summary-panel">
            <div class="dws-metric-label" style="color:#54d5db;">Current OPS Score</div>
            <div style="font-size:3rem; font-weight:700;">
                {performance.get("current_ops_score", 0):.0f}<span style="font-size:1.5rem; color:#22d3ee;"> /100</span>
            </div>
            <div style="margin-top:18px; border-top:1px solid rgba(255,255,255,0.14); padding-top:18px;" class="dws-report-row">
                <div>
                    <div class="dws-metric-label" style="color:#8ab1d4;">Strongest Driver</div>
                    <div style="color:#22d3ee; font-size:1.15rem; font-weight:700;">
                        {escape(performance.get("strongest_driver") or "Unavailable")}
                    </div>
                </div>
                <div>
                    <div class="dws-metric-label" style="color:#8ab1d4;">Focus Driver</div>
                    <div style="color:#f59e0b; font-size:1.15rem; font-weight:700;">
                        {escape(performance.get("focus_driver") or "Unavailable")}
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Settings & Support")
    for item in settings_items:
        st.markdown(
            f"""
            <div class="dws-account-card" style="padding:18px 20px;">
                <div class="dws-report-row">
                    <div class="dws-driver-title" style="font-size:1.1rem;">{escape(item.get("title", ""))}</div>
                    <div style="color:#a0b3c8;">&rsaquo;</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    logout_col, delete_col = st.columns(2)
    with logout_col:
        with st.form("logout_form"):
            confirm_logout = st.checkbox("Do you want to log out?")
            submitted = st.form_submit_button("Log Out", use_container_width=True)
        if submitted and confirm_logout:
            logout_ok, logout_payload = api_request("POST", "auth/logout", require_auth=True)
            if logout_ok:
                st.session_state.access_token = ""
                st.session_state.refresh_token = ""
                st.session_state.current_user = None
                st.session_state.chat_history = []
            render_api_result(logout_ok, logout_payload, "Logged out successfully.")

    with delete_col:
        with st.form("delete_account_form"):
            confirm_delete = st.checkbox("Confirm deleting your account")
            submitted = st.form_submit_button("Delete Account", use_container_width=True)
        if submitted and confirm_delete:
            delete_ok, delete_payload = api_request("DELETE", "users/me", require_auth=True)
            if delete_ok:
                st.session_state.access_token = ""
                st.session_state.refresh_token = ""
                st.session_state.current_user = None
                st.session_state.chat_history = []
            render_api_result(delete_ok, delete_payload, "Account deleted successfully.")


def render_edit_profile_screen() -> None:
    """Render a visual edit profile screen."""
    st.subheader("Edit Profile")
    if not st.session_state.access_token:
        st.info("Login first to edit profile.")
        return

    profile_ok, profile_payload = api_request("GET", "users/me/profile", require_auth=True)
    profile_data = profile_payload.get("data", {}) if profile_ok else {}

    organizations = fetch_organization_options()
    selected_company = (
        profile_data.get("company")
        if profile_data.get("company") in organizations
        else (organizations[0] if organizations else "")
    )
    role_options = fetch_role_options(selected_company)
    selected_role = (
        profile_data.get("role")
        if profile_data.get("role") in role_options
        else (role_options[0] if role_options else "")
    )

    with st.form("visual_edit_profile_form"):
        st.markdown(
            f"""
            <div class="dws-account-card" style="text-align:center;">
                <div class="dws-account-avatar">
                    {escape(''.join(part[0] for part in profile_data.get('name', 'User').split()[:2]).upper() or 'U')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        name = st.text_input("Name", value=profile_data.get("name", ""))
        col1, col2 = st.columns(2)
        with col1:
            age = st.number_input("Age", min_value=0, max_value=120, value=int(profile_data.get("age", 0)))
        with col2:
            gender = st.selectbox(
                "Gender",
                options=["Male", "Female", "Other"],
                index=["Male", "Female", "Other"].index(profile_data.get("gender", "Male"))
                if profile_data.get("gender", "Male") in ["Male", "Female", "Other"]
                else 0,
            )
        company = st.selectbox(
            "Company",
            options=organizations or [""],
            index=(organizations.index(selected_company) if selected_company in organizations else 0),
        )
        department = st.text_input("Department", value=profile_data.get("department", ""))
        team = st.text_input("Team", value=profile_data.get("team", ""))
        role = st.selectbox(
            "Work Role",
            options=role_options or [""],
            index=(role_options.index(selected_role) if selected_role in role_options else 0),
        )
        col3, col4 = st.columns(2)
        with col3:
            height_cm = st.number_input("Height (cm)", min_value=0.0, value=float(profile_data.get("height_cm", 0.0)))
        with col4:
            weight_kg = st.number_input("Weight (kg)", min_value=0.0, value=float(profile_data.get("weight_kg", 0.0)))
        save = st.form_submit_button("Save Profile", use_container_width=True)

    if save:
        payload = {
            "name": name,
            "age": int(age),
            "gender": gender,
            "company": company,
            "department": department,
            "team": team,
            "role": role,
            "height_cm": float(height_cm),
            "weight_kg": float(weight_kg),
        }
        path = "users/me/profile" if profile_ok else "users/me/profile"
        method = "PATCH" if profile_ok else "POST"
        ok, response_payload = api_request(method, path, payload, require_auth=True)
        render_api_result(ok, response_payload, "Profile saved successfully.")


def render_account_settings_screen() -> None:
    """Render an account settings menu screen."""
    st.subheader("Account Settings")
    st.markdown(
        """
        <div class="dws-list-row"><div class="dws-report-row"><div class="dws-driver-title">Change Password</div><div>&rsaquo;</div></div></div>
        <div class="dws-list-row"><div class="dws-report-row"><div class="dws-driver-title">Terms of condition</div><div>&rsaquo;</div></div></div>
        <div class="dws-list-row"><div class="dws-report-row"><div class="dws-driver-title">Privacy Policy</div><div>&rsaquo;</div></div></div>
        <div class="dws-list-row"><div class="dws-report-row"><div class="dws-driver-title">About Us</div><div>&rsaquo;</div></div></div>
        """,
        unsafe_allow_html=True,
    )


def render_change_password_screen() -> None:
    """Render a change password screen."""
    st.subheader("Change Password")
    if not st.session_state.access_token:
        st.info("Login first to change your password.")
        return

    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Update Password", use_container_width=True)

    if submitted:
        ok, payload = api_request(
            "POST",
            "users/me/change-password",
            {
                "current_password": current_password,
                "new_password": new_password,
                "confirm_password": confirm_password,
            },
            require_auth=True,
        )
        render_api_result(ok, payload, "Password updated successfully.")


def render_help_center_screen() -> None:
    """Render help center content from backend."""
    st.subheader("Help Center")
    ok, payload = api_request("GET", "users/help-center", require_auth=False)
    if not ok:
        st.error(payload.get("message", "Failed to fetch help center."))
        st.json(payload)
        return

    data = payload.get("data", {})
    st.markdown(f"## {escape(data.get('title', 'How can we help?'))}")
    st.write(data.get("subtitle", ""))
    st.text_input("Search for help topics...", disabled=True)
    st.markdown("### Frequently Asked Questions")
    for faq in data.get("faqs", []):
        with st.expander(faq.get("question", ""), expanded=faq == data.get("faqs", [None])[0]):
            st.write(faq.get("answer", ""))

    st.markdown(
        f"""
        <div class="dws-summary-panel">
            <div style="font-size:1.7rem; font-weight:700; margin-bottom:10px;">{escape(data.get("support_cta_title", ""))}</div>
            <div style="font-size:1rem; line-height:1.7;">{escape(data.get("support_cta_description", ""))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_contact_support_screen() -> None:
    """Render contact support form."""
    st.subheader("Contact Support")
    if not st.session_state.access_token:
        st.info("Login first to submit a support request.")
        return

    current_user = st.session_state.current_user or {}
    st.markdown("## How can we help?")
    st.write("Our performance team typically responds within 2 hours.")
    with st.form("contact_support_form"):
        issue = st.text_area("Describe your issue", height=180)
        st.text_input("Email", value=current_user.get("email", ""), disabled=True)
        submitted = st.form_submit_button("Submit Request", use_container_width=True)

    if submitted:
        ok, payload = api_request(
            "POST",
            "users/me/support-request",
            {"issue": issue},
            require_auth=True,
        )
        render_api_result(ok, payload, "Support request submitted successfully.")


def render_legal_screen(title: str, endpoint: str) -> None:
    """Render legal/about content from backend."""
    st.subheader(title)
    ok, payload = api_request("GET", endpoint, require_auth=False)
    if not ok:
        st.error(payload.get("message", f"Failed to fetch {title}."))
        st.json(payload)
        return

    data = payload.get("data", {})
    for index, item in enumerate(data.get("items", []), start=1):
        st.markdown(
            f"""
            <div class="dws-legal-card">
                <div style="font-size:1rem; color:#1f3352; line-height:1.8;">
                    <strong>{index}.</strong> {escape(item)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_question_bank_section(questions: list[dict[str, Any]]) -> None:
    """Render the onboarding assessment question bank."""
    st.subheader("Onboarding Assessment Questions")
    if not questions:
        st.info("No onboarding questions loaded.")
        return

    st.caption(f"Loaded {len(questions)} questions")
    for question in questions:
        with st.expander(f"{question['order']}. {question['text']}"):
            st.write(
                {
                    "driver": question["driver"],
                    "response_type": question["response_type"],
                    "options": question["options"],
                }
            )


def render_assessment_form(
    title: str,
    form_key: str,
    questions: list[dict[str, Any]],
    submit_path: str,
    submit_label: str,
    require_auth: bool = True,
) -> None:
    """Render a generic question form against one backend endpoint."""
    st.subheader(title)
    if require_auth and not st.session_state.access_token:
        st.info("Login first to use this form.")
        return
    if not questions:
        st.info("Questions are required before submission.")
        return

    with st.form(form_key):
        answers: list[dict[str, str]] = []
        for question in questions:
            answer = st.radio(
                question["text"],
                options=question["options"],
                key=f"{form_key}_{question['id']}",
            )
            answers.append({"question_id": question["id"], "answer": answer})

        submitted = st.form_submit_button(submit_label, use_container_width=True)

    if submitted:
        ok, payload = api_request(
            "POST",
            submit_path,
            {"answers": answers},
            require_auth=require_auth,
        )
        render_api_result(ok, payload, f"{title} submitted successfully.")


def render_onboarding_assessment_section(questions: list[dict[str, Any]]) -> None:
    """Render the onboarding assessment submission form with 5-page pagination."""
    if not st.session_state.access_token:
        st.subheader("Onboarding Assessment")
        st.info("Login first to submit the onboarding assessment.")
        return
    if not questions:
        st.subheader("Onboarding Assessment")
        st.info("Onboarding questions are required before submission.")
        return

    st.subheader("Onboarding Assessment")
    status_ok, status_payload = api_request("GET", "assessments/status", require_auth=True)
    if status_ok:
        status_data = status_payload.get("data", {})
        status_cols = st.columns(4)
        status_items = [
            ("Can Submit", "Yes" if status_data.get("can_submit_assessment") else "No"),
            ("Initial", "Yes" if status_data.get("is_initial_assessment") else "No"),
            ("Last Assessment", status_data.get("last_assessment_date") or "None"),
            ("Next Eligible", status_data.get("next_eligible_date") or "Now"),
        ]
        for index, (label, value) in enumerate(status_items):
            with status_cols[index]:
                st.markdown(
                    f"""
                    <div class="dws-metric-card">
                        <div class="dws-metric-label">{escape(label)}</div>
                        <div class="dws-metric-value" style="font-size:1.2rem;">{escape(str(value))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        if status_data.get("lock_message"):
            st.info(status_data["lock_message"])
        if not status_data.get("can_submit_assessment"):
            return


    st.divider()
    current_page = st.session_state.setdefault("assessment_page", 0)
    st.session_state.setdefault("onboarding_answers", {})
    
    # Filter questions for current step based on backend provided step field
    page_questions = [q for q in questions if q.get("step") == current_page + 1]
    total_pages = max([q.get("step", 1) for q in questions]) if questions else 1
    
    # Progress bar and page info
    progress = (current_page + 1) / total_pages
    st.progress(progress)
    st.write(f"Step {current_page + 1} of {total_pages}")

    # Display questions for this step
    for q in page_questions:
        q_id = q["id"]
        options = q["options"]
        default_val = st.session_state.onboarding_answers.get(q_id, options[0])
        try:
            default_idx = options.index(default_val) if default_val in options else 0
        except ValueError:
            default_idx = 0
            
        answer = st.selectbox(
            q["text"],
            options=options,
            index=default_idx,
            key=f"onb_q_{q_id}"
        )
        st.session_state.onboarding_answers[q_id] = answer

    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if current_page > 0:
            if st.button("Previous", use_container_width=True, key="onb_prev_btn"):
                st.session_state.assessment_page -= 1
                st.rerun()
    
    with col3:
        if current_page < total_pages - 1:
            if st.button("Next", use_container_width=True, key="onb_next_btn"):
                st.session_state.assessment_page += 1
                st.rerun()
        else:
            if st.button("Submit Assessment", type="primary", use_container_width=True, key="onb_submit_btn"):
                # Prepare all answers
                all_answers = []
                for q in questions:
                    q_id = q["id"]
                    val = st.session_state.onboarding_answers.get(q_id, q["options"][0])
                    all_answers.append({"question_id": q_id, "answer": val})
                
                ok, payload = api_request(
                    "POST",
                    "assessments/checkins",
                    {"answers": all_answers},
                    require_auth=True,
                )
                render_api_result(ok, payload, "Assessment submitted successfully.")
                if ok:
                    # Reset assessment state on success
                    st.session_state.assessment_page = 0
                    st.session_state.onboarding_answers = {}
                    st.rerun()

def render_checkin_section(
    title: str,
    questions: list[dict[str, Any]],
    status_path: str | None,
    submit_path: str,
    lock_message: str,
    form_key: str,
) -> None:
    """Render a daily, weekly, or monthly check-in section."""
    st.subheader(title)
    if not st.session_state.access_token:
        st.info("Login first to use this section.")
        return
    if not questions:
        st.info("Questions are required before submission.")
        return

    behavior_options = [
        "physical_activity",
        "recovery_practice",
        "gratitude_reflection",
        "meaningful_connection",
        "intentional_sleep_routine",
    ]

    if status_path:
        ok, payload = api_request("GET", status_path, require_auth=True)
        if not ok:
            st.error(payload.get("message", "Failed to fetch status."))
            st.json(payload)
            return
        status_data = payload.get("data", {})
        st.write(status_data)
        status_flag = (
            status_data.get("should_show_weekly_checkin")
            or status_data.get("should_show_monthly_checkin")
        )
        if status_path.endswith("status") and title != "Daily Check-In" and not status_flag:
            st.info(lock_message)
            return

    if submit_path == "daily-checkins":
        intervention_ok, intervention_payload = api_request(
            "GET",
            "daily-checkins/intervention",
            require_auth=True,
        )
        if intervention_ok:
            intervention = intervention_payload.get("data", {})
            st.markdown(
                f"""
                <div class="dws-insight-box" style="border-left:6px solid #0ea5a6;">
                    <div class="dws-metric-label">Today's Intervention</div>
                    <div style="font-size:1.25rem; font-weight:700; color:#0d3470; margin-bottom:8px;">
                        {escape(str(intervention.get("category", "recovery")).replace("_", " ").title())}
                    </div>
                    <div style="color:#183b63; line-height:1.7;">
                        <strong>Recommendation</strong><br>
                        {escape(str(intervention.get("recommendation", "No recommendation available.")))}<br><br>
                        <strong>Reason</strong><br>
                        {escape(str(intervention.get("reason_line", "No reason available.")))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            response_cols = st.columns(4)
            response_map = {
                "Completed": "completed",
                "Partial": "partial",
                "Not Completed": "not_completed",
                "No Response": "no_response",
            }
            for index, (label, value) in enumerate(response_map.items()):
                with response_cols[index]:
                    if st.button(label, key=f"{form_key}_{value}", use_container_width=True):
                        ok, payload = api_request(
                            "POST",
                            "daily-checkins/intervention/response",
                            {"status": value},
                            require_auth=True,
                        )
                        render_api_result(ok, payload, "Intervention response recorded.")

    with st.form(form_key):
        answers: list[dict[str, str]] = []
        for question in questions:
            answer = st.radio(
                question["text"],
                options=question["options"],
                key=f"{form_key}_{question['id']}",
            )
            answers.append({"question_id": question["id"], "answer": answer})
        behaviors = st.multiselect(
            "Optional Behaviors",
            options=behavior_options,
            key=f"{form_key}_behaviors",
            help="Used for behavior logs and streak tracking.",
        )

        submitted = st.form_submit_button(f"Submit {title}", use_container_width=True)

    if submitted:
        ok, payload = api_request(
            "POST",
            submit_path,
            {"answers": answers, "behaviors": behaviors},
            require_auth=True,
        )
        render_api_result(ok, payload, f"{title} submitted successfully.")


def render_scores_section() -> None:
    """Render score retrieval actions."""
    st.subheader("Scores")
    if not st.session_state.access_token:
        st.info("Login first to fetch scores.")
        return

    latest_col, history_col, by_checkin_col = st.columns([1, 1, 2])

    with latest_col:
        if st.button("Latest Score", use_container_width=True):
            ok, payload = api_request("GET", "scores/latest", require_auth=True)
            render_api_result(ok, payload, "Latest score fetched.")

    with history_col:
        if st.button("Score History", use_container_width=True):
            ok, payload = api_request("GET", "scores/history", require_auth=True)
            render_api_result(ok, payload, "Score history fetched.")

    with by_checkin_col:
        with st.form("score_by_checkin_form"):
            checkin_id = st.text_input("Check-in ID")
            submitted = st.form_submit_button("Fetch Score by Check-in", use_container_width=True)
        if submitted:
            ok, payload = api_request(
                "GET",
                f"scores/{checkin_id}",
                require_auth=True,
            )
            render_api_result(ok, payload, "Score fetched.")


def render_dashboard_section() -> None:
    """Render dashboard fetch actions and payloads."""
    st.subheader("Dashboard")
    if not st.session_state.access_token:
        st.info("Login first to load dashboard data.")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Home Dashboard", use_container_width=True):
            ok, payload = api_request("GET", "dashboard/home", require_auth=True)
            render_api_result(ok, payload, "Home dashboard fetched.")

    with col2:
        if st.button("Progress", use_container_width=True):
            ok, payload = api_request("GET", "dashboard/progress", require_auth=True)
            render_api_result(ok, payload, "Dashboard progress fetched.")

    with col3:
        if st.button("Streaks", use_container_width=True):
            ok, payload = api_request("GET", "dashboard/streaks", require_auth=True)
            render_api_result(ok, payload, "Dashboard streaks fetched.")

    with col4:
        if st.button("Recommendations", use_container_width=True):
            ok, payload = api_request("GET", "dashboard/recommendations", require_auth=True)
            render_api_result(ok, payload, "Dashboard recommendations fetched.")

    home_ok, home_payload = api_request("GET", "dashboard/home", require_auth=True)
    if not home_ok:
        st.error(home_payload.get("message", "Failed to load dashboard snapshot."))
        return

    home_data = home_payload.get("data", {})
    performance = home_data.get("overall_performance", {})
    indicators = home_data.get("dashboard_indicators", [])
    burnout_alert = home_data.get("burnout_alert", {})

    summary_cols = st.columns(2)
    with summary_cols[0]:
        st.markdown(
            f"""
            <div class="dws-metric-card">
                <div class="dws-metric-label">OPS Readiness Score</div>
                <div class="dws-metric-value">{performance.get("overall_score", 0):.0f}</div>
                <div class="dws-metric-subtext">{escape(str(performance.get("score_label", "Unknown")))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with summary_cols[1]:
        st.markdown(
            f"""
            <div class="dws-metric-card">
                <div class="dws-metric-label">Trend Summary</div>
                <div class="dws-metric-value" style="font-size:1.5rem;">{performance.get("percentage_change", 0):+.1f}%</div>
                <div class="dws-metric-subtext">{escape(str(home_data.get("trend_insight", "Unavailable")))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if indicators:
        st.markdown("### Launch Indicators")
        indicator_cols = st.columns(len(indicators))
        indicator_colors = {
            "success": "#27C86D",
            "steady": "#14B8C4",
            "warning": "#F5B800",
            "critical": "#FF5A5F",
        }
        for index, indicator in enumerate(indicators):
            with indicator_cols[index]:
                color = indicator_colors.get(indicator.get("status"), "#14B8C4")
                st.markdown(
                    f"""
                    <div class="dws-metric-card" style="border-top:4px solid {color};">
                        <div class="dws-metric-label">{escape(indicator.get("label", ""))}</div>
                        <div class="dws-metric-value" style="font-size:1.4rem;">{escape(str(indicator.get("value", "")))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if burnout_alert:
        alert_active = burnout_alert.get("is_active", False)
        alert_color = "#FF5A5F" if alert_active else "#F5B800"
        triggered = burnout_alert.get("triggered_signals", [])
        trigger_text = ", ".join(item.get("label", "") for item in triggered) or "No burnout signals triggered."
        action_items = burnout_alert.get("recommended_actions_preview", [])
        action_text = "<br>".join(escape(item) for item in action_items) or "No action needed right now."
        escalation_line = ""
        if burnout_alert.get("escalated"):
            escalation_line = (
                f"<br>Escalated: {escape(str(burnout_alert.get('escalation_target', 'Higher leadership')))}"
            )

        st.markdown("### Burnout Alert")
        st.markdown(
            f"""
            <div class="dws-insight-box" style="border-left:6px solid {alert_color};">
                <div class="dws-metric-label">Alert Level</div>
                <div style="font-size:1.35rem; font-weight:700; color:{alert_color}; margin-bottom:8px;">
                    {escape(str(burnout_alert.get("level", "Low")))}
                </div>
                <div style="color:#183b63; line-height:1.75;">
                    {int(burnout_alert.get("signals_in_risk", 0))} of {int(burnout_alert.get("total_signals", 6))} signals in risk zone.<br>
                    Trend: {escape(str(burnout_alert.get("trend", "New")))}<br>
                    Consecutive elevated days: {int(burnout_alert.get("consecutive_elevated_days", 0))}<br>
                    Drivers: {escape(trigger_text)}{escalation_line}<br><br>
                    <strong>Recommended Actions</strong><br>
                    {action_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Team & Leader Dashboard")
    filter_cols = st.columns(3)
    with filter_cols[0]:
        team_department = st.text_input("Department Filter", key="team_dashboard_department")
    with filter_cols[1]:
        team_name = st.text_input("Team Filter", key="team_dashboard_team")
    with filter_cols[2]:
        if st.button("Refresh Team Dashboard", key="refresh_team_dashboard", use_container_width=True):
            st.rerun()

    team_path = build_query_path(
        "dashboard/team",
        {"department": team_department, "team": team_name},
    )
    team_ok, team_payload = api_request("GET", team_path, require_auth=True)
    if not team_ok:
        st.warning(team_payload.get("message", "Team dashboard unavailable."))
        return

    team_data = team_payload.get("data", {})
    team_summary = team_data.get("team_summary", {})
    group_burnout = team_data.get("group_burnout", {})
    top_risk = team_data.get("top_risk_signal", {})
    recent_actions = team_data.get("recent_actions", [])
    progress_snapshot = team_data.get("progress_snapshot", {})
    leader_nudges = team_data.get("leader_nudges", [])
    driver_breakdown = team_data.get("driver_breakdown", [])
    member_snapshots = team_data.get("member_snapshots", [])

    summary_cols = st.columns(4)
    summary_values = [
        ("Average OPS", team_summary.get("average_ops", "N/A")),
        ("Members", team_summary.get("member_count", 0)),
        ("Elevated Burnout", group_burnout.get("elevated_members", 0)),
        ("Leadership Climate", group_burnout.get("average_leadership_climate", "N/A")),
    ]
    for index, (label, value) in enumerate(summary_values):
        with summary_cols[index]:
            display_value = f"{value:.1f}" if isinstance(value, float) else str(value)
            st.markdown(
                f"""
                <div class="dws-metric-card">
                    <div class="dws-metric-label">{escape(label)}</div>
                    <div class="dws-metric-value" style="font-size:1.4rem;">{escape(display_value)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    risk_color_map = {
        "critical": "#FF5A5F",
        "warning": "#F5B800",
        "steady": "#14B8C4",
    }
    top_risk_color = risk_color_map.get(top_risk.get("status"), "#14B8C4")
    st.markdown(
        f"""
        <div class="dws-action-card" style="background:{top_risk_color};">
            <div class="dws-metric-label" style="color:white;">Top Risk Signal</div>
            <div style="font-size:1.4rem; font-weight:700; margin-bottom:8px;">
                {escape(str(top_risk.get("headline", "No immediate risk detected")))}
            </div>
            <div style="font-size:1rem; line-height:1.7;">
                {escape(str(top_risk.get("summary", "No summary available.")))}<br>
                Trend: {escape(str(top_risk.get("trend", "Stable")))}<br>
                Affected Members: {escape(str(top_risk.get("affected_members", 0)))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_cols = st.columns([2, 1])
    with action_cols[0]:
        render_simple_list_card(
            "Recommended Actions",
            [str(item) for item in top_risk.get("recommended_actions", [])],
            "No actions available.",
        )
    with action_cols[1]:
        with st.form("team_action_log_form"):
            recommended_options = [str(item) for item in top_risk.get("recommended_actions", [])]
            action_choice = st.selectbox(
                "Recommended Action",
                options=[""] + recommended_options,
                key="team_action_choice",
            )
            custom_action = st.text_input("Or Custom Action", key="team_action_custom")
            action_note = st.text_area("Optional Note", height=100, key="team_action_note")
            submitted = st.form_submit_button("Log Action", use_container_width=True)
        if submitted:
            selected_action = custom_action.strip() or action_choice.strip()
            if not selected_action:
                st.error("Action lagbe.")
            else:
                ok, payload = api_request(
                    "POST",
                    "dashboard/team/actions",
                    {
                        "action": selected_action,
                        "risk_key": top_risk.get("key", "other"),
                        "note": action_note or None,
                        "selected_from_recommended": bool(action_choice.strip()),
                        "department": team_department or None,
                        "team": team_name or None,
                    },
                    require_auth=True,
                )
                render_api_result(ok, payload, "Leader action logged successfully.")

    progress_cols = st.columns(2)
    with progress_cols[0]:
        top_risk_change = progress_snapshot.get("top_risk_change", {})
        burnout_trend = progress_snapshot.get("burnout_level_trend", {})
        st.markdown(
            f"""
            <div class="dws-report-card">
                <div class="dws-driver-title" style="margin-bottom:12px;">Progress Snapshot</div>
                <div class="dws-metric-subtext">Window: {escape(str(progress_snapshot.get("comparison_window_days", 14)))} days</div>
                <div style="color:#183b63; line-height:1.9; margin-top:12px;">
                    Top Risk: {escape(str(top_risk_change.get("before", "N/A")))} → {escape(str(top_risk_change.get("after", "N/A")))}<br>
                    Status: {escape(str(top_risk_change.get("status", "Stable")))}<br>
                    Burnout Trend: {escape(str(burnout_trend.get("status", "Stable")))} ({escape(str(burnout_trend.get("delta", 0)))})
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with progress_cols[1]:
        domain_lines = []
        for item in progress_snapshot.get("domain_score_changes", []):
            delta = item.get("delta")
            delta_text = "N/A" if delta is None else f"{delta:+.1f}"
            domain_lines.append(f"{item.get('label', '')}: {delta_text}")
        render_simple_list_card("Domain Score Changes", domain_lines, "No domain change data.")

    if driver_breakdown:
        st.markdown("#### Driver Breakdown")
        driver_cols = st.columns(len(driver_breakdown))
        for index, driver in enumerate(driver_breakdown):
            with driver_cols[index]:
                color = STATUS_COLORS.get(driver.get("condition", "Stable"), "#14B8C4")
                st.markdown(
                    f"""
                    <div class="dws-driver-card" style="border-left:6px solid {color};">
                        <div class="dws-driver-title">{escape(driver.get("label", ""))}</div>
                        <div class="dws-driver-score">{float(driver.get("average_score", 0)):.0f}</div>
                        <div class="dws-metric-subtext">{escape(str(driver.get("condition", "Unknown")))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    lower_cols = st.columns(2)
    with lower_cols[0]:
        action_lines = [
            f"{item.get('created_at', '')}: {item.get('action', '')}"
            for item in recent_actions
        ]
        render_simple_list_card("Recent Actions", action_lines, "No actions logged yet.")
    with lower_cols[1]:
        nudge_lines = [str(item.get("message", "")) for item in leader_nudges]
        render_simple_list_card("Leader Nudges", nudge_lines, "No nudges right now.")

    if member_snapshots:
        st.markdown("#### Member Risk Snapshot")
        for member in member_snapshots[:8]:
            st.markdown(
                f"""
                <div class="dws-list-row">
                    <div class="dws-report-row">
                        <div>
                            <div class="dws-driver-title">{escape(str(member.get("name", "Unknown")))}</div>
                            <div class="dws-metric-subtext">
                                Burnout: {escape(str(member.get("burnout_level", "Low")))} |
                                Signals: {escape(str(member.get("signals_in_risk", 0)))}
                            </div>
                        </div>
                        <div class="dws-report-badge">{escape(str(member.get("stress_value", "N/A")))}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_report_screen() -> None:
    """Render a visual performance report screen using the backend report API."""
    st.subheader("Performance Report")
    if not st.session_state.access_token:
        st.info("Login first to load the performance report.")
        return

    current_month = datetime.utcnow().month
    current_year = datetime.utcnow().year

    filter_columns = st.columns(3)
    with filter_columns[0]:
        selected_week_label = st.selectbox(
            "Week",
            options=["All", "1 Week", "2 Week", "3 Week", "4 Week"],
            index=0,
            key="report_week",
        )
    with filter_columns[1]:
        month_options = [month_name[index] for index in range(1, 13)]
        selected_month_label = st.selectbox(
            "Month",
            options=month_options,
            index=current_month - 1,
            key="report_month",
        )
    with filter_columns[2]:
        selected_year = st.selectbox(
            "Year",
            options=[current_year - index for index in range(5)],
            index=0,
            key="report_year",
        )

    week_map = {
        "All": "all",
        "1 Week": "1",
        "2 Week": "2",
        "3 Week": "3",
        "4 Week": "4",
    }
    month_value = month_options.index(selected_month_label) + 1
    report_ok, report_payload = api_request(
        "GET",
        f"dashboard/report?week={week_map[selected_week_label]}&month={month_value}&year={selected_year}",
        require_auth=True,
    )
    if not report_ok:
        st.error(report_payload.get("message", "Failed to load performance report."))
        st.json(report_payload)
        return

    report_data = report_payload.get("data", {})
    summary = report_data.get("ops_summary", {})
    trend = report_data.get("ops_trend", [])
    driver_trends = report_data.get("driver_trends", [])
    behavior_trends = report_data.get("behavior_trends", [])

    st.markdown(
        f"""
        <div class="dws-report-card">
            <div class="dws-report-row">
                <div>
                    <div class="dws-metric-label">OPS Summary</div>
                    <div class="dws-metric-value">{summary.get("overall_score", 0):.0f}/100</div>
                </div>
                <div style="text-align:right;">
                    <div class="dws-report-badge">{escape(summary.get("status", "Unknown"))}</div>
                    <div class="dws-metric-subtext" style="margin-top:14px;">
                        {summary.get("percentage_change", 0):+.1f}% vs selected period
                    </div>
                </div>
            </div>
            <div style="margin-top:18px; height:10px; background:#e9f0f7; border-radius:999px;">
                <div style="width:{summary.get('progress_value', 0)}%; height:10px; border-radius:999px; background:#10b7bc;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bar_html = ""
    for point in trend:
        height = max(18, int(point.get("value", 0) * 1.2))
        color = "#0d3470" if point.get("is_current") else "#10b7bc"
        if point.get("value", 0) == 0:
            color = "#edf3f9"
        bar_html += (
            f'<div class="dws-bar-item">'
            f'<div class="dws-bar" style="height:{height}px; background:{color};"></div>'
            f'<div class="dws-metric-label" style="margin-bottom:0;">{escape(point.get("label", ""))}</div>'
            f"</div>"
        )

    st.markdown(
        f"""
        <div class="dws-report-card">
            <div style="color:#20324f; font-size:1.75rem; font-weight:700;">OPS Trend</div>
            <div class="dws-bar-row">{bar_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Driver Trends")
    for driver in driver_trends:
        mini_bar_html = ""
        sparkline = driver.get("sparkline", [])
        for index, value in enumerate(sparkline[-4:]):
            height = max(14, int(value * 0.55))
            opacity = 0.55 + (index * 0.12)
            mini_bar_html += (
                f'<div class="dws-mini-bar" '
                f'style="height:{height}px; background:{driver.get("color", "#10b7bc")}; opacity:{opacity};"></div>'
            )

        delta_color = "#10b981" if str(driver.get("delta_label", "")).startswith("+") else "#ef4444"
        if driver.get("delta_label") == "Stable":
            delta_color = "#94a3b8"

        st.markdown(
            f"""
            <div class="dws-driver-card">
                <div class="dws-driver-header">
                    <div>
                        <div class="dws-driver-title">{escape(driver.get("label", ""))}</div>
                        <div style="color:{delta_color}; margin-top:6px; font-weight:700;">
                            {escape(str(driver.get("delta_label", "Stable")))}
                        </div>
                    </div>
                    <div class="dws-mini-bars">{mini_bar_html}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Behavior Trends")
    for behavior in behavior_trends:
        behavior_bar_html = ""
        bars = behavior.get("bars", [])
        colors = behavior.get("color_scale", [])
        for index, _ in enumerate(bars):
            color = colors[index] if index < len(colors) else "#cbd5e1"
            behavior_bar_html += f'<div class="dws-behavior-bar" style="background:{color};"></div>'

        st.markdown(
            f"""
            <div class="dws-report-card">
                <div class="dws-report-row">
                    <div class="dws-driver-title">{escape(behavior.get("label", ""))}</div>
                    <div style="color:#0d3470; font-size:0.95rem; font-weight:600;">
                        {escape(behavior.get("status", "Unknown"))}
                    </div>
                </div>
                <div class="dws-behavior-bars">{behavior_bar_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="dws-summary-panel">
            <div style="font-size:1.6rem; font-weight:700; margin-bottom:14px;">
                Performance Summary
            </div>
            <div style="font-size:1.08rem; line-height:1.8;">
                {escape(report_data.get("performance_summary", "No report summary available."))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_insight_screen() -> None:
    """Render a visual AI Insight screen using dashboard and insight APIs."""
    st.subheader("AI Insight View")
    if not st.session_state.access_token:
        st.info("Login first to load the AI Insight view.")
        return

    home_ok, home_payload = api_request("GET", "dashboard/home", require_auth=True)
    if not home_ok:
        st.error(home_payload.get("message", "Failed to load dashboard data."))
        st.json(home_payload)
        return

    insight_ok, insight_payload = api_request("GET", "insights/latest", require_auth=True)
    if not insight_ok:
        st.error(insight_payload.get("message", "Failed to load AI insight data."))
        st.json(insight_payload)
        return

    home_data = home_payload.get("data", {})
    insight_data = insight_payload.get("data", {})
    performance = home_data.get("overall_performance", {})
    dimensions = home_data.get("dimension_breakdown", [])
    recommendations = home_data.get("personalized_improvement_plan", [])
    progress = home_data.get("last_7_days_progress", [])
    dashboard_indicators = home_data.get("dashboard_indicators", [])
    burnout_alert = home_data.get("burnout_alert", {})

    overall_score = performance.get("overall_score", 0)
    percentage_change = performance.get("percentage_change", 0)
    score_label = performance.get("score_label", "Unknown")
    updated_text = f"Updated just now" if insight_ok else "Unavailable"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="dws-metric-card">
                <div class="dws-metric-label">Overall Score</div>
                <div class="dws-metric-value">{overall_score:.0f}</div>
                <div class="dws-metric-subtext">{percentage_change:+.1f}% change</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="dws-metric-card">
                <div class="dws-metric-label">Status</div>
                <div class="dws-metric-value" style="font-size: 1.9rem;">{escape(score_label)}</div>
                <div class="dws-metric-subtext">{escape(updated_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if dashboard_indicators:
        st.markdown("### Risk Indicators")
        indicator_columns = st.columns(len(dashboard_indicators))
        indicator_colors = {
            "success": "#27C86D",
            "steady": "#14B8C4",
            "warning": "#F5B800",
            "critical": "#FF5A5F",
        }
        for index, indicator in enumerate(dashboard_indicators):
            with indicator_columns[index]:
                color = indicator_colors.get(indicator.get("status"), "#14B8C4")
                st.markdown(
                    f"""
                    <div class="dws-metric-card" style="border-top:4px solid {color};">
                        <div class="dws-metric-label">{escape(indicator.get("label", ""))}</div>
                        <div class="dws-metric-value" style="font-size:1.6rem;">{escape(str(indicator.get("value", "")))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if burnout_alert:
        alert_active = burnout_alert.get("is_active", False)
        alert_color = "#FF5A5F" if alert_active else "#F5B800"
        triggered_signals = burnout_alert.get("triggered_signals", [])
        actions_preview = burnout_alert.get("recommended_actions_preview", [])
        signal_text = ", ".join(item.get("label", "") for item in triggered_signals) or "No risk signals triggered."
        actions_text = "<br>".join(escape(action) for action in actions_preview) or "No immediate action required."
        st.markdown(
            f"""
            <div class="dws-insight-box" style="border-left:6px solid {alert_color};">
                <div class="dws-metric-label">Burnout Alert</div>
                <div style="font-size:1.3rem; font-weight:700; color:{alert_color}; margin-bottom:8px;">
                    {escape(str(burnout_alert.get("level", "Low")))}
                </div>
                <div style="color:#183b63; line-height:1.7;">
                    {int(burnout_alert.get("signals_in_risk", 0))} of {int(burnout_alert.get("total_signals", 6))} signals in risk zone.<br>
                    Trend: {escape(str(burnout_alert.get("trend", "New")))}<br>
                    Drivers: {escape(signal_text)}<br><br>
                    <strong>Recommended Actions</strong><br>
                    {actions_text}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="dws-insight-box">
            <div class="dws-metric-label">AI Insight</div>
            <div style="color:#183b63; font-size:1.08rem; line-height:1.8;">
                {escape(insight_data.get("insight", "No insight available.")).replace(chr(10), "<br>")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Core Drivers")
    for dimension in dimensions:
        condition = dimension.get("condition", "Stable")
        color = STATUS_COLORS.get(condition, "#14B8C4")
        st.markdown(
            f"""
            <div class="dws-driver-card" style="border-left: 6px solid {color};">
                <div class="dws-driver-header">
                    <div>
                        <div class="dws-driver-title">
                            {escape(dimension.get("label", ""))}
                            <span class="dws-driver-key">({escape(dimension.get("key", ""))})</span>
                        </div>
                        <span class="dws-driver-tag" style="background:{color}20; color:{color};">
                            {escape(condition)}
                        </span>
                        <div style="color:#637b96; margin-top:10px; line-height:1.6;">
                            {escape(dimension.get("description", ""))}
                        </div>
                    </div>
                    <div class="dws-driver-score">{dimension.get("score", 0):.0f}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Recommended Actions")
    for index, recommendation in enumerate(recommendations):
        alt_class = " alt" if index == len(recommendations) - 1 else ""
        st.markdown(
            f"""
            <div class="dws-action-card{alt_class}">
                <div style="font-size:1.2rem; font-weight:700; margin-bottom:8px;">
                    {escape(recommendation.get("title", ""))}
                </div>
                <div style="font-size:1rem; line-height:1.6;">
                    {escape(recommendation.get("description", ""))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    trend_points = [point.get("score_value") for point in progress if point.get("score_value") is not None]
    if len(trend_points) >= 2:
        trend_text = (
            "Recent scores are improving."
            if trend_points[-1] >= trend_points[0]
            else "Recent scores suggest a mild decline in consistency."
        )
    else:
        trend_text = "Not enough progress data yet to establish a clear trend."

    st.markdown(
        f"""
        <div class="dws-insight-box">
            <div class="dws-metric-label">Trend Insight</div>
            <div style="color:#183b63; font-size:1.05rem; line-height:1.8;">
                {escape(trend_text)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_insights_section() -> None:
    """Render AI insight and assistant chat tools."""
    st.subheader("AI Insights & Chat")
    if not st.session_state.access_token:
        st.info("Login first to use the AI assistant.")
        return

    insight_tab, generate_tab, chat_tab = st.tabs(
        ["Latest Insight", "Generate Insight", "Assistant Chat"]
    )

    with insight_tab:
        if st.button("Fetch Latest Insight", use_container_width=True):
            ok, payload = api_request("GET", "insights/latest", require_auth=True)
            render_api_result(ok, payload, "Latest insight fetched.")

    with generate_tab:
        with st.form("generate_insight_form"):
            force_refresh = st.checkbox("Force Refresh", value=True)
            submitted = st.form_submit_button("Generate Insight", use_container_width=True)
        if submitted:
            ok, payload = api_request(
                "POST",
                "insights/generate",
                {"force_refresh": force_refresh},
                require_auth=True,
            )
            render_api_result(ok, payload, "Insight generated.")

    with chat_tab:
        for entry in st.session_state.chat_history:
            role_label = "You" if entry["role"] == "user" else "DWS AI"
            st.markdown(f"**{role_label}:** {entry['content']}")

        prompt_cols = st.columns(len(SUGGESTED_PROMPTS))
        for index, suggestion in enumerate(SUGGESTED_PROMPTS):
            with prompt_cols[index]:
                if st.button(suggestion, key=f"suggestion_{index}", use_container_width=True):
                    handle_chat_submission(suggestion)
                    st.rerun()

        with st.form("assistant_chat_form"):
            message = st.text_area("Ask the DWS AI Assistant", height=120)
            submitted = st.form_submit_button("Send Message", use_container_width=True)

        if submitted and message.strip():
            handle_chat_submission(message.strip())
            st.rerun()


def handle_chat_submission(message: str) -> None:
    """Send a message to the AI assistant and persist the response."""
    st.session_state.chat_history.append({"role": "user", "content": message})
    ok, payload = api_request(
        "POST",
        "insights/chat",
        {"message": message},
        require_auth=True,
    )
    if ok:
        reply = payload.get("data", {}).get("response", "")
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
    else:
        error_message = payload.get("message", "Assistant request failed.")
        st.session_state.chat_history.append({"role": "assistant", "content": error_message})


def render_endpoint_json(title: str, path: str) -> None:
    """Render a raw endpoint payload with a heading."""
    st.markdown(f"#### {title}")
    ok, payload = api_request("GET", path, require_auth=True)
    if ok:
        st.json(payload.get("data", {}))
    else:
        st.error(payload.get("message", f"Failed to load {title}."))
        st.json(payload)


def render_leader_workbench() -> None:
    """Render leader dashboard coverage for current backend routes."""
    st.subheader("Leader Dashboard Workbench")
    if not st.session_state.access_token:
        st.info("Login with a leader account first.")
        return

    scope_col1, scope_col2, scope_col3 = st.columns(3)
    with scope_col1:
        department = st.text_input("Leader Department", key="leader_department")
    with scope_col2:
        team = st.text_input("Leader Team", key="leader_team")
    with scope_col3:
        range_key = st.selectbox(
            "Leader Range",
            options=["7d", "30d", "90d", "custom"],
            index=1,
            key="leader_range_key",
        )

    scope_params = {"department": department, "team": team, "range": range_key}
    tabs = st.tabs(
        [
            "Dashboard",
            "Members",
            "Insights",
            "Report",
            "Alerts",
            "Burnout",
            "Settings",
            "Action History",
        ]
    )

    with tabs[0]:
        render_endpoint_json("Leader Dashboard", build_query_path("dashboard/leader", scope_params))

    with tabs[1]:
        members_path = build_query_path(
            "dashboard/leader/members",
            {
                "department": department,
                "team": team,
                "page": 1,
                "page_size": 10,
            },
        )
        ok, payload = api_request("GET", members_path, require_auth=True)
        if ok:
            data = payload.get("data", {})
            st.json(data)
            items = data.get("items", [])
            member_map: dict[str, str] = {}
            for item in items:
                profile_action = item.get("profile_action", {})
                member_id = profile_action.get("user_id") or item.get("user_id") or item.get("id")
                label = item.get("name") or member_id
                if member_id:
                    member_map[str(label)] = str(member_id)
            if member_map:
                selected_label = st.selectbox(
                    "Leader Member Detail",
                    options=list(member_map.keys()),
                    key="leader_member_detail_select",
                )
                detail_path = build_query_path(
                    f"dashboard/leader/members/{member_map[selected_label]}",
                    scope_params,
                )
                render_endpoint_json("Leader Member Detail", detail_path)
        else:
            st.error(payload.get("message", "Failed to load leader members."))
            st.json(payload)

    with tabs[2]:
        render_endpoint_json("Leader Insights", build_query_path("dashboard/leader/insights", scope_params))

    with tabs[3]:
        render_endpoint_json(
            "Leader Report",
            build_query_path("dashboard/leader/report", {**scope_params, "page": 1, "page_size": 10}),
        )

    with tabs[4]:
        render_endpoint_json("Leader Alerts", build_query_path("dashboard/leader/alerts", scope_params))

    with tabs[5]:
        sub1, sub2 = st.columns(2)
        with sub1:
            render_endpoint_json(
                "Leader Burnout Recommendations",
                build_query_path("dashboard/leader/burnout-recommendations", scope_params),
            )
        with sub2:
            render_endpoint_json(
                "Leader Burnout Details",
                build_query_path("dashboard/leader/burnout-details", scope_params),
            )

    with tabs[6]:
        settings_tabs = st.tabs(["Page", "Profile Update"])
        with settings_tabs[0]:
            render_endpoint_json("Leader Settings", build_query_path("dashboard/leader/settings", {"department": department, "team": team}))
        with settings_tabs[1]:
            with st.form("leader_settings_profile_form"):
                name = st.text_input("Leader Name")
                email = st.text_input("Leader Email")
                role = st.text_input("Leader Role")
                contact_number = st.text_input("Leader Contact Number")
                employee_id = st.text_input("Leader Employee ID")
                profile_image_url = st.text_input("Leader Profile Image URL")
                submitted = st.form_submit_button("Update Leader Profile", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "PATCH",
                    "dashboard/leader/settings/profile",
                    {
                        "name": name or None,
                        "email": email or None,
                        "role": role or None,
                        "contact_number": contact_number or None,
                        "employee_id": employee_id or None,
                        "profile_image_url": profile_image_url or None,
                    },
                    require_auth=True,
                )
                render_api_result(ok, payload, "Leader settings updated.")

    with tabs[7]:
        render_endpoint_json(
            "Leader Action History",
            build_query_path(
                "dashboard/leader/actions/history",
                {**scope_params, "outcome": "all", "page": 1, "page_size": 10},
            ),
        )


def render_superadmin_workbench() -> None:
    """Render superadmin dashboard coverage for current backend routes."""
    st.subheader("Superadmin Dashboard Workbench")
    if not st.session_state.access_token:
        st.info("Login with a superadmin account first.")
        return

    scope_col1, scope_col2, scope_col3, scope_col4 = st.columns(4)
    with scope_col1:
        company = st.text_input("Superadmin Company", key="superadmin_company")
    with scope_col2:
        department = st.text_input("Superadmin Department", key="superadmin_department")
    with scope_col3:
        team = st.text_input("Superadmin Team", key="superadmin_team")
    with scope_col4:
        range_key = st.selectbox(
            "Superadmin Range",
            options=["7d", "30d", "90d", "custom"],
            index=1,
            key="superadmin_range_key",
        )

    scope_params = {
        "company": company,
        "department": department,
        "team": team,
        "range": range_key,
    }

    tabs = st.tabs(
        [
            "Dashboard",
            "Organizations",
            "Users",
            "Insights",
            "Report",
            "Alerts",
            "Audit Logs",
            "Settings",
        ]
    )

    with tabs[0]:
        render_endpoint_json("Superadmin Dashboard", build_query_path("dashboard/superadmin", scope_params))

    with tabs[1]:
        orgs_path = build_query_path(
            "dashboard/superadmin/organizations",
            {"query": None, "risk_filter": "all", "sort_by": "performance", "page": 1, "page_size": 10},
        )
        ok, payload = api_request("GET", orgs_path, require_auth=True)
        if ok:
            data = payload.get("data", {})
            st.json(data)
            items = data.get("items", [])
            company_names = [item.get("company_name") for item in items if item.get("company_name")]
            if company_names:
                selected_company = st.selectbox(
                    "Organization Detail",
                    options=company_names,
                    key="superadmin_org_select",
                )
                render_endpoint_json(
                    "Company Dashboard",
                    build_query_path(
                        f"dashboard/superadmin/organizations/{selected_company}",
                        {"query": None, "risk_filter": "all", "sort_by": "performance", "page": 1, "page_size": 10},
                    ),
                )
        else:
            st.error(payload.get("message", "Failed to load organizations."))
            st.json(payload)

    with tabs[2]:
        users_path = build_query_path(
            "dashboard/superadmin/users",
            {"query": None, "status_filter": "all", "sort_by": "company", "page": 1, "page_size": 10},
        )
        ok, payload = api_request("GET", users_path, require_auth=True)
        if ok:
            data = payload.get("data", {})
            st.json(data)
            items = data.get("items", [])
            user_map: dict[str, str] = {}
            for item in items:
                user_id = item.get("id") or item.get("user_id")
                label = item.get("name") or user_id
                if user_id:
                    user_map[str(label)] = str(user_id)
            if user_map:
                selected_user = st.selectbox(
                    "Superadmin User Detail",
                    options=list(user_map.keys()),
                    key="superadmin_user_select",
                )
                detail_path = f"dashboard/superadmin/users/{user_map[selected_user]}"
                render_endpoint_json("Superadmin User Detail", detail_path)
        else:
            st.error(payload.get("message", "Failed to load users."))
            st.json(payload)

    with tabs[3]:
        render_endpoint_json("Superadmin Insights", build_query_path("dashboard/superadmin/insights", scope_params))

    with tabs[4]:
        render_endpoint_json(
            "Superadmin Report",
            build_query_path("dashboard/superadmin/report", {**scope_params, "page": 1, "page_size": 10}),
        )

    with tabs[5]:
        alerts_tabs = st.tabs(["Risk & Alerts", "Recommendations", "Details"])
        with alerts_tabs[0]:
            render_endpoint_json("Superadmin Alerts", build_query_path("dashboard/superadmin/alerts", scope_params))
        with alerts_tabs[1]:
            render_endpoint_json(
                "Superadmin Burnout Recommendations",
                build_query_path("dashboard/superadmin/burnout-recommendations", scope_params),
            )
        with alerts_tabs[2]:
            render_endpoint_json(
                "Superadmin Burnout Details",
                build_query_path("dashboard/superadmin/burnout-details", scope_params),
            )

    with tabs[6]:
        audit_path = build_query_path(
            "dashboard/superadmin/audit-logs",
            {
                "company": company,
                "time_filter": "today",
                "user_filter": "all",
                "status_filter": "all",
                "page": 1,
                "page_size": 10,
            },
        )
        ok, payload = api_request("GET", audit_path, require_auth=True)
        if ok:
            data = payload.get("data", {})
            st.json(data)
            items = data.get("items", [])
            log_map = {str(item.get("id")): str(item.get("id")) for item in items if item.get("id")}
            if log_map:
                selected_log = st.selectbox(
                    "Audit Log Detail",
                    options=list(log_map.keys()),
                    key="superadmin_audit_select",
                )
                render_endpoint_json(
                    "Superadmin Audit Detail",
                    build_query_path(
                        f"dashboard/superadmin/audit-logs/{selected_log}",
                        {"company": company},
                    ),
                )
        else:
            st.error(payload.get("message", "Failed to load audit logs."))
            st.json(payload)

    with tabs[7]:
        settings_tabs = st.tabs(
            [
                "Menu",
                "Profile",
                "Change Password",
                "Forgot Password",
                "Privacy Policy",
                "Terms",
                "About Us",
            ]
        )
        with settings_tabs[0]:
            render_endpoint_json("Superadmin Settings Menu", "dashboard/superadmin/settings")
        with settings_tabs[1]:
            render_endpoint_json("Superadmin Profile Page", "dashboard/superadmin/settings/profile")
            with st.form("superadmin_profile_update_form"):
                name = st.text_input("Superadmin Name")
                email = st.text_input("Superadmin Email")
                role = st.text_input("Superadmin Role")
                contact_number = st.text_input("Superadmin Contact Number")
                employee_id = st.text_input("Superadmin Employee ID")
                profile_image_url = st.text_input("Superadmin Profile Image URL")
                submitted = st.form_submit_button("Update Superadmin Profile", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "PATCH",
                    "dashboard/superadmin/settings/profile",
                    {
                        "name": name or None,
                        "email": email or None,
                        "role": role or None,
                        "contact_number": contact_number or None,
                        "employee_id": employee_id or None,
                        "profile_image_url": profile_image_url or None,
                    },
                    require_auth=True,
                )
                render_api_result(ok, payload, "Superadmin profile updated.")
        with settings_tabs[2]:
            render_endpoint_json(
                "Superadmin Change Password Page",
                "dashboard/superadmin/settings/change-password",
            )
            with st.form("superadmin_change_password_form"):
                current_password = st.text_input("Current Password", type="password", key="sa_current_password")
                new_password = st.text_input("New Password", type="password", key="sa_new_password")
                confirm_password = st.text_input("Confirm New Password", type="password", key="sa_confirm_password")
                submitted = st.form_submit_button("Change Password", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "POST",
                    "users/me/change-password",
                    {
                        "current_password": current_password,
                        "new_password": new_password,
                        "confirm_password": confirm_password,
                    },
                    require_auth=True,
                )
                render_api_result(ok, payload, "Superadmin password updated.")
        with settings_tabs[3]:
            sub_tabs = st.tabs(["Forgot Password Page", "Send OTP", "Verify Code", "Reset Password"])
            with sub_tabs[0]:
                render_endpoint_json(
                    "Superadmin Forgot Password Page",
                    "dashboard/superadmin/settings/forgot-password",
                )
                render_endpoint_json(
                    "Superadmin Verify Reset Code Page",
                    "dashboard/superadmin/settings/verify-reset-code",
                )
            with sub_tabs[1]:
                with st.form("superadmin_forgot_password_form"):
                    email = st.text_input("Superadmin Reset Email")
                    submitted = st.form_submit_button("Get OTP", use_container_width=True)
                if submitted:
                    ok, payload = api_request(
                        "POST",
                        "auth/superadmin-forgot-password",
                        {"email": email},
                    )
                    render_api_result(ok, payload, "Superadmin reset code sent.")
            with sub_tabs[2]:
                with st.form("superadmin_verify_reset_code_form"):
                    email = st.text_input("Email for Code Verification")
                    code = st.text_input("Verification Code", max_chars=4)
                    resend = st.checkbox("Resend instead of verify", value=False)
                    submitted = st.form_submit_button("Submit", use_container_width=True)
                if submitted:
                    path = (
                        "auth/superadmin-resend-reset-code"
                        if resend
                        else "auth/superadmin-verify-reset-code"
                    )
                    body = {"email": email} if resend else {"email": email, "code": code}
                    ok, payload = api_request("POST", path, body)
                    render_api_result(ok, payload, "Superadmin reset code flow completed.")
            with sub_tabs[3]:
                with st.form("superadmin_reset_password_form"):
                    email = st.text_input("Reset Email")
                    code = st.text_input("Reset Code", max_chars=4)
                    new_password = st.text_input("New Password", type="password", key="sa_reset_new_password")
                    confirm_password = st.text_input("Confirm Password", type="password", key="sa_reset_confirm_password")
                    submitted = st.form_submit_button("Reset Password", use_container_width=True)
                if submitted:
                    ok, payload = api_request(
                        "POST",
                        "auth/superadmin-reset-password",
                        {
                            "email": email,
                            "code": code,
                            "new_password": new_password,
                            "confirm_password": confirm_password,
                        },
                    )
                    render_api_result(ok, payload, "Superadmin password reset completed.")
        with settings_tabs[4]:
            render_endpoint_json(
                "Superadmin Privacy Policy Page",
                "dashboard/superadmin/settings/privacy-policy",
            )
            with st.form("superadmin_privacy_policy_form"):
                title = st.text_input("Privacy Policy Title", value="Privacy Policy")
                content = st.text_area("Privacy Policy Content", height=220)
                image_url = st.text_input("Privacy Policy Image URL")
                submitted = st.form_submit_button("Save Privacy Policy", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "PATCH",
                    "dashboard/superadmin/settings/privacy-policy",
                    {"title": title, "content": content, "image_url": image_url or None},
                    require_auth=True,
                )
                render_api_result(ok, payload, "Privacy policy updated.")
        with settings_tabs[5]:
            render_endpoint_json(
                "Superadmin Terms & Conditions Page",
                "dashboard/superadmin/settings/terms-and-conditions",
            )
            with st.form("superadmin_terms_form"):
                title = st.text_input("Terms Title", value="Terms & Conditions")
                content = st.text_area("Terms Content", height=220)
                image_url = st.text_input("Terms Image URL")
                submitted = st.form_submit_button("Save Terms", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "PATCH",
                    "dashboard/superadmin/settings/terms-and-conditions",
                    {"title": title, "content": content, "image_url": image_url or None},
                    require_auth=True,
                )
                render_api_result(ok, payload, "Terms updated.")
        with settings_tabs[6]:
            render_endpoint_json(
                "Superadmin About Us Page",
                "dashboard/superadmin/settings/about-us",
            )
            with st.form("superadmin_about_us_form"):
                title = st.text_input("About Us Title", value="About Us")
                content = st.text_area("About Us Content", height=220)
                image_url = st.text_input("About Us Image URL")
                submitted = st.form_submit_button("Save About Us", use_container_width=True)
            if submitted:
                ok, payload = api_request(
                    "PATCH",
                    "dashboard/superadmin/settings/about-us",
                    {"title": title, "content": content, "image_url": image_url or None},
                    require_auth=True,
                )
                render_api_result(ok, payload, "About us updated.")


def main() -> None:
    """Render the Streamlit backend test client."""
    run_app("all")


def run_app(mode: str = "all") -> None:
    """Render the Streamlit client in user, leader, superadmin, or full mode."""
    st.set_page_config(page_title="Dominion Backend Test Client", layout="wide")
    init_session_state()
    render_global_styles()
    render_sidebar()

    page_titles = {
        "user": "Dominion Wellness Solutions",
        "leader": "Leader Dashboard Client",
        "superadmin": "Superadmin Dashboard Client",
        "all": "Dominion Wellness Solutions",
    }
    page_captions = {
        "user": "Normal user portal and account flows.",
        "leader": "Leader dashboard and team analytics workbench.",
        "superadmin": "Superadmin dashboard and organization analytics workbench.",
        "all": "Full Streamlit test client for the FastAPI backend.",
    }

    st.title(page_titles.get(mode, page_titles["all"]))
    st.caption(page_captions.get(mode, page_captions["all"]))

    questions = fetch_data("questions", data_key="questions") or []
    daily_questions = fetch_data("daily-checkins/questions", data_key="questions") or []
    weekly_questions = fetch_data("weekly-checkins/questions", data_key="questions") or []
    monthly_questions = fetch_data("monthly-checkins/questions", data_key="questions") or []

    if mode in {"all", "user"}:
        render_auth_section()
        st.divider()
        render_account_section()
        st.divider()
        render_question_bank_section(questions)
        st.divider()
        render_onboarding_assessment_section(questions)
        st.divider()
        render_checkin_section(
            "Daily Check-In",
            daily_questions,
            None,
            "daily-checkins",
            "",
            "daily_checkin_form",
        )
        st.divider()
        render_checkin_section(
            "Weekly Check-In",
            weekly_questions,
            "weekly-checkins/status",
            "weekly-checkins",
            "Weekly check-in unlock hobe 7-day daily streak complete hole.",
            "weekly_checkin_form",
        )
        st.divider()
        render_checkin_section(
            "Monthly Check-In",
            monthly_questions,
            "monthly-checkins/status",
            "monthly-checkins",
            "Monthly check-in unlock hobe 30 completed daily check-in er por.",
            "monthly_checkin_form",
        )
        st.divider()
        render_scores_section()
        st.divider()
        render_dashboard_section()
        st.divider()
        render_report_screen()
        st.divider()
        render_ai_insight_screen()
        st.divider()
        render_insights_section()
        st.divider()
        render_account_screen()
        st.divider()
        render_edit_profile_screen()
        st.divider()
        render_account_settings_screen()
        st.divider()
        render_change_password_screen()
        st.divider()
        render_help_center_screen()
        st.divider()
        render_contact_support_screen()
        st.divider()
        render_legal_screen("Privacy Policy", "users/privacy-policy")
        st.divider()
        render_legal_screen("Terms of Condition", "users/terms-of-condition")
        st.divider()
        render_legal_screen("About Us", "users/about-us")

    if mode in {"all", "leader"}:
        if mode == "leader":
            render_auth_section()
        st.divider()
        render_leader_workbench()

    if mode in {"all", "superadmin"}:
        if mode == "superadmin":
            render_auth_section()
        st.divider()
        render_superadmin_workbench()


if __name__ == "__main__":
    main()
