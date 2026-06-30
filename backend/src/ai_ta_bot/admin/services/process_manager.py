from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ... import config, config_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
PID_FILE = RUNTIME_DIR / "bot.pid"
LOCK_FILE = RUNTIME_DIR / "bot.lock"

BOT_COMMAND_MARKER = "ai_ta_bot"
ADMIN_COMMAND_MARKER = "admin_app"


@dataclass(frozen=True)
class RuntimeCheck:
    code: str
    message: str
    level: str = "blocking"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "level": self.level,
            "message": self.message,
        }


def runtime_health() -> dict[str, Any]:
    metadata = _read_pid_metadata()
    health = _read_json(_health_path())
    pid = _metadata_pid(metadata) or _safe_int(health.get("pid"))
    commandline = _get_process_commandline(pid) if pid else ""
    process_running = bool(pid and _is_managed_command(commandline))

    if process_running:
        status = str(health.get("status") or "starting")
    elif metadata:
        status = "error" if health.get("status") == "failed" else "exited"
    elif health.get("status") in {"stopped", "failed"}:
        status = "error" if health.get("status") == "failed" else "stopped"
    else:
        status = "not_started"

    last_task = health.get("last_task") if isinstance(health.get("last_task"), dict) else {}
    last_error = str(
        health.get("error")
        or last_task.get("error")
        or ""
    )
    log_file = str(metadata.get("logFile") or metadata.get("log_file") or "")
    listen_groups = (
        health.get("allowed_chats")
        or list(config.LISTEN_GROUPS)
    )
    bot_names = health.get("bot_names") or list(config.BOT_MENTION_NAMES)

    return {
        "ok": True,
        "status": status,
        "running": process_running and status in {"starting", "running"},
        "pid": pid if process_running or metadata else None,
        "startedAt": metadata.get("startedAt") or metadata.get("started_at"),
        "stoppedAt": health.get("stopped_at") or health.get("stoppedAt"),
        "exitCode": health.get("exit_code") or health.get("exitCode"),
        "dryRun": bool(health.get("dry_run", config.DRY_RUN)),
        "listenGroups": list(listen_groups or []),
        "botMentionNames": list(bot_names or []),
        "lastHeartbeatAt": health.get("updated_at") or health.get("updatedAt"),
        "lastError": last_error,
        "logFile": log_file,
        "warnings": _runtime_warnings(),
        "health": health,
    }


def runtime_logs(limit: int = 200) -> dict[str, Any]:
    safe_limit = min(max(int(limit or 200), 1), 1000)
    log_file = _current_log_file()
    if log_file is None or not log_file.exists():
        return {
            "ok": True,
            "logFile": "",
            "lines": [],
            "truncated": False,
        }

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    tail = lines[-safe_limit:]
    return {
        "ok": True,
        "logFile": _relative(log_file),
        "lines": [_redact_secrets(line) for line in tail],
        "truncated": len(lines) > len(tail),
    }


def start_bot(*, force: bool = False) -> dict[str, Any]:
    current = runtime_health()
    if current["running"]:
        if not force:
            return {
                **current,
                "blockingChecks": [],
                "warnings": current.get("warnings", []),
                "message": "机器人监听已在运行",
            }
        stopped = stop_bot(force=True)
        if not stopped["ok"]:
            return stopped

    blocking, warnings = preflight_checks()
    if blocking:
        return {
            "ok": False,
            "status": "error",
            "running": False,
            "pid": None,
            "logFile": "",
            "blockingChecks": [item.to_dict() for item in blocking],
            "warnings": [item.to_dict() for item in warnings],
            "message": "启动前检查未通过",
        }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"bot_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_handle = open(log_file, "w", encoding="utf-8")
    creation_flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, "-m", BOT_COMMAND_MARKER]
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
            env=env,
        )
    finally:
        log_handle.close()
    started_at = _now()
    _write_pid_metadata({
        "pid": proc.pid,
        "startedAt": started_at,
        "logFile": _relative(log_file),
        "command": command,
    })
    return {
        "ok": True,
        "status": "starting",
        "running": True,
        "pid": proc.pid,
        "startedAt": started_at,
        "stoppedAt": None,
        "exitCode": None,
        "dryRun": config.DRY_RUN,
        "listenGroups": list(config.LISTEN_GROUPS),
        "botMentionNames": list(config.BOT_MENTION_NAMES),
        "lastHeartbeatAt": None,
        "lastError": "",
        "logFile": _relative(log_file),
        "blockingChecks": [],
        "warnings": [item.to_dict() for item in warnings],
        "message": "机器人监听启动中",
    }


