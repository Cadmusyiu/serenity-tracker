"""單元測試 — 純邏輯層（不需 API keys）。

涵蓋：
- parse_mentions_json 容錯（純 JSON / code fence / 夾雜文字 / 空 / 陣列形式）
- normalize_ticker 正規化（$sive → SIVE、台積電 → TSM）
- merge 去重（同 tweet_id+ticker+stance 不重複）
- build.aggregate 區間計數

可用 pytest 跑，或直接 `python tests/test_logic.py`。
"""
import os
import sys
import inspect
import tempfile
from pathlib import Path

# 讓測試能 import src 模組
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from classify import (  # noqa: E402
    Mention,
    normalize_ticker,
    parse_mentions_json,
)
from merge import load_mentions, merge, mention_key  # noqa: E402
from build import aggregate  # noqa: E402


# ---------- parse_mentions_json ----------
def test_parse_plain_json():
    raw = '{"mentions":[{"ticker":"NVDA","stance":"bullish","rationale":"x"}]}'
    out = parse_mentions_json(raw)
    assert len(out) == 1
    assert out[0]["ticker"] == "NVDA"


def test_parse_code_fence():
    raw = '```json\n{"mentions":[{"ticker":"TSM","stance":"bearish","rationale":"y"}]}\n```'
    out = parse_mentions_json(raw)
    assert len(out) == 1
    assert out[0]["ticker"] == "TSM"


def test_parse_with_surrounding_text():
    raw = '好的，以下是結果：\n{"mentions":[{"ticker":"SIVE","stance":"neutral","rationale":"z"}]}\n希望有幫助'
    out = parse_mentions_json(raw)
    assert len(out) == 1
    assert out[0]["ticker"] == "SIVE"


def test_parse_empty_mentions():
    assert parse_mentions_json('{"mentions":[]}') == []
    assert parse_mentions_json("") == []
    assert parse_mentions_json("not json at all") == []


def test_parse_array_form():
    # LLM 偶爾直接回陣列而非包在 {mentions:...}
    raw = '[{"ticker":"NVDA","stance":"bullish","rationale":"a"}]'
    out = parse_mentions_json(raw)
    assert len(out) == 1


# ---------- normalize_ticker ----------
def test_normalize_strips_dollar_and_uppercases():
    assert normalize_ticker("$sive") == "SIVE"
    assert normalize_ticker(" nvda ") == "NVDA"


def test_normalize_alias():
    assert normalize_ticker("$TSMC") == "TSM"
    assert normalize_ticker("台積電") == "TSM"
    assert normalize_ticker("NVIDIA") == "NVDA"


def test_normalize_empty():
    assert normalize_ticker("") == ""
    assert normalize_ticker(None) == ""  # type: ignore


# ---------- merge dedup ----------
def _mk(tid, ticker, stance="bullish"):
    return Mention(
        tweet_id=tid, tweet_url="https://x.com/x/status/" + tid,
        created_at="2026-07-01T00:00:00Z", text="...", ticker=ticker,
        stance=stance, rationale="...", ingested_at="",
    )


def test_merge_dedup_same_key(tmp_path):
    p = str(tmp_path / "m.jsonl")
    first = merge([_mk("100", "NVDA", "bullish")], p)
    again = merge([_mk("100", "NVDA", "bullish")], p)  # 完全相同 key → 跳過
    assert first == 1
    assert again == 0
    assert len(load_mentions(p)) == 1


def test_merge_keeps_different_stance(tmp_path):
    p = str(tmp_path / "m.jsonl")
    a = merge([_mk("100", "NVDA", "bullish")], p)
    b = merge([_mk("100", "NVDA", "bearish")], p)  # 同貼文同股但立場不同 → 算新
    assert a == 1
    assert b == 1
    assert len(load_mentions(p)) == 2


def test_merge_keeps_different_ticker(tmp_path):
    p = str(tmp_path / "m.jsonl")
    a = merge([_mk("100", "NVDA", "bullish")], p)
    b = merge([_mk("100", "TSM", "bullish")], p)  # 同貼文不同股 → 新
    assert a == 1
    assert b == 1
    assert len(load_mentions(p)) == 2


def test_mention_key_format():
    assert mention_key(_mk("9", "NVDA", "bearish")) == "9|NVDA|bearish"


# ---------- aggregate windows ----------
def test_aggregate_counts_and_sort():
    mentions = [
        _mk("1", "SIVE", "bullish"),   # created_at 固定 2026-07-01
        _mk("2", "SIVE", "bearish"),
        _mk("3", "NVDA", "bullish"),
    ]
    data = aggregate(mentions)
    tickers = [s["ticker"] for s in data["stocks"]]
    assert set(tickers) == {"SIVE", "NVDA"}
    sive = next(s for s in data["stocks"] if s["ticker"] == "SIVE")
    assert sive["count"] == 2
    assert sive["stance_counts"]["bullish"] == 1
    assert sive["stance_counts"]["bearish"] == 1
    assert data["total_mentions"] == 3


if __name__ == "__main__":
    # 不依賴 pytest 也能跑：收集本模組內 test_ 開頭函式逐一執行
    g = globals()
    failures = 0
    for name, fn in list(g.items()):
        if name.startswith("test_") and callable(fn):
            params = inspect.signature(fn).parameters
            try:
                if "tmp_path" in params:
                    fn(tmp_path=Path(tempfile.mkdtemp()))
                else:
                    fn()
                print(f"✅ {name}")
            except AssertionError as e:
                failures += 1
                print(f"❌ {name}: {e}")
    print(f"\n{'全綠' if not failures else '有失敗'} ({failures} failed)")
    sys.exit(1 if failures else 0)
