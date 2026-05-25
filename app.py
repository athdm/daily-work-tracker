"""
Daily Work Tracker
==================

A small personal work tracker with:
- per-user workspace names
- per-user color themes
- per-user task logs
- persistent local storage until the CSV/JSON files are deleted

Run with Streamlit:
   python -m streamlit run app.py

Run tests:
   python app.py --run-tests

Data files created automatically:
- work_logs.csv: stores tasks
- user_profiles.json: stores each user's name and selected color theme
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import tempfile
import unittest
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# ------------------------------------------------------------
# Optional dependency
# ------------------------------------------------------------
try:
    import streamlit as st  # type: ignore
except ModuleNotFoundError:
    st = None


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
DATA_FILE = Path("work_logs.csv")
USER_PROFILES_FILE = Path("user_profiles.json")

STATUS_OPTIONS = ["Planned", "In Progress", "Done", "Blocked"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
ENERGY_OPTIONS = ["Low", "Medium", "High"]

DEFAULT_USER_NAME = "User"
DEFAULT_THEME_NAME = "Lavender"

THEME_PRESETS: Dict[str, Dict[str, object]] = {
    "Lavender": {
        "primary": "#8B5CF6",
        "primary_dark": "#6D28D9",
        "background_start": "#F5F3FF",
        "background_end": "#EDE9FE",
        "sidebar": "#EDE9FE",
        "card": "#FFFFFF",
        "border": "#DDD6FE",
        "text": "#4C1D95",
        "muted": "#7C3AED",
        "tag_text": "#2E1065",
        "status_colors": {
            "Planned": "#EDE9FE",
            "In Progress": "#C4B5FD",
            "Done": "#A78BFA",
            "Blocked": "#8B5CF6",
        },
        "priority_colors": {
            "Low": "#F3E8FF",
            "Medium": "#DDD6FE",
            "High": "#C084FC",
        },
    },
    "Rose": {
        "primary": "#EC4899",
        "primary_dark": "#BE185D",
        "background_start": "#FFF1F2",
        "background_end": "#FCE7F3",
        "sidebar": "#FCE7F3",
        "card": "#FFFFFF",
        "border": "#FBCFE8",
        "text": "#831843",
        "muted": "#BE185D",
        "tag_text": "#500724",
        "status_colors": {
            "Planned": "#FCE7F3",
            "In Progress": "#F9A8D4",
            "Done": "#F472B6",
            "Blocked": "#EC4899",
        },
        "priority_colors": {
            "Low": "#FFF1F2",
            "Medium": "#FBCFE8",
            "High": "#F472B6",
        },
    },
    "Sky": {
        "primary": "#0EA5E9",
        "primary_dark": "#0369A1",
        "background_start": "#F0F9FF",
        "background_end": "#E0F2FE",
        "sidebar": "#E0F2FE",
        "card": "#FFFFFF",
        "border": "#BAE6FD",
        "text": "#0C4A6E",
        "muted": "#0369A1",
        "tag_text": "#082F49",
        "status_colors": {
            "Planned": "#E0F2FE",
            "In Progress": "#7DD3FC",
            "Done": "#38BDF8",
            "Blocked": "#0EA5E9",
        },
        "priority_colors": {
            "Low": "#F0F9FF",
            "Medium": "#BAE6FD",
            "High": "#38BDF8",
        },
    },
    "Sage": {
        "primary": "#10B981",
        "primary_dark": "#047857",
        "background_start": "#F0FDF4",
        "background_end": "#DCFCE7",
        "sidebar": "#DCFCE7",
        "card": "#FFFFFF",
        "border": "#BBF7D0",
        "text": "#064E3B",
        "muted": "#047857",
        "tag_text": "#022C22",
        "status_colors": {
            "Planned": "#DCFCE7",
            "In Progress": "#86EFAC",
            "Done": "#4ADE80",
            "Blocked": "#10B981",
        },
        "priority_colors": {
            "Low": "#F0FDF4",
            "Medium": "#BBF7D0",
            "High": "#4ADE80",
        },
    },
    "Dark Purple": {
        "primary": "#A78BFA",
        "primary_dark": "#7C3AED",
        "background_start": "#111827",
        "background_end": "#2E1065",
        "sidebar": "#1F2937",
        "card": "#18181B",
        "border": "#6D28D9",
        "text": "#F5F3FF",
        "muted": "#C4B5FD",
        "tag_text": "#2E1065",
        "status_colors": {
            "Planned": "#DDD6FE",
            "In Progress": "#C4B5FD",
            "Done": "#A78BFA",
            "Blocked": "#8B5CF6",
        },
        "priority_colors": {
            "Low": "#EDE9FE",
            "Medium": "#C4B5FD",
            "High": "#A78BFA",
        },
    },
}

CSV_FIELDS = [
    "id",
    "user_name",
    "date",
    "project",
    "task",
    "category",
    "status",
    "priority",
    "time_spent_minutes",
    "energy",
    "notes",
    "created_at",
]


# ------------------------------------------------------------
# Domain model
# ------------------------------------------------------------
@dataclass
class WorkLog:
    id: int
    user_name: str
    date: str
    project: str
    task: str
    category: str
    status: str
    priority: str
    time_spent_minutes: int
    energy: str
    notes: str
    created_at: str


# ------------------------------------------------------------
# Validation and helpers
# ------------------------------------------------------------
def normalize_date(value: Optional[str | date]) -> str:
    """Return a YYYY-MM-DD date string."""
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    value = str(value).strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def validate_choice(value: str, valid_options: Iterable[str], field_name: str) -> str:
    value = str(value).strip()
    if value not in valid_options:
        allowed = ", ".join(valid_options)
        raise ValueError(f"Invalid {field_name}: {value}. Allowed values: {allowed}")
    return value


def validate_non_empty(value: str, field_name: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{field_name} cannot be empty.")
    return value


def normalize_user_name(value: str) -> str:
    value = value.strip()
    if not value:
        return DEFAULT_USER_NAME
    return value


def user_key(name: str) -> str:
    """Stable key used in the JSON settings file."""
    normalized = normalize_user_name(name).lower()
    normalized = re.sub(r"[^a-z0-9α-ωάέήίόύώϊϋΐΰ]+", "_", normalized, flags=re.IGNORECASE)
    normalized = normalized.strip("_")
    return normalized or "user"


def minutes_to_hours(minutes: int) -> str:
    minutes = max(0, int(minutes))
    hours = minutes // 60
    mins = minutes % 60
    if hours == 0:
        return f"{mins}m"
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def get_week_range(selected_date: str | date) -> Tuple[str, str]:
    parsed = datetime.strptime(normalize_date(selected_date), "%Y-%m-%d").date()
    start = parsed - timedelta(days=parsed.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def next_id(logs: List[WorkLog]) -> int:
    if not logs:
        return 1
    return max(log.id for log in logs) + 1


def render_tag(label: str, color: str, tag_text_color: str = "#2E1065") -> str:
    safe_label = html.escape(str(label))
    safe_color = html.escape(str(color))
    safe_tag_text_color = html.escape(str(tag_text_color))
    return f'<span class="tag" style="background:{safe_color}; color:{safe_tag_text_color};">{safe_label}</span>'


def format_workspace_title(name: str) -> str:
    cleaned_name = normalize_user_name(name)
    return f"{cleaned_name}'s Workspace"


def get_theme(theme_name: str) -> Dict[str, object]:
    return THEME_PRESETS.get(theme_name, THEME_PRESETS[DEFAULT_THEME_NAME])


# ------------------------------------------------------------
# User profile persistence
# ------------------------------------------------------------
def load_user_profiles(profiles_file: Path = USER_PROFILES_FILE) -> Dict[str, Dict[str, str]]:
    if not profiles_file.exists():
        return {}

    try:
        with profiles_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned: Dict[str, Dict[str, str]] = {}
    for key, profile in data.items():
        if not isinstance(profile, dict):
            continue
        name = normalize_user_name(str(profile.get("name", DEFAULT_USER_NAME)))
        theme_name = str(profile.get("theme", DEFAULT_THEME_NAME))
        if theme_name not in THEME_PRESETS:
            theme_name = DEFAULT_THEME_NAME
        cleaned[str(key)] = {"name": name, "theme": theme_name}

    return cleaned


def save_user_profiles(profiles: Dict[str, Dict[str, str]], profiles_file: Path = USER_PROFILES_FILE) -> None:
    profiles_file.parent.mkdir(parents=True, exist_ok=True)
    with profiles_file.open("w", encoding="utf-8") as file:
        json.dump(profiles, file, ensure_ascii=False, indent=2)


def get_or_create_profile(name: str, profiles_file: Path = USER_PROFILES_FILE) -> Dict[str, str]:
    profiles = load_user_profiles(profiles_file)
    cleaned_name = normalize_user_name(name)
    key = user_key(cleaned_name)

    if key not in profiles:
        profiles[key] = {"name": cleaned_name, "theme": DEFAULT_THEME_NAME}
        save_user_profiles(profiles, profiles_file)

    return profiles[key]


def update_user_profile(name: str, theme_name: str, profiles_file: Path = USER_PROFILES_FILE) -> Dict[str, str]:
    cleaned_name = normalize_user_name(name)
    theme_name = theme_name if theme_name in THEME_PRESETS else DEFAULT_THEME_NAME
    key = user_key(cleaned_name)

    profiles = load_user_profiles(profiles_file)
    profiles[key] = {"name": cleaned_name, "theme": theme_name}
    save_user_profiles(profiles, profiles_file)
    return profiles[key]


def delete_user_profile(name: str, profiles_file: Path = USER_PROFILES_FILE) -> bool:
    key = user_key(name)
    profiles = load_user_profiles(profiles_file)
    if key not in profiles:
        return False
    del profiles[key]
    save_user_profiles(profiles, profiles_file)
    return True


# ------------------------------------------------------------
# Persistence layer: standard library only
# ------------------------------------------------------------
def load_logs(data_file: Path = DATA_FILE) -> List[WorkLog]:
    if not data_file.exists():
        return []

    with data_file.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        logs: List[WorkLog] = []
        for row in reader:
            if not row:
                continue

            try:
                log = WorkLog(
                    id=int(row.get("id", 0) or 0),
                    user_name=normalize_user_name(row.get("user_name", DEFAULT_USER_NAME)),
                    date=normalize_date(row.get("date") or None),
                    project=row.get("project", "").strip(),
                    task=row.get("task", "").strip(),
                    category=(row.get("category") or "General").strip(),
                    status=validate_choice(row.get("status", "Planned"), STATUS_OPTIONS, "status"),
                    priority=validate_choice(row.get("priority", "Medium"), PRIORITY_OPTIONS, "priority"),
                    time_spent_minutes=max(0, int(float(row.get("time_spent_minutes", 0) or 0))),
                    energy=validate_choice(row.get("energy", "Medium"), ENERGY_OPTIONS, "energy"),
                    notes=(row.get("notes") or "").strip(),
                    created_at=(row.get("created_at") or "").strip(),
                )
                logs.append(log)
            except ValueError:
                # Skip malformed rows instead of breaking the app.
                continue

        return logs


def save_logs(logs: List[WorkLog], data_file: Path = DATA_FILE) -> None:
    data_file.parent.mkdir(parents=True, exist_ok=True)
    with data_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for log in logs:
            writer.writerow(asdict(log))


def add_log(
    *,
    user_name: str = DEFAULT_USER_NAME,
    log_date: str | date | None = None,
    project: str,
    task: str,
    category: str = "General",
    status: str = "In Progress",
    priority: str = "Medium",
    time_spent_minutes: int = 0,
    energy: str = "Medium",
    notes: str = "",
    data_file: Path = DATA_FILE,
) -> WorkLog:
    user_name = normalize_user_name(user_name)
    project = validate_non_empty(project, "Project")
    task = validate_non_empty(task, "Task")
    category = category.strip() or "General"
    status = validate_choice(status, STATUS_OPTIONS, "status")
    priority = validate_choice(priority, PRIORITY_OPTIONS, "priority")
    energy = validate_choice(energy, ENERGY_OPTIONS, "energy")
    time_spent_minutes = max(0, int(time_spent_minutes))

    logs = load_logs(data_file)
    log = WorkLog(
        id=next_id(logs),
        user_name=user_name,
        date=normalize_date(log_date),
        project=project,
        task=task,
        category=category,
        status=status,
        priority=priority,
        time_spent_minutes=time_spent_minutes,
        energy=energy,
        notes=notes.strip(),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    logs.append(log)
    save_logs(logs, data_file)
    return log


def update_log_status(task_id: int, new_status: str, data_file: Path = DATA_FILE) -> bool:
    new_status = validate_choice(new_status, STATUS_OPTIONS, "status")
    logs = load_logs(data_file)
    changed = False

    for log in logs:
        if log.id == int(task_id):
            log.status = new_status
            changed = True
            break

    if changed:
        save_logs(logs, data_file)
    return changed


def delete_log(task_id: int, data_file: Path = DATA_FILE) -> bool:
    logs = load_logs(data_file)
    original_count = len(logs)
    logs = [log for log in logs if log.id != int(task_id)]
    changed = len(logs) != original_count

    if changed:
        save_logs(logs, data_file)
    return changed


def delete_logs_for_user(user_name: str, data_file: Path = DATA_FILE) -> int:
    user_name = normalize_user_name(user_name)
    logs = load_logs(data_file)
    kept_logs = [log for log in logs if log.user_name != user_name]
    deleted_count = len(logs) - len(kept_logs)
    if deleted_count:
        save_logs(kept_logs, data_file)
    return deleted_count


def filter_logs(
    logs: List[WorkLog],
    *,
    user_name: Optional[str] = None,
    selected_day: Optional[str | date] = None,
    show_all_dates: bool = False,
    selected_projects: Optional[List[str]] = None,
    selected_statuses: Optional[List[str]] = None,
) -> List[WorkLog]:
    result = list(logs)

    if user_name is not None:
        normalized = normalize_user_name(user_name)
        result = [log for log in result if log.user_name == normalized]

    if selected_day is not None and not show_all_dates:
        day = normalize_date(selected_day)
        result = [log for log in result if log.date == day]

    if selected_projects:
        result = [log for log in result if log.project in selected_projects]

    if selected_statuses:
        result = [log for log in result if log.status in selected_statuses]

    return sorted(result, key=lambda item: (item.date, item.id), reverse=True)


def summarize(logs: List[WorkLog], *, selected_day: Optional[str | date] = None) -> Dict[str, object]:
    day = normalize_date(selected_day) if selected_day is not None else date.today().isoformat()
    week_start, week_end = get_week_range(day)

    today_logs = [log for log in logs if log.date == day]
    weekly_logs = [log for log in logs if week_start <= log.date <= week_end]

    time_by_project: Dict[str, int] = {}
    status_counts: Dict[str, int] = {status: 0 for status in STATUS_OPTIONS}

    for log in logs:
        status_counts[log.status] = status_counts.get(log.status, 0) + 1
        time_by_project[log.project] = time_by_project.get(log.project, 0) + log.time_spent_minutes

    return {
        "selected_day": day,
        "week_start": week_start,
        "week_end": week_end,
        "tasks_today": len(today_logs),
        "done_today": sum(1 for log in today_logs if log.status == "Done"),
        "blocked_today": sum(1 for log in today_logs if log.status == "Blocked"),
        "time_today_minutes": sum(log.time_spent_minutes for log in today_logs),
        "time_this_week_minutes": sum(log.time_spent_minutes for log in weekly_logs),
        "completed_this_week": sum(1 for log in weekly_logs if log.status == "Done"),
        "status_counts": status_counts,
        "time_by_project": dict(sorted(time_by_project.items(), key=lambda item: item[1], reverse=True)),
    }


def weekly_grouped_summary(logs: List[WorkLog], *, selected_day: Optional[str | date] = None) -> List[Dict[str, object]]:
    day = normalize_date(selected_day) if selected_day is not None else date.today().isoformat()
    week_start, week_end = get_week_range(day)
    weekly_logs = [log for log in logs if week_start <= log.date <= week_end]

    grouped: Dict[Tuple[str, str], Dict[str, object]] = {}
    for log in weekly_logs:
        key = (log.project, log.status)
        if key not in grouped:
            grouped[key] = {
                "project": log.project,
                "status": log.status,
                "tasks": 0,
                "minutes": 0,
                "time": "0m",
            }
        grouped[key]["tasks"] = int(grouped[key]["tasks"]) + 1
        grouped[key]["minutes"] = int(grouped[key]["minutes"]) + log.time_spent_minutes
        grouped[key]["time"] = minutes_to_hours(int(grouped[key]["minutes"]))

    return sorted(grouped.values(), key=lambda row: (str(row["project"]), str(row["status"])))


# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------
def require_streamlit() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit is not installed. Install it with: pip install streamlit\n"
            "Or use the CLI mode: python app.py --help"
        )


def inject_theme_css(theme: Dict[str, object]) -> None:
    primary = str(theme["primary"])
    primary_dark = str(theme["primary_dark"])
    background_start = str(theme["background_start"])
    background_end = str(theme["background_end"])
    sidebar = str(theme["sidebar"])
    card = str(theme["card"])
    border = str(theme["border"])
    text = str(theme["text"])
    muted = str(theme["muted"])

    st.markdown(
        f"""
        <style>
            .stApp {{
                background: linear-gradient(180deg, {background_start} 0%, {background_end} 100%);
            }}

            .main {{ background: transparent; }}

            .block-container {{
                padding-top: 2rem;
                padding-bottom: 2rem;
            }}

            .app-title {{
                font-size: 2.2rem;
                font-weight: 800;
                color: {text};
                margin-bottom: 0.2rem;
            }}

            .app-subtitle {{
                font-size: 1rem;
                color: {muted};
                margin-bottom: 1.5rem;
            }}

            .task-card {{
                background: {card};
                padding: 1rem 1.1rem;
                border-radius: 16px;
                margin-bottom: 0.8rem;
                box-shadow: 0 6px 18px rgba(79, 70, 229, 0.12);
                border: 1px solid {border};
            }}

            .tag {{
                display: inline-block;
                padding: 0.25rem 0.55rem;
                border-radius: 999px;
                font-size: 0.78rem;
                font-weight: 700;
                margin-right: 0.35rem;
            }}

            .small-muted {{
                color: {muted};
                font-size: 0.88rem;
            }}

            .section-title {{
                font-size: 1.25rem;
                font-weight: 800;
                color: {text};
                margin-top: 1rem;
                margin-bottom: 0.8rem;
            }}

            section[data-testid="stSidebar"] {{ background: {sidebar}; }}

            div[data-baseweb="input"],
            div[data-baseweb="select"],
            textarea,
            input {{
                border-radius: 12px !important;
            }}

            .stButton > button {{
                background: {primary} !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
            }}

            .stButton > button:hover {{
                background: {primary_dark} !important;
                color: white !important;
            }}

            .stDownloadButton > button {{
                background: {primary} !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
            }}

            [data-testid="stMetric"] {{
                background: {card};
                border: 1px solid {border};
                border-radius: 16px;
                padding: 1rem;
                box-shadow: 0 6px 18px rgba(79, 70, 229, 0.10);
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_streamlit_app() -> None:
    require_streamlit()

    st.set_page_config(
        page_title="Daily Work Tracker",
        page_icon="🗓️",
        layout="wide",
    )

    profiles = load_user_profiles(USER_PROFILES_FILE)
    profile_names = sorted({profile["name"] for profile in profiles.values()})
    if DEFAULT_USER_NAME not in profile_names:
        profile_names.insert(0, DEFAULT_USER_NAME)

    st.sidebar.title("Workspace")
    selected_existing_user = st.sidebar.selectbox(
        "Choose existing user",
        profile_names,
        index=0,
    )
    user_name_input = st.sidebar.text_input(
        "Your name",
        value="" if selected_existing_user == DEFAULT_USER_NAME else selected_existing_user,
        placeholder="Type your name, e.g. Maria",
    )

    if not user_name_input.strip():
        inject_theme_css(get_theme(DEFAULT_THEME_NAME))
        st.markdown('<div class="app-title">🗓️ Personal Workspace</div>', unsafe_allow_html=True)
        st.info("Add your name in the sidebar to create your personal workspace.")
        return

    user_name = normalize_user_name(user_name_input)

    current_profile = get_or_create_profile(user_name, USER_PROFILES_FILE)
    saved_theme_name = current_profile.get("theme", DEFAULT_THEME_NAME)
    if saved_theme_name not in THEME_PRESETS:
        saved_theme_name = DEFAULT_THEME_NAME

    theme_names = list(THEME_PRESETS.keys())
    selected_theme_name = st.sidebar.selectbox(
        "Workspace colour theme",
        theme_names,
        index=theme_names.index(saved_theme_name),
    )

    if (
        current_profile.get("name") != user_name
        or current_profile.get("theme") != selected_theme_name
    ):
        update_user_profile(user_name, selected_theme_name, USER_PROFILES_FILE)
        st.rerun()

    theme = get_theme(selected_theme_name)
    status_colors = theme["status_colors"]
    priority_colors = theme["priority_colors"]
    tag_text_color = str(theme["tag_text"])

    inject_theme_css(theme)

    st.sidebar.caption("Your name and colour theme are saved locally until you delete/reset them.")

    with st.sidebar.expander("Danger zone"):
        st.caption("This removes the selected user's saved name/theme and their task logs.")
        confirm_delete = st.checkbox("I understand this will delete this user's data")
        if st.button("Delete this user", disabled=not confirm_delete):
            delete_user_profile(user_name, USER_PROFILES_FILE)
            delete_logs_for_user(user_name, DATA_FILE)
            st.success("User deleted.")
            st.rerun()

    workspace_title = format_workspace_title(user_name)

    st.markdown(f'<div class="app-title">🗓️ {html.escape(workspace_title)}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-subtitle">Personal dashboard for daily tasks, progress, time spent and blockers.</div>',
        unsafe_allow_html=True,
    )

    all_logs = load_logs(DATA_FILE)
    user_logs = [log for log in all_logs if log.user_name == user_name]

    st.sidebar.title("Filters")
    selected_day = st.sidebar.date_input("Selected day", value=date.today())
    selected_day_str = normalize_date(selected_day)
    week_start, week_end = get_week_range(selected_day_str)

    project_options = sorted({log.project for log in user_logs})
    selected_projects = st.sidebar.multiselect("Projects", project_options, default=project_options)
    selected_statuses = st.sidebar.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS)
    show_all_dates = st.sidebar.checkbox("Show all dates", value=False)

    with st.expander("➕ Add a new task", expanded=True):
        with st.form("add_task_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                log_date = st.date_input("Date", value=date.today())
                project = st.text_input("Project / Client", placeholder="e.g. Internal, Client A, Admin")
                category = st.text_input("Category", placeholder="e.g. Research, Reporting, Content, Admin")

            with col2:
                status = st.selectbox("Status", STATUS_OPTIONS, index=1)
                priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=1)
                energy = st.selectbox("Energy", ENERGY_OPTIONS, index=1)

            with col3:
                hours = st.number_input("Hours", min_value=0, max_value=24, value=0, step=1)
                minutes = st.number_input("Minutes", min_value=0, max_value=59, value=30, step=5)

            task = st.text_area("Task description", placeholder="What did you work on?")
            notes = st.text_area("Notes / blockers", placeholder="Optional notes, blockers, links, next steps...")

            submitted = st.form_submit_button("Save task")
            if submitted:
                try:
                    add_log(
                        user_name=user_name,
                        log_date=log_date,
                        project=project,
                        task=task,
                        category=category or "General",
                        status=status,
                        priority=priority,
                        time_spent_minutes=int(hours * 60 + minutes),
                        energy=energy,
                        notes=notes,
                        data_file=DATA_FILE,
                    )
                    st.success("Task saved successfully.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    metrics = summarize(user_logs, selected_day=selected_day_str)

    st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tasks today", metrics["tasks_today"])
    m2.metric("Done today", metrics["done_today"])
    m3.metric("Blocked today", metrics["blocked_today"])
    m4.metric("Time today", minutes_to_hours(int(metrics["time_today_minutes"])))

    m5, m6 = st.columns(2)
    m5.metric("Time this week", minutes_to_hours(int(metrics["time_this_week_minutes"])))
    m6.metric("Completed this week", metrics["completed_this_week"])

    if user_logs:
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown('<div class="section-title">Status breakdown</div>', unsafe_allow_html=True)
            st.bar_chart(metrics["status_counts"])
        with chart_col2:
            st.markdown('<div class="section-title">Time by project</div>', unsafe_allow_html=True)
            st.bar_chart(metrics["time_by_project"])
    else:
        st.info("No tasks yet. Add your first task from the form above.")

    filtered_logs = filter_logs(
        user_logs,
        user_name=user_name,
        selected_day=selected_day_str,
        show_all_dates=show_all_dates,
        selected_projects=selected_projects,
        selected_statuses=selected_statuses,
    )

    st.markdown('<div class="section-title">Task list</div>', unsafe_allow_html=True)
    if not filtered_logs:
        st.warning("No tasks match the current filters.")
    else:
        for log in filtered_logs:
            status_color = dict(status_colors).get(log.status, "#E5E7EB")
            priority_color = dict(priority_colors).get(log.priority, "#E5E7EB")

            st.markdown(
                f"""
                <div class="task-card">
                    <div style="font-size:1.05rem; font-weight:800; color:{html.escape(str(theme['text']))};">
                        {html.escape(log.task)}
                    </div>
                    <div class="small-muted">
                        {html.escape(log.date)} · {html.escape(log.project)} · {html.escape(log.category)}
                    </div>
                    <div style="margin-top:0.55rem;">
                        {render_tag(log.status, status_color, tag_text_color)}
                        {render_tag(log.priority, priority_color, tag_text_color)}
                        {render_tag(log.energy + ' energy', str(theme['border']), tag_text_color)}
                        {render_tag(minutes_to_hours(log.time_spent_minutes), str(theme['background_start']), tag_text_color)}
                    </div>
                    <div style="margin-top:0.7rem; color:{html.escape(str(theme['muted']))};">
                        {html.escape(log.notes)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            action_col1, action_col2, action_col3, action_col4, _ = st.columns([1, 1, 1, 1, 2])
            with action_col1:
                if st.button("Done", key=f"done_{log.id}"):
                    update_log_status(log.id, "Done", DATA_FILE)
                    st.rerun()
            with action_col2:
                if st.button("Progress", key=f"progress_{log.id}"):
                    update_log_status(log.id, "In Progress", DATA_FILE)
                    st.rerun()
            with action_col3:
                if st.button("Blocked", key=f"blocked_{log.id}"):
                    update_log_status(log.id, "Blocked", DATA_FILE)
                    st.rerun()
            with action_col4:
                if st.button("Delete", key=f"delete_{log.id}"):
                    delete_log(log.id, DATA_FILE)
                    st.rerun()

    st.markdown('<div class="section-title">Weekly summary</div>', unsafe_allow_html=True)
    st.caption(f"Week: {week_start} to {week_end}")
    grouped_summary = weekly_grouped_summary(user_logs, selected_day=selected_day_str)
    if grouped_summary:
        st.dataframe(grouped_summary, use_container_width=True)
    else:
        st.info("No entries for this week yet.")

    st.markdown('<div class="section-title">Export data</div>', unsafe_allow_html=True)
    if user_logs:
        temp_path = Path("daily_work_tracker_export.csv")
        save_logs(user_logs, temp_path)
        try:
            csv_bytes = temp_path.read_bytes()
        finally:
            temp_path.unlink(missing_ok=True)

        st.download_button(
            label="Download my CSV",
            data=csv_bytes,
            file_name=f"{user_key(user_name)}_daily_work_tracker_export.csv",
            mime="text/csv",
        )
    else:
        st.caption("Add at least one task to enable export.")

    st.markdown("---")
    st.caption("Personal tracker · User profiles are stored in user_profiles.json · Task logs are stored in work_logs.csv")


# ------------------------------------------------------------
# CLI mode
# ------------------------------------------------------------
def print_logs(logs: List[WorkLog]) -> None:
    if not logs:
        print("No logs found.")
        return

    for log in logs:
        print(
            f"#{log.id} | {log.user_name} | {log.date} | {log.project} | {log.status} | "
            f"{minutes_to_hours(log.time_spent_minutes)} | {log.task}"
        )
        if log.notes:
            print(f"   Notes: {log.notes}")


def print_summary(logs: List[WorkLog]) -> None:
    metrics = summarize(logs)
    print("Daily Work Tracker Summary")
    print("--------------------------")
    print(f"Selected day: {metrics['selected_day']}")
    print(f"Tasks today: {metrics['tasks_today']}")
    print(f"Done today: {metrics['done_today']}")
    print(f"Blocked today: {metrics['blocked_today']}")
    print(f"Time today: {minutes_to_hours(int(metrics['time_today_minutes']))}")
    print(f"Week: {metrics['week_start']} to {metrics['week_end']}")
    print(f"Time this week: {minutes_to_hours(int(metrics['time_this_week_minutes']))}")
    print(f"Completed this week: {metrics['completed_this_week']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily Work Tracker")
    parser.add_argument("--data-file", default=str(DATA_FILE), help="Path to CSV data file.")

    action = parser.add_mutually_exclusive_group()
    action.add_argument("--add", action="store_true", help="Add a task from CLI.")
    action.add_argument("--list", action="store_true", help="List saved tasks.")
    action.add_argument("--summary", action="store_true", help="Show summary.")
    action.add_argument("--run-tests", action="store_true", help="Run built-in tests.")

    parser.add_argument("--user", default=DEFAULT_USER_NAME, help="User name.")
    parser.add_argument("--date", default=None, help="Task date in YYYY-MM-DD format.")
    parser.add_argument("--project", default="", help="Project or client name.")
    parser.add_argument("--task", default="", help="Task description.")
    parser.add_argument("--category", default="General", help="Task category.")
    parser.add_argument("--status", default="In Progress", choices=STATUS_OPTIONS, help="Task status.")
    parser.add_argument("--priority", default="Medium", choices=PRIORITY_OPTIONS, help="Task priority.")
    parser.add_argument("--minutes", type=int, default=0, help="Time spent in minutes.")
    parser.add_argument("--energy", default="Medium", choices=ENERGY_OPTIONS, help="Energy level.")
    parser.add_argument("--notes", default="", help="Optional notes.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data_file = Path(args.data_file)

    if args.run_tests:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkTrackerTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.add:
        try:
            log = add_log(
                user_name=args.user,
                log_date=args.date,
                project=args.project,
                task=args.task,
                category=args.category,
                status=args.status,
                priority=args.priority,
                time_spent_minutes=args.minutes,
                energy=args.energy,
                notes=args.notes,
                data_file=data_file,
            )
            print(f"Saved task #{log.id}.")
            return 0
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    if args.list:
        print_logs(load_logs(data_file))
        return 0

    if args.summary:
        print_summary(load_logs(data_file))
        return 0

    if st is not None:
        run_streamlit_app()
        return 0

    parser.print_help()
    print("\nStreamlit is not installed, so the visual UI cannot run in this environment.")
    print("Install it locally with: pip install streamlit")
    return 0


# ------------------------------------------------------------
# Tests
# ------------------------------------------------------------
class WorkTrackerTests(unittest.TestCase):
    def test_add_and_load_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            created = add_log(
                user_name="Maria",
                log_date="2026-05-25",
                project="Internal",
                task="Prepare report",
                category="Reporting",
                status="Done",
                priority="High",
                time_spent_minutes=90,
                energy="Medium",
                notes="Weekly summary",
                data_file=path,
            )

            self.assertEqual(created.id, 1)
            loaded = load_logs(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].user_name, "Maria")
            self.assertEqual(loaded[0].project, "Internal")
            self.assertEqual(loaded[0].task, "Prepare report")
            self.assertEqual(loaded[0].time_spent_minutes, 90)

    def test_update_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            add_log(project="A", task="Task A", data_file=path)
            changed = update_log_status(1, "Blocked", path)

            self.assertTrue(changed)
            self.assertEqual(load_logs(path)[0].status, "Blocked")

    def test_delete_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            add_log(project="A", task="Task A", data_file=path)
            add_log(project="B", task="Task B", data_file=path)

            changed = delete_log(1, path)
            logs = load_logs(path)

            self.assertTrue(changed)
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].id, 2)

    def test_delete_logs_for_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            add_log(user_name="Maria", project="A", task="Task A", data_file=path)
            add_log(user_name="Eleni", project="B", task="Task B", data_file=path)

            deleted_count = delete_logs_for_user("Maria", path)
            logs = load_logs(path)

            self.assertEqual(deleted_count, 1)
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].user_name, "Eleni")

    def test_filter_logs_by_user(self) -> None:
        logs = [
            WorkLog(1, "Maria", "2026-05-25", "A", "Task A", "General", "Done", "Medium", 30, "Medium", "", "now"),
            WorkLog(2, "Eleni", "2026-05-25", "B", "Task B", "General", "Done", "Medium", 30, "Medium", "", "now"),
        ]
        filtered = filter_logs(logs, user_name="Maria", selected_day="2026-05-25")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].user_name, "Maria")

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            add_log(
                log_date="2026-05-25",
                project="Internal",
                task="Task A",
                status="Done",
                time_spent_minutes=30,
                data_file=path,
            )
            add_log(
                log_date="2026-05-25",
                project="Internal",
                task="Task B",
                status="Blocked",
                time_spent_minutes=60,
                data_file=path,
            )

            metrics = summarize(load_logs(path), selected_day="2026-05-25")

            self.assertEqual(metrics["tasks_today"], 2)
            self.assertEqual(metrics["done_today"], 1)
            self.assertEqual(metrics["blocked_today"], 1)
            self.assertEqual(metrics["time_today_minutes"], 90)

    def test_invalid_empty_project_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            with self.assertRaises(ValueError):
                add_log(project="", task="Valid task", data_file=path)

    def test_invalid_date_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "logs.csv"
            with self.assertRaises(ValueError):
                add_log(log_date="25/05/2026", project="A", task="Task A", data_file=path)

    def test_minutes_to_hours(self) -> None:
        self.assertEqual(minutes_to_hours(0), "0m")
        self.assertEqual(minutes_to_hours(45), "45m")
        self.assertEqual(minutes_to_hours(60), "1h")
        self.assertEqual(minutes_to_hours(95), "1h 35m")

    def test_format_workspace_title(self) -> None:
        self.assertEqual(format_workspace_title("Maria"), "Maria's Workspace")
        self.assertEqual(format_workspace_title("  Eleni  "), "Eleni's Workspace")
        self.assertEqual(format_workspace_title(""), "User's Workspace")

    def test_save_and_load_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "user_profiles.json"
            update_user_profile("Maria", "Rose", path)
            profile = get_or_create_profile("Maria", path)
            self.assertEqual(profile["name"], "Maria")
            self.assertEqual(profile["theme"], "Rose")

    def test_delete_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "user_profiles.json"
            update_user_profile("Maria", "Lavender", path)
            deleted = delete_user_profile("Maria", path)
            self.assertTrue(deleted)
            self.assertEqual(load_user_profiles(path), {})

    def test_theme_preset_exists(self) -> None:
        self.assertIn(DEFAULT_THEME_NAME, THEME_PRESETS)
        self.assertIn("status_colors", THEME_PRESETS[DEFAULT_THEME_NAME])
        self.assertIn("priority_colors", THEME_PRESETS[DEFAULT_THEME_NAME])


if __name__ == "__main__":
    raise SystemExit(main())
