import json
from pathlib import Path

import storage_mysql


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    if not storage_mysql.is_configured():
        print(
            "MySQL is not configured. Set MYSQL_USER and MYSQL_DATABASE (and optional MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT)."
        )
        return 2

    storage_mysql.ensure_schema()

    users_path = Path("data") / "users.json"
    users = _load_json(users_path)
    if isinstance(users, dict):
        storage_mysql.save_users(users)
        print(f"Migrated users: {len(users)}")
    else:
        print("No users migrated (missing or invalid data/users.json).")

    assessments_path = Path("data") / "assessments.json"
    assessments = _load_json(assessments_path)
    migrated_assessments = 0
    if isinstance(assessments, dict):
        for email, entries in assessments.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # Keep the last 180 entries per user, matching app behavior.
                storage_mysql.append_user_assessment(email, entry, keep_last=180)
                migrated_assessments += 1
        print(f"Migrated assessments: {migrated_assessments}")
    else:
        print("No assessments migrated (missing or invalid data/assessments.json).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

