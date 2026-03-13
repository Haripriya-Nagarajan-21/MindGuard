from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pickle
import numpy as np
import json
import random
import os
import re
import secrets
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

import storage_mysql
import chatbot_llm

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mindguard_dev_secret")

USERS_DB_PATH = os.path.join("data", "users.json")
ASSESSMENTS_DB_PATH = os.path.join("data", "assessments.json")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
STRESS_LEVEL_MAP = {
    "Low Stress": 0,
    "Medium Stress": 1,
    "High Stress": 2,
}
LEVEL_CLASS_MAP = {
    0: "low",
    1: "medium",
    2: "high",
}


def is_mysql_storage_enabled():
    mode = os.environ.get("MINDGUARD_STORAGE", "").strip().lower()
    if mode == "mysql":
        return True
    if mode == "json":
        return False

    # Auto-detect: enable MySQL when basic config is present.
    return storage_mysql.is_configured()


def default_signup_form():
    return {
        "role": "user",
        "full_name": "",
        "email": "",
        "agree": False,
    }


def is_safe_next_path(path):
    return isinstance(path, str) and path.startswith("/")


def build_signup_response(error=None, form_data=None):
    return render_template(
        "signup.html",
        error=error,
        form_data=form_data or default_signup_form(),
    )


def build_google_oauth_error_redirect(message):
    return redirect(url_for("signup", error=message))


def load_users():
    if is_mysql_storage_enabled():
        return storage_mysql.load_users()

    if not os.path.exists(USERS_DB_PATH):
        return {}

    try:
        with open(USERS_DB_PATH, "r", encoding="utf-8") as users_file:
            users = json.load(users_file)
    except (json.JSONDecodeError, OSError):
        return {}

    return users if isinstance(users, dict) else {}


def save_users(users):
    if is_mysql_storage_enabled():
        storage_mysql.save_users(users)
        return

    os.makedirs(os.path.dirname(USERS_DB_PATH), exist_ok=True)
    with open(USERS_DB_PATH, "w", encoding="utf-8") as users_file:
        json.dump(users, users_file, indent=2)


