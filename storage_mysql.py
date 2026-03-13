from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any

_SCHEMA_READY = False


def _utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def is_configured() -> bool:
    user = os.environ.get("MYSQL_USER", "").strip()
    database = os.environ.get("MYSQL_DATABASE", "").strip()
    return bool(user and database)


def _get_config() -> dict[str, Any]:
    host = os.environ.get("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port_value = os.environ.get("MYSQL_PORT", "3306").strip() or "3306"
    try:
        port = int(port_value)
    except ValueError as exc:
        raise RuntimeError("MYSQL_PORT must be an integer.") from exc

    user = os.environ.get("MYSQL_USER", "").strip()
    password = os.environ.get("MYSQL_PASSWORD", "")
    database = os.environ.get("MYSQL_DATABASE", "").strip()

    if not user or not database:
        raise RuntimeError(
            "MySQL is not configured. Set MYSQL_USER and MYSQL_DATABASE (and optional MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT)."
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def _connect():
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("PyMySQL is required for MySQL storage. Install it with: pip install pymysql") from exc

    config = _get_config()
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@contextmanager
def _connection():
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    email VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    password_hash TEXT NOT NULL,
                    auth_provider VARCHAR(32) NOT NULL DEFAULT '',
                    created_at VARCHAR(32) NOT NULL,
                    PRIMARY KEY (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS assessments (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    email VARCHAR(255) NOT NULL,
                    timestamp VARCHAR(32) NOT NULL,
                    sleep_hours DOUBLE NOT NULL,
                    work_study_hours DOUBLE NOT NULL,
                    screen_time DOUBLE NOT NULL,
                    physical_activity DOUBLE NOT NULL,
                    mood DOUBLE NOT NULL,
                    prediction VARCHAR(32) NOT NULL,
                    stress_level INT NOT NULL,
                    wellness_score INT NOT NULL,
                    driver_keys_json TEXT NOT NULL,
                    PRIMARY KEY (id),
                    INDEX idx_assessments_email_id (email, id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

    _SCHEMA_READY = True


def load_users() -> dict[str, dict[str, Any]]:
    ensure_schema()

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT email, full_name, role, password_hash, auth_provider, created_at FROM users"
            )
            rows = cursor.fetchall() or []

    users: dict[str, dict[str, Any]] = {}
    for row in rows:
        email = str(row.get("email") or "").strip().lower()
        if not email:
            continue
        users[email] = {
            "full_name": row.get("full_name") or "",
            "email": email,
            "role": row.get("role") or "user",
            "password_hash": row.get("password_hash") or "",
            "auth_provider": row.get("auth_provider") or "",
            "created_at": row.get("created_at") or "",
        }

    return users


def save_users(users: dict[str, dict[str, Any]]) -> None:
    ensure_schema()
    if not isinstance(users, dict):
        return

    query = """
        INSERT INTO users (email, full_name, role, password_hash, auth_provider, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            full_name = VALUES(full_name),
            role = VALUES(role),
            password_hash = VALUES(password_hash),
            auth_provider = VALUES(auth_provider),
            created_at = VALUES(created_at)
    """

    with _connection() as connection:
        with connection.cursor() as cursor:
            for key_email, user in users.items():
                if not isinstance(user, dict):
                    continue

                email = str(user.get("email") or key_email or "").strip().lower()
                if not email:
                    continue

                full_name = str(user.get("full_name") or "").strip()
                role = str(user.get("role") or "user").strip().lower()
                if role not in {"user", "admin"}:
                    role = "user"

                password_hash = str(user.get("password_hash") or "")
                auth_provider = str(user.get("auth_provider") or "")
                created_at = str(user.get("created_at") or "").strip() or _utc_iso()

                cursor.execute(
                    query,
                    (
                        email,
                        full_name,
                        role,
                        password_hash,
                        auth_provider,
                        created_at,
                    ),
                )


def get_user_assessments(email: str, limit: int = 180) -> list[dict[str, Any]]:
    ensure_schema()

    email_value = str(email or "").strip().lower()
    if not email_value:
        return []

    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 180
    limit_value = max(1, min(limit_value, 1000))

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    timestamp,
                    sleep_hours,
                    work_study_hours,
                    screen_time,
                    physical_activity,
                    mood,
                    prediction,
                    stress_level,
                    wellness_score,
                    driver_keys_json
                FROM assessments
                WHERE email = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (email_value, limit_value),
            )
            rows = cursor.fetchall() or []

    entries: list[dict[str, Any]] = []
    for row in reversed(rows):
        raw_keys = row.get("driver_keys_json") or "[]"
        try:
            driver_keys = json.loads(raw_keys)
        except (TypeError, ValueError, json.JSONDecodeError):
            driver_keys = []
        if not isinstance(driver_keys, list):
            driver_keys = []

        entries.append(
            {
                "timestamp": row.get("timestamp") or "",
                "sleep_hours": float(row.get("sleep_hours") or 0.0),
                "work_study_hours": float(row.get("work_study_hours") or 0.0),
                "screen_time": float(row.get("screen_time") or 0.0),
                "physical_activity": float(row.get("physical_activity") or 0.0),
                "mood": float(row.get("mood") or 0.0),
                "prediction": row.get("prediction") or "",
                "stress_level": int(row.get("stress_level") or 0),
                "wellness_score": int(row.get("wellness_score") or 0),
                "driver_keys": driver_keys,
            }
        )

    return entries


def append_user_assessment(email: str, entry: dict[str, Any], keep_last: int = 180) -> list[dict[str, Any]]:
    ensure_schema()

    email_value = str(email or "").strip().lower()
    if not email_value:
        return []

    if not isinstance(entry, dict):
        return get_user_assessments(email_value, limit=keep_last)

    try:
        keep_value = int(keep_last)
    except (TypeError, ValueError):
        keep_value = 180
    keep_value = max(1, min(keep_value, 1000))

    driver_keys = entry.get("driver_keys") or []
    if not isinstance(driver_keys, list):
        driver_keys = []

    timestamp = str(entry.get("timestamp") or "").strip() or _utc_iso()

    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO assessments (
                    email,
                    timestamp,
                    sleep_hours,
                    work_study_hours,
                    screen_time,
                    physical_activity,
                    mood,
                    prediction,
                    stress_level,
                    wellness_score,
                    driver_keys_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    email_value,
                    timestamp,
                    float(entry.get("sleep_hours") or 0.0),
                    float(entry.get("work_study_hours") or 0.0),
                    float(entry.get("screen_time") or 0.0),
                    float(entry.get("physical_activity") or 0.0),
                    float(entry.get("mood") or 0.0),
                    str(entry.get("prediction") or ""),
                    int(entry.get("stress_level") or 0),
                    int(entry.get("wellness_score") or 0),
                    json.dumps(driver_keys),
                ),
            )

            # Trim older rows to keep the most recent N per user.
            cursor.execute(
                """
                DELETE FROM assessments
                WHERE email = %s
                  AND id NOT IN (
                    SELECT id FROM (
                        SELECT id
                        FROM assessments
                        WHERE email = %s
                        ORDER BY id DESC
                        LIMIT %s
                    ) AS keep_rows
                  )
                """,
                (email_value, email_value, keep_value),
            )

    return get_user_assessments(email_value, limit=keep_value)