def stop_bot(*, force: bool = False, timeout_seconds: int = 8) -> dict[str, Any]:
    metadata = _read_pid_metadata()
    pid = _metadata_pid(metadata)
    if not pid:
        _write_stop_health(None, "stopped")
        return {
            "ok": True,
            "status": "stopped",
            "running": False,
            "stoppedPids": [],
            "message": "机器人监听未运行",
        }

    commandline = _get_process_commandline(pid)
    if not commandline and _is_process_running(pid):
        return {
            "ok": False,
            "status": "error",
            "running": True,
            "stoppedPids": [],
            "message": f"无法验证 PID {pid} 是否为本产品机器人进程，已拒绝停止",
        }
    if commandline and not _is_managed_command(commandline):
        return {
            "ok": False,
            "status": "error",
            "running": False,
            "stoppedPids": [],
            "message": f"PID {pid} 不是本产品机器人进程，已拒绝停止",
        }

    if commandline:
        _terminate_pid(pid, force=force)
        deadline = time.monotonic() + max(1, int(timeout_seconds or 8))
        while time.monotonic() < deadline:
            if not _is_process_running(pid):
                break
            time.sleep(0.2)
        if _is_process_running(pid):
            if not force:
                return {
                    "ok": False,
                    "status": "error",
                    "running": True,
                    "stoppedPids": [],
                    "message": "停止超时，请稍后重试或使用强制停止",
                }
            _terminate_pid(pid, force=True)
    _clear_pid_metadata()
    _write_stop_health(pid, "stopped")
    return {
        "ok": True,
        "status": "stopped",
        "running": False,
        "stoppedPids": [pid],
        "message": "机器人监听已停止",
    }


def restart_bot(*, force: bool = False) -> dict[str, Any]:
    stopped = stop_bot(force=force)
    if not stopped["ok"]:
        return stopped
    started = start_bot(force=False)
    return {
        **started,
        "stoppedPids": stopped.get("stoppedPids", []),
    }


def preflight_checks() -> tuple[list[RuntimeCheck], list[RuntimeCheck]]:
    blocking: list[RuntimeCheck] = []
    warnings: list[RuntimeCheck] = []

    try:
        config_data = config_store.read_config()
        validation_errors = config_store.validate_config(config_data)
    except Exception as exc:
        config_data = {}
        validation_errors = [str(exc)]
    for index, error in enumerate(validation_errors):
        blocking.append(RuntimeCheck(
            code=f"CONFIG_VALIDATION_{index + 1}",
            message=error,
        ))

    listen_groups = list(config.LISTEN_GROUPS)
    if config.REQUIRE_LISTEN_GROUPS and not listen_groups:
        blocking.append(RuntimeCheck(
            code="MISSING_LISTEN_GROUPS",
            message="REQUIRE_LISTEN_GROUPS=true 时必须配置 LISTEN_GROUPS",
        ))

    bindings = config_data.get("bindings", []) if isinstance(config_data, dict) else []
    binding_by_group = {
        str(item.get("group", "")).strip(): item
        for item in bindings
    }
    kb_by_id = {
        str(item.get("id", "")).strip(): item
        for item in config_data.get("knowledgeBases", [])
    } if isinstance(config_data, dict) else {}
    if (
        not _configured_value(config.LLM_API_KEY)
        and _requires_local_llm(config_data, listen_groups)
    ):
        blocking.append(RuntimeCheck(
            code="MISSING_LLM_API_KEY",
            message="缺少 LLM_API_KEY，无法启动本项目回答生成。若走 MaxKB，请确保监听群只绑定 provider=maxkb 的知识库",
        ))

    for group in listen_groups:
        binding = binding_by_group.get(group)
        if not binding:
            blocking.append(RuntimeCheck(
                code="LISTEN_GROUP_NOT_BOUND",
                message=f"LISTEN_GROUPS 中的群未在 bindings 中配置: {group}",
            ))
            continue
        providers = {
            str(kb_by_id.get(kb_id, {}).get("provider", "aliyun_bailian") or "aliyun_bailian")
            for kb_id in binding.get("knowledgeBaseIds", [])
            if kb_id in kb_by_id
        }
        if len(providers) > 1:
            blocking.append(RuntimeCheck(
                code="MIXED_KNOWLEDGE_PROVIDERS",
                message=f"群 {group} 绑定了多个 provider，MVP 阶段不支持混合检索",
            ))
        if providers == {"maxkb"}:
            if not _configured_value(getattr(config, "MAXKB_API_KEY", "")):
                blocking.append(RuntimeCheck(
                    code="MISSING_MAXKB_API_KEY",
                    message="MaxKB provider 已绑定，但 MAXKB_API_KEY 未配置",
                ))
            if not _configured_value(getattr(config, "MAXKB_BASE_URL", "")):
                blocking.append(RuntimeCheck(
                    code="MISSING_MAXKB_BASE_URL",
                    message="MaxKB provider 已绑定，但 MAXKB_BASE_URL 未配置",
                ))

    if not config.DRY_RUN and not getattr(config, "ALLOW_REAL_SEND_CONFIRM", False):
        blocking.append(RuntimeCheck(
            code="REAL_SEND_NOT_CONFIRMED",
            message="DRY_RUN=false 前必须在页面确认允许真实发送",
        ))

    metadata = _read_pid_metadata()
    pid = _metadata_pid(metadata)
    if pid:
        commandline = _get_process_commandline(pid)
        if commandline and not _is_managed_command(commandline):
            blocking.append(RuntimeCheck(
                code="UNMANAGED_PID_FILE",
                message=f"runtime/bot.pid 指向的 PID {pid} 不是本产品机器人进程",
            ))

    if LOCK_FILE.exists():
        lock_holder_alive = False
        if pid:
            commandline = _get_process_commandline(pid)
            lock_holder_alive = bool(commandline and _is_managed_command(commandline))
        if not lock_holder_alive:
            warnings.append(RuntimeCheck(
                code="STALE_LOCK_FILE",
                level="warning",
                message="runtime/bot.lock 存在但无对应运行进程，将被自动清理",
            ))
            _clear_lock_file()

    warnings.extend(_runtime_warning_checks())
    return blocking, warnings


