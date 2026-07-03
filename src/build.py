"""Build — 聚合 mentions → dashboard 資料模型。

4 區間：Daily(今)、Weekly(7d)、Monthly(28d)、Quarterly(90d)。
每股聚合：提及次數、首次/最後日期、最新 stance、stance 分佈、原文連結。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from classify import Mention
from dashboard import render_dashboard


def _parse_dt(s: str) -> datetime:
    """容錯解析 ISO 字串 → aware datetime（UTC）。"""
    if not s:
        return datetime.now(timezone.utc)
    t = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        # 嘗試常見的 Twitter 格式 "Thu Jun 12 10:00:00 +0000 2025"
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# 區間定義：key → 從現在起往前推的天數（None = 全部）
WINDOWS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 28,
    "quarterly": 90,
}


def aggregate(mentions: List[Mention]) -> dict:
    """聚合全部 mentions → 每股摘要（依最後提及時間排序）。

    回傳結構：
    {
      "stocks": [
        {
          "ticker", "count", "first_at", "last_at", "latest_stance",
          "stance_counts": {"bullish":n,"bearish":n,"neutral":n},
          "mentions": [ <Mention dict> 按時間倒序 ]
        }, ...
      ],
      "total_mentions": int,
      "window_counts": {"daily": n, "weekly": n, ...}
    }
    """
    now = datetime.now(timezone.utc)
    by_ticker: Dict[str, List[Mention]] = defaultdict(list)
    for m in mentions:
        by_ticker[m.ticker].append(m)

    stocks = []
    window_counts = {k: 0 for k in WINDOWS}
    for ticker, ms in by_ticker.items():
        ms_sorted = sorted(ms, key=lambda x: _parse_dt(x.created_at), reverse=True)
        stances = [x.stance for x in ms_sorted]
        stance_counts = {
            "bullish": stances.count("bullish"),
            "bearish": stances.count("bearish"),
            "neutral": stances.count("neutral"),
        }
        first = ms_sorted[-1]
        last = ms_sorted[0]
        stocks.append(
            {
                "ticker": ticker,
                "count": len(ms_sorted),
                "first_at": first.created_at,
                "last_at": last.created_at,
                "latest_stance": last.stance,
                "stance_counts": stance_counts,
                "mentions": [_mention_to_dict(x) for x in ms_sorted],
            }
        )
        # 累計各區間提及次數（以該股最後一次提及是否落在窗內計）
        for key, days in WINDOWS.items():
            if _parse_dt(last.created_at) >= now - timedelta(days=days):
                window_counts[key] += 1

    # 依最後提及時間倒序（最近活躍的在前）
    stocks.sort(key=lambda s: _parse_dt(s["last_at"]), reverse=True)

    return {
        "stocks": stocks,
        "total_mentions": len(mentions),
        "window_counts": window_counts,
    }


def _mention_to_dict(m: Mention) -> dict:
    return {
        "tweet_id": m.tweet_id,
        "tweet_url": m.tweet_url,
        "created_at": m.created_at,
        "text": m.text,
        "ticker": m.ticker,
        "stance": m.stance,
        "rationale": m.rationale,
    }


def build(mentions_path: str, out_dir: str, handle: str = "aleabitoreddit") -> dict:
    """主入口：讀 mentions → aggregate → render dashboard。回傳聚合結果。"""
    from merge import load_mentions

    mentions = load_mentions(mentions_path)
    data = aggregate(mentions)
    render_dashboard(data, out_dir, handle=handle)
    return data
