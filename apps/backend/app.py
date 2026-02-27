#!/usr/bin/env python
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    subprocess.check_call(command, cwd=BASE_DIR)


def main() -> None:
    # Default to configured PostgreSQL in development; only use SQLite if explicitly set.
    os.environ.setdefault("USE_SQLITE", os.getenv("USE_SQLITE", "0"))
    run([sys.executable, "manage.py", "migrate"])
    run(
        [
            sys.executable,
            "manage.py",
            "shell",
            "-c",
            (
                "from django.contrib.auth.models import User; "
                "User.objects.filter(username='admin@local').exists() or "
                "User.objects.create_superuser('admin@local','admin@local','admin')"
            ),
        ]
    )
    run([sys.executable, "manage.py", "runserver", "0.0.0.0:8000"])


if __name__ == "__main__":
    main()
