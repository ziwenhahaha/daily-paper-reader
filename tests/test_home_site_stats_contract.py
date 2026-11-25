import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTICE_FILES = (
    ROOT / "docs_init" / "_home_notice.md",
    ROOT / "docs_init" / "README.md",
)

HOME_README_FILES = (
    ROOT / "docs_init" / "README.md",
)

PROMO_FILES = (
    ROOT / "docs_init" / "_home_promo.md",
    ROOT / "docs_init" / "README.md",
)


def test_home_notice_contains_stats_and_tutorial_entry():
    for path in NOTICE_FILES:
        content = path.read_text(encoding="utf-8")
        assert "公告与更新" in content, path
        assert 'class="dpr-home-notice-tutorial"' in content, path
        assert "data-dpr-site-stats" in content, path
        assert "data-dpr-daily-readers" in content, path
        assert "data-dpr-fork-count" in content, path
        assert "今天有" in content and "人在看论文" in content, path
        assert "人加入 Daily Paper Reader" in content, path


def test_home_readme_contains_history_trend_selectors():
    for path in HOME_README_FILES:
        content = path.read_text(encoding="utf-8")
        assert "昨天有" in content, path
        assert 'class="dpr-home-history"' in content, path
        assert 'class="dpr-home-history-trigger"' in content, path
        assert "data-dpr-history-trigger" in content, path
        assert 'class="dpr-home-history-popover"' in content, path
        assert "data-dpr-history-popover" in content, path
        assert 'class="dpr-home-history-header"' in content, path
        assert "data-dpr-history-range" in content, path
        assert "data-dpr-history-peak" in content, path
        assert "data-dpr-history-chart" in content, path


def test_home_notice_contains_latest_update():
    for path in NOTICE_FILES:
        content = path.read_text(encoding="utf-8")
        assert 'class="dpr-home-notice-entry"' in content, path
        assert content.count('class="dpr-home-notice-entry"') <= 3, path
        assert '<time class="dpr-home-notice-date" datetime="2026-11-25">11.25</time>' in content, path
        assert "侧边栏新增后台任务实时进度显示" in content, path
        assert "公共 Supabase 实时显示当前步骤与逐篇生成进度" in content, path
        assert "90天/365天专题回溯与大礼包重构为标准流水线" in content, path
        assert "默认精选最多 50 篇" in content, path
        assert "阅读页、侧边栏与后台管理界面视觉升级" in content, path
        assert "极简炭黑×浅雾蓝护眼配色" in content, path
        assert "medRxiv 自动更新已恢复" not in content, path
        assert "日报跨日重复推荐已修复" not in content, path
        assert "90天/365天 arXiv 专题回溯" not in content, path
        assert "区间日报可正常点开" not in content, path
        titles = re.findall(r'<strong class="dpr-home-notice-entry-title">([^<]+)</strong>', content)
        assert titles[0] == "侧边栏新增后台任务实时进度显示", path
        dates = re.findall(r'<time class="dpr-home-notice-date" datetime="([^"]+)">', content)
        assert dates == sorted(dates, reverse=True), path
        assert re.search(
            r'<time class="dpr-home-notice-date" datetime="\d{4}-\d{2}-\d{2}">\d{2}\.\d{2}</time>',
            content,
        ), path
        assert re.search(
            r'<strong class="dpr-home-notice-entry-title">[^<]+</strong>',
            content,
        ), path


def test_home_promo_uses_the_shared_panel_structure():
    for path in PROMO_FILES:
        content = path.read_text(encoding="utf-8")
        assert 'class="dpr-home-promo-card dpr-home-panel"' in content, path
        assert 'class="dpr-home-panel-header"' in content, path
        assert 'class="dpr-home-promo-copy"' in content, path
        assert 'class="dpr-home-promo-meta"' in content, path
        assert "QQ群" in content and "583867967" in content, path


def test_home_panel_modules_are_embedded_in_the_init_homepage():
    readme = (ROOT / "docs_init" / "README.md").read_text(encoding="utf-8")
    notice = (ROOT / "docs_init" / "_home_notice.md").read_text(encoding="utf-8").strip()
    promo = (ROOT / "docs_init" / "_home_promo.md").read_text(encoding="utf-8").strip()
    assert notice in readme
    assert promo in readme


def test_site_stats_script_is_loaded_without_blocking_core_assets():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "app/site-stats.js" in html
    assert "[DPR] 首页统计加载失败" in html


