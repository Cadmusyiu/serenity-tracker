"""Merge — 去重合併進 mentions.jsonl + 維護增量狀態 state.json。

去重 key = tweet_id|ticker|stance（同一貼文對同一股票同一立場只留一筆）。
原子寫入（temp → rename）避免 Actions 中斷造成損毀。
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import List, Set

from classify import Mention


def mention_key(m: Mention) -> str:
    return f"{m.tweet_id}|{m.ticker}|{m.stance}"


def load_mentions(path: str) -> List[Mention]:
    """讀 JSONL → List[Mention]。檔不存在或空檔回 []。"""
    mentions: List[Mention] = []
    if not os.path.exists(path):
        return mentions
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                mentions.append(Mention(**obj))
            except (json.JSONDecodeError, TypeError):
                continue
    return mentions


def existing_keys(mentions: List[Mention]) -> Set[str]:
    return {mention_key(m) for m in mentions}


def merge(new_mentions: List[Mention], path: str) -> int:
    """Append 新 mention（跳過已存在的 key），回傳實際新增筆數。"""
    seen = existing_keys(load_mentions(path))
    added = 0
    # 確保目錄存在
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for m in new_mentions:
            k = mention_key(m)
            if k in seen:
                continue
            seen.add(k)
            obj = {
                "tweet_id": m.tweet_id,
                "tweet_url": m.tweet_url,
                "created_at": m.created_at,
                "text": m.text,
                "ticker": m.ticker,
                "stance": m.stance,
                "rationale": m.rationale,
                "ingested_at": m.ingested_at,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            added += 1
    return added


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(path: str, since_id: str, last_run: str) -> None:
    """原子寫入 state.json（temp → rename）。"""
    payload = {"since_id": since_id, "last_run": last_run}
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
