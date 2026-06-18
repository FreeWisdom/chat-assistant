from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent


def stop_bot() -> list[int]:
    """Kill running ai_ta_bot processes (exclude admin), return killed PIDs."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline,processid", "/format:csv"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return []
    killed: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "ai_ta_bot" not in line or "admin_app" in line:
            continue
        parts = line.split(",")
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            killed.append(pid)
        except Exception:
            pass
    return killed


def start_bot() -> subprocess.Popen:
    log_dir = PROJECT_ROOT / "runtime" / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"restart_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_handle = open(log_file, "w", encoding="utf-8")

    creation_flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [sys.executable, "-m", "ai_ta_bot"],
        cwd=str(PROJECT_ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags,
        close_fds=True,
        env=env,
    )
