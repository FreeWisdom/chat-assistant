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
import sys

from dotenv import load_dotenv
load_dotenv()

from course_manager import CourseManager
from rag_engine import RAGEngine
from wechat_bot import WeChatBot
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    logger = logging.getLogger("main")
    logger.info("=" * 50)
    logger.info("   AI 助教机器人 启动中...")
    logger.info("=" * 50)

    try:
        # 1. 加载课程配置
        cm = CourseManager()
        cm.load("./config/courses.yaml")

        if config.TEST_GROUP:
            target = config.TEST_GROUP.strip()
            if target not in cm.group_map:
                logger.error(f"TEST_GROUP='{target}' 在 courses.yaml 的 bindings 中找不到，请检查群名！")
                logger.error(f"当前已配置的群: {list(cm.group_map.keys())}")
                sys.exit(1)
            cm.group_map = {target: cm.group_map[target]}
            # 同步精简 bindings 和 knowledge_bases（避免加载未绑定 KB）
            cm.bindings = [b for b in cm.bindings if b.group == target]
            logger.info(f"🔧 TEST_GROUP 模式: 只监听 [{target}]")

        # 2. 加载知识库
        rag = RAGEngine()
        loaded_kb_ids = set()
        for kb in cm.knowledge_bases.values():
            if kb.id in loaded_kb_ids:
                continue
            rag.load_knowledge_base(kb)
            loaded_kb_ids.add(kb.id)

        # 3. 启动微信机器人
        bot = WeChatBot(cm, rag)
        bot.start()

    except FileNotFoundError as e:
        logger.error(f"配置文件未找到: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("机器人已停止")
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
