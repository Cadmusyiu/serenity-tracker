"""Dashboard — Jinja2 渲染主頁 + 每股 detail 頁。

繁中 UI + 英文 ticker/stance。
4-view 切換靠前端 JS filter（同一份資料，不重 build），立場 badge：🟢🔴⚪。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

STANCE_LABEL = {
    "bullish": "看多",
    "bearish": "看空",
    "neutral": "中立",
}
STANCE_EMOJI = {
    "bullish": "🟢",
    "bearish": "🔴",
    "neutral": "⚪",
}

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _fmt_dt(s: str) -> str:
    """ISO → 'YYYY-MM-DD HH:MM'（容錯）。"""
    if not s:
        return ""
    t = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return s[:16]


def render_dashboard(data: dict, out_dir: str, handle: str = "aleabitoreddit") -> None:
    env = _env()
    env.filters["stance_label"] = lambda s: STANCE_LABEL.get(s, s)
    env.filters["stance_emoji"] = lambda s: STANCE_EMOJI.get(s, "❓")
    env.filters["fmt_dt"] = _fmt_dt

    ctx = {
        "handle": handle,
        "display_name": "Serenity",
        "stocks": data["stocks"],
        "total_mentions": data["total_mentions"],
        "window_counts": data["window_counts"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    os.makedirs(out_dir, exist_ok=True)
    stocks_dir = os.path.join(out_dir, "stocks")
    os.makedirs(stocks_dir, exist_ok=True)

    # 主頁
    index_tmpl = env.get_template("index.html")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_tmpl.render(**ctx))

    # 每股 detail 頁
    stock_tmpl = env.get_template("stock.html")
    for s in data["stocks"]:
        with open(os.path.join(stocks_dir, f"{s['ticker']}.html"), "w", encoding="utf-8") as f:
            f.write(stock_tmpl.render(stock=s, handle=handle,
                                      display_name="Serenity",
                                      generated_at=ctx["generated_at"]))