def load_assessments():
    if not os.path.exists(ASSESSMENTS_DB_PATH):
        return {}

    try:
        with open(ASSESSMENTS_DB_PATH, "r", encoding="utf-8") as assessments_file:
            data = json.load(assessments_file)
    except (json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def save_assessments(data):
    os.makedirs(os.path.dirname(ASSESSMENTS_DB_PATH), exist_ok=True)
    with open(ASSESSMENTS_DB_PATH, "w", encoding="utf-8") as assessments_file:
        json.dump(data, assessments_file, indent=2)


def clamp(value, low, high):
    return max(low, min(high, value))


def parse_timestamp_date(timestamp):
    if not timestamp:
        return None

    try:
        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def calculate_wellness_score(sleep_hours, work_study_hours, screen_time, physical_activity, mood):
    sleep_score = 100 - abs(sleep_hours - 8.0) * 15
    workload_score = 100 - max(0, work_study_hours - 8.0) * 12
    screen_score = 100 - max(0, screen_time - 4.0) * 11
    activity_score = min(100, physical_activity * 70)
    mood_score = mood * 10

    weighted = (
        clamp(sleep_score, 0, 100) * 0.26
        + clamp(workload_score, 0, 100) * 0.16
        + clamp(screen_score, 0, 100) * 0.17
        + clamp(activity_score, 0, 100) * 0.17
        + clamp(mood_score, 0, 100) * 0.24
    )
    return int(round(clamp(weighted, 0, 100)))


def detect_stress_drivers(sleep_hours, work_study_hours, screen_time, physical_activity, mood):
    drivers = []

    if sleep_hours < 7:
        gap = 7 - sleep_hours
        drivers.append(
            {
                "key": "sleep",
                "label": "Low Sleep Recovery",
                "impact": int(round(gap * 18)),
                "why": "Sleep below 7 hours tends to increase stress reactivity.",
                "action": "Add a fixed sleep start time tonight and avoid screens 30 minutes before bed.",
            }
        )

    if work_study_hours > 8:
        excess = work_study_hours - 8
        drivers.append(
            {
                "key": "workload",
                "label": "Workload Overload",
                "impact": int(round(excess * 14)),
                "why": "Long continuous workload can amplify cognitive fatigue.",
                "action": "Use focused 25-minute blocks with 5-minute breaks.",
            }
        )

    if screen_time > 5:
        excess = screen_time - 5
        drivers.append(
            {
                "key": "screen",
                "label": "High Screen Exposure",
                "impact": int(round(excess * 12)),
                "why": "Long screen exposure can reduce mental recovery quality.",
                "action": "Take a 5-minute eye/body break every hour.",
            }
        )

    if physical_activity < 1:
        gap = 1 - physical_activity
        drivers.append(
            {
                "key": "activity",
                "label": "Low Physical Activity",
                "impact": int(round(gap * 22)),
                "why": "Low movement is linked with lower mood regulation.",
                "action": "Do at least 15-20 minutes of light walk or stretching.",
            }
        )

    if mood < 6:
        gap = 6 - mood
        drivers.append(
            {
                "key": "mood",
                "label": "Mood Depletion",
                "impact": int(round(gap * 13)),
                "why": "Lower mood can reduce stress resilience across the day.",
                "action": "Use one grounding exercise and message someone you trust.",
            }
        )

    if not drivers:
        drivers.append(
            {
                "key": "balanced",
                "label": "Balanced Routine",
                "impact": 10,
                "why": "Your inputs look fairly balanced right now.",
                "action": "Keep this routine stable for the next few days.",
            }
        )

    for driver in drivers:
        impact = driver["impact"]
        if impact >= 30:
            driver["severity"] = "High"
            driver["severity_class"] = "sev-high"
        elif impact >= 16:
            driver["severity"] = "Medium"
            driver["severity_class"] = "sev-medium"
        else:
            driver["severity"] = "Low"
            driver["severity_class"] = "sev-low"

    drivers.sort(key=lambda item: item["impact"], reverse=True)
    return drivers[:3]


def build_micro_challenge(driver_key):
    challenges = {
        "sleep": {
            "title": "Tonight Sleep Reset",
            "steps": [
                "Set a lights-off alarm for your target bedtime.",
                "No social media in the last 30 minutes before sleep.",
                "Take 8 slow breaths once you lie down.",
            ],
        },
        "workload": {
            "title": "Workload Decompression",
            "steps": [
                "Write the top 3 tasks only for today.",
                "Start with the smallest task to gain momentum.",
                "Take a 5-minute reset after each focus block.",
            ],
        },
        "screen": {
            "title": "Screen Detox Sprint",
            "steps": [
                "Enable one no-notification block for 45 minutes.",
                "Look away from screen every 20 minutes.",
                "End the day with 20 offline minutes before bed.",
            ],
        },
        "activity": {
            "title": "Movement Booster",
            "steps": [
                "Do a 2-minute stretch right now.",
                "Walk for at least 15 minutes today.",
                "Stand up and move once every hour.",
            ],
        },
        "mood": {
            "title": "Mood Lift Protocol",
            "steps": [
                "Do one grounding prompt from the result page.",
                "Send one supportive message to a friend/family member.",
                "Write one thing that went right today.",
            ],
        },
        "balanced": {
            "title": "Consistency Challenge",
            "steps": [
                "Repeat today’s healthy routine tomorrow.",
                "Schedule one short recovery break in advance.",
                "Log one more check-in tomorrow to keep momentum.",
            ],
        },
    }

    return challenges.get(driver_key, challenges["balanced"])


def append_user_assessment(email, entry):
    if is_mysql_storage_enabled():
        return storage_mysql.append_user_assessment(email, entry)

    all_assessments = load_assessments()
    user_entries = all_assessments.get(email, [])
    if not isinstance(user_entries, list):
        user_entries = []

    user_entries.append(entry)
    all_assessments[email] = user_entries[-180:]
    save_assessments(all_assessments)
    return all_assessments[email]


def get_user_assessments(email):
    if is_mysql_storage_enabled():
        return storage_mysql.get_user_assessments(email)

    all_assessments = load_assessments()
    user_entries = all_assessments.get(email, [])
    return user_entries if isinstance(user_entries, list) else []


def build_focus_tip(entries):
    if not entries:
        return "Complete one check-in to unlock personalized focus tips."

    key_counts = {}
    for entry in entries[-10:]:
        for key in entry.get("driver_keys", []):
            key_counts[key] = key_counts.get(key, 0) + 1

    if not key_counts:
        return "Keep your routine consistent and repeat your assessment tomorrow."

    primary = max(key_counts, key=key_counts.get)
    tip_map = {
        "sleep": "Focus on sleep timing first. Even +45 minutes can reduce tomorrow's stress.",
        "workload": "Reduce overload by planning only 3 must-do tasks per day.",
        "screen": "Break long screen sessions with regular 5-minute recovery breaks.",
        "activity": "Movement is your strongest lever now. Add a short walk today.",
        "mood": "Support mood early with grounding and one trusted social connection.",
        "balanced": "Your pattern is stable. Keep consistency for the next 3 days.",
    }
    return tip_map.get(primary, tip_map["balanced"])


def build_progress_summary(entries):
    if not entries:
        return {
            "total_checks": 0,
            "streak_days": 0,
            "trend_text": "Need more check-ins",
            "trend_class": "trend-stable",
            "avg_wellness": 0,
            "bars": [],
            "last_result": "No data yet",
        }

    recent = entries[-7:]
    bars = []
    for entry in recent:
        level = int(entry.get("stress_level", 1))
        date_value = parse_timestamp_date(entry.get("timestamp"))
        bars.append(
            {
                "height": 32 + (level * 18),
                "label": date_value.strftime("%d %b") if date_value else "Check",
                "level_text": entry.get("prediction", "Medium Stress"),
                "level_class": f"bar-{LEVEL_CLASS_MAP.get(level, 'medium')}",
            }
        )

    level_values = [int(item.get("stress_level", 1)) for item in entries]
    if len(level_values) >= 6:
        previous_avg = float(np.mean(level_values[-6:-3]))
        current_avg = float(np.mean(level_values[-3:]))
        delta = current_avg - previous_avg
        if delta >= 0.2:
            trend_text = "Stress trend rising"
            trend_class = "trend-up"
        elif delta <= -0.2:
            trend_text = "Stress trend improving"
            trend_class = "trend-down"
        else:
            trend_text = "Stress trend stable"
            trend_class = "trend-stable"
    else:
        trend_text = "Need more check-ins"
        trend_class = "trend-stable"

    unique_dates = sorted(
        {
            parse_timestamp_date(entry.get("timestamp"))
            for entry in entries
            if parse_timestamp_date(entry.get("timestamp"))
        },
        reverse=True,
    )

    streak_days = 0
    if unique_dates:
        streak_days = 1
        cursor = unique_dates[0]
        for date_value in unique_dates[1:]:
            if (cursor - date_value) == timedelta(days=1):
                streak_days += 1
                cursor = date_value
            else:
                break

    avg_wellness = int(round(np.mean([int(item.get("wellness_score", 0)) for item in recent])))

    return {
        "total_checks": len(entries),
        "streak_days": streak_days,
        "trend_text": trend_text,
        "trend_class": trend_class,
        "avg_wellness": avg_wellness,
        "bars": bars,
        "last_result": entries[-1].get("prediction", "Unknown"),
    }


def validate_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        return "Password must include at least one letter and one number."
    return None


# ---------------- LOAD STRESS MODEL ----------------
stress_model = pickle.load(open("model/stress_model.pkl", "rb"))

# ---------------- LOAD CHATBOT MODEL ----------------
chatbot_model = pickle.load(open("model/chatbot_model.pkl", "rb"))
vectorizer = pickle.load(open("model/vectorizer.pkl", "rb"))

with open("data/intents.json") as f:
    intents = json.load(f)

STRESS_ACTION_PLANS = {
    "Low Stress": {
        "message": "Great baseline. Keep your routine stable so stress does not build up later.",
        "now_steps": [
            "Take 10 slow breaths and relax your shoulders.",
            "Drink one glass of water.",
            "Write one priority for the next hour.",
        ],
        "today_steps": [
            "Keep a fixed sleep time tonight.",
            "Take at least one short outdoor walk.",
            "Limit unnecessary screen time before bed.",
        ],
        "alert": "",
    },
    "Medium Stress": {
        "message": "You are under pressure. A short reset now can prevent escalation.",
        "now_steps": [
            "Use the 1-minute breathing reset below.",
            "Take a 5-minute break away from screens.",
            "Split your biggest task into one smaller next step.",
        ],
        "today_steps": [
            "Use 25-minute focus blocks with 5-minute breaks.",
            "Avoid caffeine late in the day.",
            "Share your workload concerns with a friend or teammate.",
        ],
        "alert": "",
    },
    "High Stress": {
        "message": "Your stress is high right now. Prioritize immediate calming and support.",
        "now_steps": [
            "Pause work for 10 minutes and focus on controlled breathing.",
            "Ground yourself: name 5 things you see, 4 you feel, 3 you hear.",
            "Message someone you trust and tell them you need support.",
        ],
        "today_steps": [
            "Reduce non-essential tasks for today.",
            "Take at least 20 minutes of light movement (walk/stretch).",
            "Use the chatbot for immediate support and coping prompts.",
        ],
        "alert": "If stress feels overwhelming or unsafe, contact a licensed mental health professional or local emergency support.",
    },
}

GROUNDING_PROMPTS = [
    "Notice 5 things you can see right now.",
    "Notice 4 things you can physically feel.",
    "Notice 3 sounds around you.",
    "Notice 2 things you can smell.",
    "Notice 1 thing you can taste or remember tasting.",
    "Unclench your jaw, drop your shoulders, and take one deep breath.",
    "Name one thing you can finish in the next 10 minutes.",
]


# ---------------- HOME PAGE ----------------
@app.route("/")
def home():
    return render_template(
        "index.html",
        is_logged_in=bool(session.get("user")),
        username=session.get("user"),
    )


@app.route("/assessment")
def assessment():
    progress_summary = None
    focus_tip = None
    user_email = session.get("user_email")
    if user_email:
        user_entries = get_user_assessments(user_email)
        progress_summary = build_progress_summary(user_entries)
        focus_tip = build_focus_tip(user_entries)

    return render_template(
        "assessment.html",
        is_logged_in=bool(session.get("user")),
        username=session.get("user"),
        progress_summary=progress_summary,
        focus_tip=focus_tip,
    )


# ---------------- AUTH ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    default_next = request.values.get("next", request.values.get("next_url", "/"))
    safe_next = default_next if is_safe_next_path(default_next) else "/"

    if request.method == "GET":
        return render_template(
            "login.html",
            error=None,
            next_url=safe_next,
            form_data={"email": ""},
        )

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.form.get("next_url", "/").strip()
    safe_next = next_url if is_safe_next_path(next_url) else "/"

    if not email or not password:
        return render_template(
            "login.html",
            error="Email and password are required.",
            next_url=safe_next,
            form_data={"email": email},
        )

    users = load_users()
    user = users.get(email)
    password_hash = user.get("password_hash") if user else ""

    if user and not password_hash:
        return render_template(
            "login.html",
            error="This account uses Google sign-in. Please continue with Google.",
            next_url=safe_next,
            form_data={"email": email},
        )

    if not user or not password_hash or not check_password_hash(password_hash, password):
        return render_template(
            "login.html",
            error="Invalid email or password.",
            next_url=safe_next,
            form_data={"email": email},
        )

    session["user"] = user.get("full_name", email)
    session["user_email"] = email
    session["user_role"] = user.get("role", "user")
    return redirect(safe_next)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return build_signup_response(
            error=request.args.get("error"),
            form_data=default_signup_form(),
        )

    role = request.form.get("role", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    agree_terms = request.form.get("agree_terms") == "on"

    form_data = {
        "role": role or "user",
        "full_name": full_name,
        "email": email,
        "agree": agree_terms,
    }

    if role not in {"user", "admin"}:
        return build_signup_response(error="Please select a valid role.", form_data=form_data)

    if len(full_name) < 2:
        return build_signup_response(error="Please enter your full name.", form_data=form_data)

    if not EMAIL_PATTERN.match(email):
        return build_signup_response(error="Please enter a valid email address.", form_data=form_data)

    password_error = validate_password(password)
    if password_error:
        return build_signup_response(error=password_error, form_data=form_data)

    if password != confirm_password:
        return build_signup_response(error="Passwords do not match.", form_data=form_data)

    if not agree_terms:
        return build_signup_response(
            error="You must accept the Terms of Service and Privacy Policy.",
            form_data=form_data,
        )

    users = load_users()
    if email in users:
        return build_signup_response(
            error="An account with this email already exists. Please log in.",
            form_data=form_data,
        )

    users[email] = {
        "full_name": full_name,
        "email": email,
        "role": role,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    save_users(users)

    session["user"] = full_name
    session["user_email"] = email
    session["user_role"] = role
    return redirect(url_for("home"))


@app.route("/auth/google")
def google_auth():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return build_google_oauth_error_redirect(
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    requested_next = request.args.get("next", "/")
    safe_next = requested_next if is_safe_next_path(requested_next) else "/"

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state
    session["google_oauth_next"] = safe_next

    query = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": url_for("google_callback", _external=True),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return redirect(f"{GOOGLE_AUTH_ENDPOINT}?{query}")


@app.route("/auth/google/callback")
def google_callback():
    if request.args.get("error"):
        return build_google_oauth_error_redirect("Google sign-in was cancelled or denied.")

    expected_state = session.pop("google_oauth_state", None)
    safe_next = session.pop("google_oauth_next", "/")
    if not is_safe_next_path(safe_next):
        safe_next = "/"

    state = request.args.get("state", "")
    code = request.args.get("code", "")

    if not expected_state or not state or state != expected_state:
        return build_google_oauth_error_redirect("Google sign-in failed due to invalid state.")

    if not code:
        return build_google_oauth_error_redirect("Google sign-in failed. Missing authorization code.")

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return build_google_oauth_error_redirect(
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    try:
        token_payload = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": url_for("google_callback", _external=True),
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")

        token_request = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(token_request, timeout=12) as token_response:
            token_data = json.loads(token_response.read().decode("utf-8"))

        access_token = token_data.get("access_token", "")
        if not access_token:
            return build_google_oauth_error_redirect("Google sign-in failed while retrieving an access token.")

        userinfo_request = urllib.request.Request(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )

        with urllib.request.urlopen(userinfo_request, timeout=12) as userinfo_response:
            google_user = json.loads(userinfo_response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return build_google_oauth_error_redirect("Google sign-in failed while contacting Google.")

    email = str(google_user.get("email", "")).strip().lower()
    full_name = str(google_user.get("name", "")).strip()

    if not email:
        return build_google_oauth_error_redirect("Google account did not return an email address.")

    if not full_name:
        full_name = email.split("@")[0]

    users = load_users()
    existing_user = users.get(email)
    if existing_user:
        existing_user["full_name"] = existing_user.get("full_name") or full_name
        existing_user["role"] = existing_user.get("role", "user")
        existing_user["auth_provider"] = "google"
    else:
        users[email] = {
            "full_name": full_name,
            "email": email,
            "role": "user",
            "password_hash": "",
            "auth_provider": "google",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    save_users(users)

    session["user"] = users[email].get("full_name", full_name)
    session["user_email"] = email
    session["user_role"] = users[email].get("role", "user")
    return redirect(safe_next)


@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("user_email", None)
    session.pop("user_role", None)
    return redirect(url_for("home"))


# ---------------- STRESS PREDICTION ----------------
@app.route("/predict", methods=["POST"])
def predict():
    if not session.get("user"):
        return redirect(url_for("login", next="/assessment"))

    try:
        sleep_hours = float(request.form["sleep_hours"])
        work_study_hours = float(request.form["work_study_hours"])
        screen_time = float(request.form["screen_time"])
        physical_activity = float(request.form["physical_activity"])
        mood = float(request.form["mood"])
    except (KeyError, ValueError, TypeError):
        return redirect(url_for("assessment"))

    features = np.array([[sleep_hours, work_study_hours, screen_time, physical_activity, mood]])
    prediction = stress_model.predict(features)[0]

    if prediction == 0:
        result = "Low Stress"
    elif prediction == 1:
        result = "Medium Stress"
    else:
        result = "High Stress"

    wellness_score = calculate_wellness_score(
        sleep_hours=sleep_hours,
        work_study_hours=work_study_hours,
        screen_time=screen_time,
        physical_activity=physical_activity,
        mood=mood,
    )
    drivers = detect_stress_drivers(
        sleep_hours=sleep_hours,
        work_study_hours=work_study_hours,
        screen_time=screen_time,
        physical_activity=physical_activity,
        mood=mood,
    )
    micro_challenge = build_micro_challenge(drivers[0]["key"])

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "sleep_hours": sleep_hours,
        "work_study_hours": work_study_hours,
        "screen_time": screen_time,
        "physical_activity": physical_activity,
        "mood": mood,
        "prediction": result,
        "stress_level": STRESS_LEVEL_MAP[result],
        "wellness_score": wellness_score,
        "driver_keys": [item["key"] for item in drivers[:2]],
    }

    user_email = session.get("user_email")
    if user_email:
        user_entries = append_user_assessment(user_email, entry)
    else:
        user_entries = [entry]

    progress_summary = build_progress_summary(user_entries)
    focus_tip = build_focus_tip(user_entries)

    return render_template(
        "result.html",
        prediction=result,
        is_logged_in=bool(session.get("user")),
        plan=STRESS_ACTION_PLANS[result],
        grounding_prompts=GROUNDING_PROMPTS,
        wellness_score=wellness_score,
        drivers=drivers,
        micro_challenge=micro_challenge,
        progress_summary=progress_summary,
        focus_tip=focus_tip,
    )


# ---------------- CHATBOT PAGE ----------------
@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")


# ---------------- CHATBOT API ----------------
@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_msg = str(payload.get("message", "")).strip()
    history = payload.get("history")

    if not user_msg:
        return jsonify({"reply": "Send a message and I’ll respond."})

    crisis_reply = chatbot_llm.crisis_reply_if_needed(user_msg)
    if crisis_reply:
        return jsonify({"reply": crisis_reply})

    if chatbot_llm.is_enabled():
        try:
            reply = chatbot_llm.generate_reply(user_msg, history=history)
            return jsonify({"reply": reply})
        except RuntimeError:
            # Fall back to the local intent model if the LLM call fails.
            pass

    X = vectorizer.transform([user_msg])

    fallback_reply = (
        "I’m here with you. What’s the main thing stressing you right now: sleep, workload, screen time, mood, or something else?"
    )

    intent = None
    confidence = None
    if hasattr(chatbot_model, "predict_proba"):
        try:
            proba = chatbot_model.predict_proba(X)[0]
            best_index = int(np.argmax(proba))
            confidence = float(proba[best_index])
            intent = str(chatbot_model.classes_[best_index])
        except Exception:
            intent = None
            confidence = None
    if intent is None:
        try:
            intent = str(chatbot_model.predict(X)[0])
        except Exception:
            intent = None

    # If the classifier is unsure, do not force an unrelated canned intent.
    if confidence is not None and confidence < 0.35:
        return jsonify({"reply": fallback_reply})

    for i in intents.get("intents", []):
        if i.get("tag") == intent:
            responses = i.get("responses") or []
            if isinstance(responses, list) and responses:
                return jsonify({"reply": random.choice(responses)})

    return jsonify({"reply": fallback_reply})


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(debug=True)
