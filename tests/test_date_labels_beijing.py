"""展示标签改用北京时区的单测。

覆盖：
- main.resolve_sidebar_date_label / build_sidebar_date_label（北京日期）
- 6.generate_docs.next_run_beijing_label（下次名义运行时刻）
- 6.generate_docs.build_latest_report_section（首页含"下次更新"/"北京时间"，详情链接用标签文本）
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BJT = ZoneInfo("Asia/Shanghai")


def _load_main_module():
    root = Path(__file__).resolve().parents[1]
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    spec = importlib.util.spec_from_file_location("main_bjt_mod", root / "src" / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_gen6_module():
    root = Path(__file__).resolve().parents[1]
    if "fitz" not in sys.modules:
        fitz_stub = types.ModuleType("fitz")
        fitz_stub.open = lambda *a, **k: None
        sys.modules["fitz"] = fitz_stub
    if "llm" not in sys.modules:
        llm_stub = types.ModuleType("llm")

        class DummyDeepSeekClient:
            def __init__(self, *a, **k):
                pass

        llm_stub.DeepSeekClient = DummyDeepSeekClient
        llm_stub.resolve_max_output_tokens = lambda default=393216: default
        sys.modules["llm"] = llm_stub
    spec = importlib.util.spec_from_file_location("gen6_bjt_mod", root / "src" / "6.generate_docs.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class MainDateLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_main_module()

    def test_single_day_label_is_beijing_date(self):
        label = self.mod.resolve_sidebar_date_label(None)
        expected = datetime.now(BJT).strftime("%Y-%m-%d")
        self.assertEqual(label, expected)
        # 形如 YYYY-MM-DD
        self.assertRegex(label or "", r"^\d{4}-\d{2}-\d{2}$")

    def test_explicit_small_fetch_days_returns_beijing_single_day(self):
        label = self.mod.resolve_sidebar_date_label(5)
        expected = datetime.now(BJT).strftime("%Y-%m-%d")
        self.assertEqual(label, expected)

    def test_range_label_endpoints_use_beijing(self):
        label = self.mod.build_sidebar_date_label(9)
        end = datetime.now(BJT).date()
        self.assertTrue((label or "").endswith(end.strftime("%Y-%m-%d")))


class Gen6NextRunLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_gen6_module()

    def test_before_nominal_today(self):
        # UTC 当天 10:00（早于 18:30）→ 名义时刻为今天 18:30 UTC = 次日 02:30 北京
        now_utc = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
        label = self.mod.next_run_beijing_label(now_utc)
        self.assertEqual(label, "2026-07-01 02:30")

    def test_after_nominal_rolls_to_next_day(self):
        # UTC 当天 20:00（晚于 18:30）→ 名义时刻为明天 18:30 UTC = 后天 02:30 北京
        now_utc = datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)
        label = self.mod.next_run_beijing_label(now_utc)
        self.assertEqual(label, "2026-07-02 02:30")

    def test_exactly_nominal_rolls_forward(self):
        # 恰好 18:30（<= now）→ 顺延到次日
        now_utc = datetime(2026, 6, 30, 18, 30, tzinfo=timezone.utc)
        label = self.mod.next_run_beijing_label(now_utc)
        self.assertEqual(label, "2026-07-02 02:30")


class Gen6LatestReportSectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_gen6_module()

    def _section(self, date_str="20260629", date_label="2026-06-30"):
        return self.mod.build_latest_report_section(
            date_str=date_str,
            date_label=date_label,
            generated_at="2026-06-30 04:47:00 北京时间",
            recommend_exists=True,
            deep_entries=[],
            quick_entries=[],
            paper_evidence_by_id={},
        )

    def test_has_next_update_line(self):
        out = self._section()
        self.assertIn("下次更新", out)
        self.assertIn("北京时间", out)
        self.assertIn("每日 02:30 自动刷新", out)

    def test_detail_link_uses_label_not_token_path(self):
        out = self._section(date_str="20260629", date_label="2026-06-30")
        # href 仍是 token 路径
        self.assertIn("(/202606/29/README)", out)
        # 可见文本用北京标签
        self.assertIn("[2026-06-30 日报](/202606/29/README)", out)
        # 不应再把路径当文本展示
        self.assertNotIn("[/202606/29/README]", out)

    def test_label_shown_when_passed(self):
        out = self._section(date_str="20260629", date_label="2026-06-30")
        self.assertIn("最新运行日期：2026-06-30", out)


if __name__ == "__main__":
    unittest.main()
