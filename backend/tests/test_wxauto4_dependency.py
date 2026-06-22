import json
import re
import unittest
from importlib import metadata
from pathlib import Path

import wxauto4


ROOT = Path(__file__).resolve().parents[2]
PIN_PATTERN = re.compile(
    r"https://github\.com/FreeWisdom/wxauto-4\.0\.git@([0-9a-f]{40})"
)


class Wxauto4DependencyTests(unittest.TestCase):
    def test_all_dependency_files_match_the_lock(self):
        lock = json.loads(
            (ROOT / "config" / "wxauto4.lock.json").read_text(encoding="utf-8")
        )
        expected = lock["commit"]
        files = (
            ROOT / "backend" / "requirements.txt",
            ROOT / "backend" / "pyproject.toml",
        )

        for path in files:
            match = PIN_PATTERN.search(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(match, f"missing wxauto4 commit pin in {path}")
            self.assertEqual(match.group(1), expected, f"stale wxauto4 pin in {path}")

    def test_runtime_package_matches_the_lock(self):
        expected = json.loads(
            (ROOT / "config" / "wxauto4.lock.json").read_text(encoding="utf-8")
        )["commit"]
        direct_url_text = metadata.distribution("wxauto4").read_text("direct_url.json")

        self.assertIsNotNone(
            direct_url_text,
            "wxauto4 install source is unknown; run scripts/sync-wxauto4.ps1",
        )
        direct_url = json.loads(direct_url_text)
        self.assertFalse(
            direct_url.get("dir_info", {}).get("editable", False),
            "wxauto4 must not be imported from an editable sibling checkout",
        )
        self.assertEqual(
            direct_url.get("vcs_info", {}).get("commit_id"),
            expected,
            "installed wxauto4 does not match config/wxauto4.lock.json",
        )

    def test_latest_upstream_feature_exports_are_available(self):
        for name in (
            "WeChat",
            "WxParam",
            "Moment",
            "HandRaiseReplyWorkflow",
            "ReplyTaskStore",
            "SearchMessageLocator",
        ):
            self.assertTrue(hasattr(wxauto4, name), f"wxauto4 export is missing: {name}")


if __name__ == "__main__":
    unittest.main()