def test_home_stats_css_has_desktop_and_mobile_layouts():
    css = (ROOT / "app" / "app.css").read_text(encoding="utf-8")
    assert ".dpr-home-panel-header" in css
    assert ".dpr-home-site-stats" in css
    assert ".dpr-home-site-stat-value" in css
    assert ".dpr-home-history" in css
    assert ".dpr-home-history-trigger" in css
    assert ".dpr-home-history-popover" in css
    assert "[data-dpr-history-range]" in css
    assert "[data-dpr-history-peak]" in css
    assert "[data-dpr-history-chart]" in css
    assert "font-variant-numeric: tabular-nums" in css
    assert "@media (max-width: 600px)" in css

    hidden_rule = css.split(".markdown-section .dpr-home-site-stats[hidden]", 1)[1].split("}", 1)[0]
    assert "visibility: hidden" in hidden_rule
    assert "display: none" not in hidden_rule

    popover_rule = css.split(".markdown-section .dpr-home-history-popover", 1)[1].split("}", 1)[0]
    assert "opacity: 0" in popover_rule
    assert "visibility: hidden" in popover_rule
    assert "pointer-events: none" in popover_rule
    assert "width: 260px" in popover_rule
    assert "border-radius: 8px" in popover_rule
    assert "background: #ffffff" in popover_rule
    assert "box-shadow:" in popover_rule
    assert "gradient" not in popover_rule

    trigger_rule = css.split(".markdown-section .dpr-home-history-trigger", 1)[1].split("}", 1)[0]
    assert "width: 26px" in trigger_rule
    assert "height: 26px" in trigger_rule
    assert "border-radius: 999px" in trigger_rule

    chart_rule = css.split(".markdown-section [data-dpr-history-chart]", 1)[1].split("}", 1)[0]
    assert "border" in chart_rule
    assert "#278553" in chart_rule or "#2f7a55" in chart_rule
    assert "gradient" not in chart_rule

    meta_rule = css.split(".markdown-section .dpr-home-history-meta", 1)[1].split("}", 1)[0]
    assert "display: flex" in meta_rule
    assert "justify-content: space-between" in meta_rule

    mobile_css = css.split("@media (max-width: 600px)", 1)[1]
    mobile_popover_rule = mobile_css.split(".markdown-section .dpr-home-history-popover", 1)[1].split("}", 1)[0]
    assert "left: 0" in mobile_popover_rule
    assert "left: 50%" not in mobile_popover_rule
    assert "--dpr-home-history-x: 0" in mobile_popover_rule

    assert ".markdown-section .dpr-home-history:hover .dpr-home-history-popover" in css
    assert ".markdown-section .dpr-home-history:focus-within .dpr-home-history-popover" in css
    assert ".dpr-home-history-area" in css
    assert ".dpr-home-history-line" in css


def test_home_panels_share_a_quiet_visual_language():
    css = (ROOT / "app" / "app.css").read_text(encoding="utf-8")
    shared_selector = (
        ".markdown-section .dpr-home-notice-card,\n"
        ".markdown-section .dpr-home-promo-card"
    )
    assert shared_selector in css

    shared_rule = css.split(shared_selector, 1)[1].split("}", 1)[0]
    assert "background: #fbfcfb" in shared_rule
    assert "border: 1px solid #dfe7e2" in shared_rule
    assert "border-left" not in shared_rule
    assert "border-radius: 6px" in shared_rule
    assert "box-shadow: none" in shared_rule
    assert "gradient" not in shared_rule

    assert ".dpr-home-panel-header" in css
    assert ".dpr-home-notice-entry" in css
    assert ".dpr-home-promo-meta" in css

    panel_section = css.split("/* 首页信息面板", 1)[1].split("/* 侧边栏字体放大", 1)[0]
    assert "gradient" not in panel_section
    assert "::before" not in panel_section
    assert "::after" not in panel_section


def test_supabase_site_reader_stats_sql_is_least_privilege():
    sql = (ROOT / "sql" / "create_site_reader_stats_schema.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists public.site_daily_reader_events" in sql
    assert "create table if not exists public.site_daily_reader_counts" in sql
    assert "alter table public.site_daily_reader_events enable row level security" in sql
    assert "alter table public.site_daily_reader_counts enable row level security" in sql
    assert "create schema if not exists private" in sql
    assert "create or replace function private.increment_site_daily_reader_count" in sql
    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert "grant insert on public.site_daily_reader_events to anon, authenticated" in sql
    assert "grant select on public.site_daily_reader_counts to anon, authenticated" in sql
    assert "for insert" in sql and "with check" in sql
    assert "asia/shanghai" in sql
    assert "visitor_hash ~ '^[a-f0-9]{64}$'" in sql
    assert "grant select on public.site_daily_reader_events to anon" not in sql
