"""Live route/search/DeepSeek smoke test without touching WeChat."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SOURCE = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SOURCE) not in sys.path:
    sys.path.insert(0, str(BACKEND_SOURCE))

from ai_ta_bot.configuration import CourseManager  # noqa: E402
from ai_ta_bot.knowledge import RAGEngine  # noqa: E402
from ai_ta_bot.knowledge.question_router import (  # noqa: E402
    ROUTE_WEB,
    RouteDecision,
)


class ForceWebRouter:
    def classify(self, question, runtime, chat_history=None):
        return RouteDecision(
            route=ROUTE_WEB,
            reason="smoke test forced web route",
            search_query=question,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test routing, knowledge/search, and DeepSeek without touching WeChat.",
    )
    parser.add_argument("--group", required=True, help="Exact configured WeChat group name")
    parser.add_argument("--question", required=True, help="Question text without #举手")
    parser.add_argument(
        "--force-web",
        action="store_true",
        help="Force the configured web-search provider route",
    )
    args = parser.parse_args()

    manager = CourseManager()
    manager.load(PROJECT_ROOT / "config" / "bot.yaml")
    runtime = manager.get_course(args.group)
    if runtime is None:
        available = ", ".join(manager.group_map)
        raise SystemExit(f"Group is not configured: {args.group}; available: {available}")

    engine = RAGEngine(
        question_router=ForceWebRouter() if args.force_web else None,
    )
    if not args.force_web:
        engine.validate_knowledge_bases([runtime])

    answer = engine.answer(
        args.question,
        runtime,
        sender="smoke-test",
        group_name=args.group,
    )
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
