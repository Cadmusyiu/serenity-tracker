"""Classify — 用 LLM 從貼文抽取股票 ticker 並分類多頭/空頭/中立。

Z.AI 為 Anthropic-compatible，用 anthropic SDK 設 base_url + api_key。
結構化輸出靠 prompt 強制 JSON + 容錯 parse。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

VALID_STANCES = {"bullish", "bearish", "neutral"}

# 常見 ticker 口語 alias → 正規代碼
TICKER_ALIASES = {
    "NVIDIA": "NVDA",
    "TSMC": "TSM",
    "台積電": "TSM",
    "GOOGLE": "GOOGL",
    "META PLATFORMS": "META",
}


@dataclass
class Mention:
    tweet_id: str
    tweet_url: str
    created_at: str
    text: str
    ticker: str
    stance: str  # bullish | bearish | neutral
    rationale: str
    ingested_at: str = ""


def normalize_ticker(raw: str) -> str:
    """正規化 ticker：去 $ 前綴、大寫、查 alias 表。"""
    if not raw:
        return ""
    t = raw.strip().upper().lstrip("$").strip()
    return TICKER_ALIASES.get(t, t)


def parse_mentions_json(raw_text: str) -> List[dict]:
    """從 LLM 回應容錯抽取 mentions 陣列。

    處理：純 JSON、markdown code fence 包裹、JSON 夾雜說明文字。
    """
    if not raw_text:
        return []
    text = raw_text.strip()

    # 去 markdown code fence
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    # 直接 parse
    try:
        return _extract_mentions(json.loads(text))
    except json.JSONDecodeError:
        pass

    # 抽第一個 {...} 區塊
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return _extract_mentions(json.loads(m.group(0)))
        except json.JSONDecodeError:
            pass
    return []


def _extract_mentions(obj) -> List[dict]:
    if isinstance(obj, dict) and "mentions" in obj:
        return obj["mentions"] if isinstance(obj["mentions"], list) else []
    if isinstance(obj, list):
        return obj  # 直接是陣列形式
    return []


SYSTEM_PROMPT = """你是股市分析助手。以下來自 @aleabitoreddit (Serenity，AI 半導體供應鏈分析師) 的 X 貼文，
請抽取她「明確提及」的股票，並判斷她對每支的立場。

規則：
- ticker：美股代碼大寫（NVDA、SIVE、AXTI...），去 $ 前綴。只取明確點名的公司股票，不猜測。
- stance：bullish=看多/看好/買點；bearish=看空/風險/做空；neutral=僅提及/中性觀察
- rationale：一句話中文說明她為何這樣看

只回 JSON，不要任何額外說明文字：
{"mentions":[{"ticker":"...","stance":"bullish|bearish|neutral","rationale":"..."}]}
若該貼文無提及任何股票，回 {"mentions":[]}"""


def _client():
    """建立 Z.AI Anthropic-compatible client。"""
    from anthropic import Anthropic

    return Anthropic(
        base_url=os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/anthropic"),
        api_key=os.environ.get("ZAI_API_KEY"),
    )


def classify_tweet(tweet, model: Optional[str] = None) -> List[Mention]:
    """分類單篇貼文 → 0~多個 Mention。tweet 需有 id/text/created_at/url 屬性。"""
    if model is None:
        model = os.environ.get("ZAI_MODEL", "glm-4.6")
    client = _client()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f'貼文：\n"""\n{tweet.text}\n"""'}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    parsed = parse_mentions_json(raw)
    now = datetime.now(timezone.utc).isoformat()
    mentions: List[Mention] = []
    for m in parsed:
        ticker = normalize_ticker(m.get("ticker", ""))
        stance = (m.get("stance") or "").strip().lower()
        if not ticker or stance not in VALID_STANCES:
            continue
        mentions.append(
            Mention(
                tweet_id=tweet.id,
                tweet_url=tweet.url,
                created_at=tweet.created_at,
                text=tweet.text,
                ticker=ticker,
                stance=stance,
                rationale=(m.get("rationale") or "").strip(),
                ingested_at=now,
            )
        )
    return mentions


def classify_tweets(tweets, model: Optional[str] = None) -> List[Mention]:
    """批次分類多篇貼文（逐篇呼叫，穩定優先）。"""
    all_mentions: List[Mention] = []
    for tw in tweets:
        try:
            all_mentions.extend(classify_tweet(tw, model=model))
        except Exception as e:  # 單篇失敗不中斷整批
            print(f"[classify] tweet {getattr(tw, 'id', '?')} failed: {e}")
    return all_mentions
