"""Start the real WeChat bot with a hard-coded two-group safety gate."""

from __future__ import annotations

import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SOURCE = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SOURCE) not in sys.path:
    sys.path.insert(0, str(BACKEND_SOURCE))

from ai_ta_bot import config  # noqa: E402
from ai_ta_bot.__main__ import main  # noqa: E402
from ai_ta_bot.configuration import CourseManager  # noqa: E402


EXPECTED_GROUPS = (
    "\u9879\u76ee\u7814\u7a76",
    "\u6bcf\u65e5\u996e\u98df\u6253\u5361\U0001f37d\ufe0f",
)


def validate_safety_gate() -> None:
    if config.LISTEN_GROUPS != EXPECTED_GROUPS:
        raise RuntimeError(
            f"LISTEN_GROUPS must exactly match {EXPECTED_GROUPS}, "
            f"got {config.LISTEN_GROUPS}"
        )
    if config.DRY_RUN:
        raise RuntimeError("DRY_RUN=true; real reply test is not enabled")

    manager = CourseManager()
    manager.load(PROJECT_ROOT / "config" / "bot.yaml")
    manager.restrict_to_groups(config.LISTEN_GROUPS)
    if tuple(manager.group_map) != EXPECTED_GROUPS:
        raise RuntimeError(f"Unexpected runtime groups: {tuple(manager.group_map)}")
    for group_name, runtime in manager.group_map.items():
        if runtime.reply_triggers != ["#\u4e3e\u624b"]:
            raise RuntimeError(
                f"Unexpected trigger for {group_name}: {runtime.reply_triggers}"
            )


def configure_file_log() -> Path:
    log_dir = PROJECT_ROOT / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "two-group-live-test.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger().addHandler(handler)
    return log_path


if __name__ == "__main__":
    validate_safety_gate()
    path = configure_file_log()
    print("安全白名单已确认：项目研究、每日饮食打卡🍽️")
    print("响应 #举手、@机器人，以及引用机器人消息后的问题。")
    print("需要立即停止时，请在此窗口按 Ctrl+C。")
    print(f"日志：{path}")
    raise SystemExit(main())
