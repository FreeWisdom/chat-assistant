"""
AI 助教机器人 — 入口文件

启动方式:
  1. 复制 .env.example 为 .env，填入 DeepSeek API Key
  2. 编辑 config/courses.yaml，填入微信群名
  3. 在 knowledge/ 目录下放入课程知识文档
  4. py -3.11 -m pip install -r requirements.txt
  5. 确保 Windows 桌面版微信已登录（微信 4.0.5.x）
  6. py -3.11 main.py
"""
import logging
from dotenv import load_dotenv
load_dotenv()

from application.bootstrap import build_runner
from configuration import CourseManager
from knowledge import RAGEngine
import config

# 配置日志
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
        # 1. 加载课程配置
        cm = CourseManager()
        cm.load("./config/courses.yaml")

        if config.REQUIRE_TEST_GROUP and not config.TEST_GROUP.strip():
            raise ValueError(
                "MVP 安全模式要求配置 TEST_GROUP，拒绝默认监听全部微信群"
            )
        if config.TEST_GROUP:
            cm.restrict_to_group(config.TEST_GROUP)
            logger.info("TEST_GROUP 模式: 只监听 [%s]", config.TEST_GROUP)

        # 2. 加载知识库
        rag = RAGEngine()
        loaded_kb_ids = set()
        for kb in cm.knowledge_bases.values():
            if kb.id in loaded_kb_ids:
                continue
            rag.load_knowledge_base(kb)
            loaded_kb_ids.add(kb.id)

        # 3. 启动微信机器人
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
