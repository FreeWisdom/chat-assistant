"""
AI 助教机器人 — 入口文件

启动方式:
  1. 复制 backend/.env.example 为 backend/.env，填入 DeepSeek API Key
  2. 编辑 config/bot.yaml，配置群、机器人、知识库绑定
  3. 在 knowledge-data/ 目录下放入知识文档
  4. cd backend && pip install -e .
  5. 确保 Windows 桌面版微信已登录（微信 4.0.5.x）
  6. python -m ai_ta_bot
"""
import logging
from pathlib import Path

from dotenv import load_dotenv

from .application.bootstrap import build_runner
from .configuration import CourseManager
from .knowledge import RAGEngine
from .persistence import single_instance_lock
from . import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / "backend" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> int:
    logger = logging.getLogger("main")
    logger.info("=" * 50)
    logger.info("   AI 助教机器人 启动中...")
    logger.info("=" * 50)

    try:
        with single_instance_lock(config.BOT_LOCK_FILE):
            cm = CourseManager()
            cm.load(str(PROJECT_ROOT / "config" / "bot.yaml"))

            if config.REQUIRE_LISTEN_GROUPS and not config.LISTEN_GROUPS:
                raise ValueError(
                    "安全模式要求配置 LISTEN_GROUPS，拒绝默认监听全部微信群"
                )
            if config.LISTEN_GROUPS:
                cm.restrict_to_groups(config.LISTEN_GROUPS)
                logger.info("微信群白名单: %s", ", ".join(config.LISTEN_GROUPS))

            rag = RAGEngine()
            loaded_kb_ids = set()
            for kb in cm.knowledge_bases.values():
                if kb.id in loaded_kb_ids:
                    continue
                rag.load_knowledge_base(kb)
                loaded_kb_ids.add(kb.id)

            runner = build_runner(cm, rag)
            runner.start()
            return 0

    except FileNotFoundError as e:
        logger.error(f"配置文件未找到: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("机器人已停止")
        return 0
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
