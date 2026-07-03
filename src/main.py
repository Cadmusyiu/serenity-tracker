"""Main — 編排器：fetch → classify → merge → build。

Phase 1（--sample）：用 sample/mentions.jsonl 直接 build dashboard，不需 keys。
Phase 2（live）：跑完整管線，每小時由 GH Actions cron 觸發。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# 讓 `python src/main.py` 也能 import 同層模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HANDLE = "aleabitoreddit"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SAMPLE_PATH = os.path.join(ROOT, "sample", "mentions.jsonl")
MENTIONS_PATH = os.path.join(DATA_DIR, "mentions.jsonl")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
DOCS_DIR = os.path.join(ROOT, "docs")


def run_sample() -> None:
    """Phase 1：用 sample 資料 build dashboard。"""
    from build import build

    print("✅ [sample] building dashboard from sample data...")
    data = build(SAMPLE_PATH, DOCS_DIR, handle=HANDLE)
    print(f"✅ [sample] done. {data['total_mentions']} mentions, {len(data['stocks'])} stocks → {DOCS_DIR}")


def run_live() -> None:
    """Phase 2：完整管線 fetch → classify → merge → build。"""
    from build import build
    from classify import classify_tweets
    from fetcher import SocialDataFetcher
    from merge import load_state, merge, save_state

    fetcher = SocialDataFetcher()
    state = load_state(STATE_PATH)
    since_id = state.get("since_id")

    print(f"💬 [live] fetching @{HANDLE} (since_id={since_id or 'none'})...")
    tweets = fetcher.fetch_recent(HANDLE, since_id=since_id)
    print(f"💬 [live] fetched {len(tweets)} new tweets")

    if not tweets:
        print("🌐 [live] no new tweets; skipping classify/build")
        return

    print(f"📜 [live] classifying {len(tweets)} tweets via Z.AI...")
    mentions = classify_tweets(tweets)

    added = merge(mentions, MENTIONS_PATH)
    print(f"📜 [live] merged {added} new mentions into {MENTIONS_PATH}")

    # since_id 用數值最大的 tweet id（字串比較對 snowflake id 等價數值比較）
    latest_id = max(t.id for t in tweets)
    save_state(STATE_PATH, latest_id, datetime.now(timezone.utc).isoformat())
    print(f"✅ [live] state updated since_id={latest_id}")

    data = build(MENTIONS_PATH, DOCS_DIR, handle=HANDLE)
    print(f"✅ [live] dashboard rebuilt. {data['total_mentions']} total mentions, {len(data['stocks'])} stocks")


def main() -> None:
    p = argparse.ArgumentParser(description="Serenity X tracker")
    p.add_argument("--sample", action="store_true", help="用 sample 資料 build dashboard（不需 keys）")
    args = p.parse_args()

    if args.sample:
        run_sample()
    else:
        run_live()


if __name__ == "__main__":
    main()