def _runtime_warnings() -> list[dict[str, str]]:
    return [item.to_dict() for item in _runtime_warning_checks()]


def _runtime_warning_checks() -> list[RuntimeCheck]:
    warnings: list[RuntimeCheck] = []
    if not config.BOT_MENTION_NAMES:
        warnings.append(RuntimeCheck(
            code="EMPTY_BOT_MENTION_NAMES",
            level="warning",
            message="BOT_MENTION_NAMES 为空，只能依赖触发词识别",
        ))
    if config.WEB_SEARCH_ENABLED:
        if config.WEB_SEARCH_PROVIDER == "volcengine" and not _configured_value(config.VOLCENGINE_API_KEY):
            warnings.append(RuntimeCheck(
                code="MISSING_VOLCENGINE_API_KEY",
                level="warning",
                message="已启用火山引擎搜索，但 VOLCENGINE_API_KEY 未配置",
            ))
        if config.WEB_SEARCH_PROVIDER == "tavily" and not _configured_value(config.TAVILY_API_KEY):
            warnings.append(RuntimeCheck(
                code="MISSING_TAVILY_API_KEY",
                level="warning",
                message="已启用 Tavily 搜索，但 TAVILY_API_KEY 未配置",
            ))
    return warnings


def _health_path() -> Path:
    path = Path(config.BOT_HEALTH_PATH)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_stop_health(pid: int | None, status: str) -> None:
    path = _health_path()
    existing = _read_json(path)
    existing.update({
        "status": status,
        "pid": pid,
        "updated_at": _now(),
        "stopped_at": _now(),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_pid_metadata() -> dict[str, Any]:
    return _read_json(PID_FILE)


def _write_pid_metadata(metadata: dict[str, Any]) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _clear_pid_metadata() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass
    _clear_lock_file()


def _clear_lock_file() -> None:
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def _metadata_pid(metadata: dict[str, Any]) -> int | None:
    return _safe_int(metadata.get("pid"))


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_process_commandline(pid: int | None) -> str:
    if not pid:
        return ""
    if os.name == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"(Get-CimInstance Win32_Process -Filter "
                f"'ProcessId = {pid}').CommandLine"
            ),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return ""
        return (result.stdout or "").strip()
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        try:
            return proc_cmdline.read_text(encoding="utf-8").replace("\x00", " ").strip()
        except OSError:
            return ""
    return ""


def _is_managed_command(commandline: str) -> bool:
    normalized = commandline.replace("\\", "/").lower()
    return (
        BOT_COMMAND_MARKER in normalized
        and ADMIN_COMMAND_MARKER not in normalized
    )


def _terminate_pid(pid: int, *, force: bool) -> None:
    if os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(command, capture_output=True, timeout=8)
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def _current_log_file() -> Path | None:
    metadata = _read_pid_metadata()
    log_file = metadata.get("logFile") or metadata.get("log_file")
    if log_file:
        path = PROJECT_ROOT / str(log_file)
        if path.exists():
            return path
    if not LOG_DIR.exists():
        return None
    candidates = sorted(
        LOG_DIR.glob("*.log"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _configured_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.startswith("your-") else text


def _requires_local_llm(config_data: Any, listen_groups: list[str]) -> bool:
    if not isinstance(config_data, dict) or not listen_groups:
        return True
    bindings = config_data.get("bindings", [])
    knowledge_bases = {
        str(item.get("id", "")).strip(): item
        for item in config_data.get("knowledgeBases", [])
    }
    bindings_by_group = {
        str(item.get("group", "")).strip(): item
        for item in bindings
    }
    for group in listen_groups:
        binding = bindings_by_group.get(group)
        if not binding:
            return True
        providers = {
            str(
                knowledge_bases.get(kb_id, {}).get("provider", "aliyun_bailian")
                or "aliyun_bailian"
            )
            for kb_id in binding.get("knowledgeBaseIds", [])
            if kb_id in knowledge_bases
        }
        if providers != {"maxkb"}:
            return True
    return False


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _redact_secrets(text: str) -> str:
    redacted = text
    markers = ("sk-", "Bearer ")
    for marker in markers:
        index = redacted.find(marker)
        if index >= 0:
            end = index + len(marker) + 6
            redacted = redacted[:index + len(marker)] + "***" + redacted[end:]
    return redacted
