from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import pickle
import numpy as np
import json
import random
import os
import re
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mindguard_dev_secret")

USERS_DB_PATH = os.path.join("data", "users.json")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def load_users():
    if not os.path.exists(USERS_DB_PATH):
        return {}

    try:
        with open(USERS_DB_PATH, "r", encoding="utf-8") as users_file:
            users = json.load(users_file)
    except (json.JSONDecodeError, OSError):
        return {}

    return users if isinstance(users, dict) else {}


def save_users(users):
    os.makedirs(os.path.dirname(USERS_DB_PATH), exist_ok=True)
    with open(USERS_DB_PATH, "w", encoding="utf-8") as users_file:
        json.dump(users, users_file, indent=2)


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


# ---------------- HOME PAGE ----------------
@app.route("/")
def home():
    return render_template(
        "index.html",
        is_logged_in=bool(session.get("user")),
        username=session.get("user"),
    )


# ---------------- AUTH ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    default_next = request.values.get("next", request.values.get("next_url", "/"))
    safe_next = default_next if isinstance(default_next, str) and default_next.startswith("/") else "/"

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
    safe_next = next_url if next_url.startswith("/") else "/"

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
        return render_template(
            "signup.html",
            error=None,
            form_data={
                "role": "user",
                "full_name": "",
                "email": "",
                "agree": False,
            },
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
        return render_template("signup.html", error="Please select a valid role.", form_data=form_data)

    if len(full_name) < 2:
        return render_template("signup.html", error="Please enter your full name.", form_data=form_data)

    if not EMAIL_PATTERN.match(email):
        return render_template("signup.html", error="Please enter a valid email address.", form_data=form_data)

    password_error = validate_password(password)
    if password_error:
        return render_template("signup.html", error=password_error, form_data=form_data)

    if password != confirm_password:
        return render_template("signup.html", error="Passwords do not match.", form_data=form_data)

    if not agree_terms:
        return render_template(
            "signup.html",
            error="You must accept the Terms of Service and Privacy Policy.",
            form_data=form_data,
        )

    users = load_users()
    if email in users:
        return render_template(
            "signup.html",
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
        return redirect(url_for("login", next="/"))

    try:
        sleep_hours = float(request.form["sleep_hours"])
        work_study_hours = float(request.form["work_study_hours"])
        screen_time = float(request.form["screen_time"])
        physical_activity = float(request.form["physical_activity"])
        mood = float(request.form["mood"])
    except (KeyError, ValueError, TypeError):
        return redirect(url_for("home"))

    features = np.array([[sleep_hours, work_study_hours, screen_time, physical_activity, mood]])
    prediction = stress_model.predict(features)[0]

    if prediction == 0:
        result = "Low Stress"
    elif prediction == 1:
        result = "Medium Stress"
    else:
        result = "High Stress"

    return render_template("result.html", prediction=result)


# ---------------- CHATBOT PAGE ----------------
@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")


# ---------------- CHATBOT API ----------------
@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.json["message"]

    X = vectorizer.transform([user_msg])
    intent = chatbot_model.predict(X)[0]

    for i in intents["intents"]:
        if i["tag"] == intent:
            return jsonify({"reply": random.choice(i["responses"])})

    return jsonify({"reply": "I'm here to help. Please tell me more."})


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(debug=True)
