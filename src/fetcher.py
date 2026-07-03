"""Fetcher — 抓取目標 X 帳號的公開貼文。

可插拔設計：實作 Fetcher protocol 即可換資料來源
（SocialData → 官方 X API → Apify）。主流程只依賴 fetch_recent()。

SocialData.tools 實測確認（docs.socialdata.tools/reference）：
  - BASE = https://api.socialdata.tools  ← 注意是 api. 子域（socialdata.tools 是網站）
  - profile：GET /twitter/user/{username}            （path param，回傳含 id_str 的 profile 物件）
  - tweets ：GET /twitter/user/{user_id}/tweets?cursor=  （user_id 是數字；分頁用 cursor）
  - 認證：header Authorization: Bearer <SOCIALDATA_API_KEY>，建議附 Accept: application/json
  - tweet 正文用 full_text（text 欄位為 null）；時間用 tweet_created_at（已是 ISO 8601）
  - 增量：API 無 since_id，改 client 端用 snowflake id 數值比較過濾
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import requests


@dataclass
class RawTweet:
    id: str
    text: str
    created_at: str  # ISO 8601
    url: str


class Fetcher(Protocol):
    def fetch_recent(self, handle: str, since_id: Optional[str] = None) -> List[RawTweet]:
        ...


def _le(a: str, b: str) -> bool:
    """兩個 snowflake id（字串）的數值 <= 比較；非數字回 False（保守不過濾）。"""
    return a.isdigit() and b.isdigit() and int(a) <= int(b)


class SocialDataFetcher:
    """SocialData.tools 後端爬蟲 API（$0.0002/tweet，pay-per-use，Bearer token）。"""

    BASE = "https://api.socialdata.tools"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("SOCIALDATA_API_KEY")
        if not self.api_key:
            raise RuntimeError("SOCIALDATA_API_KEY not set")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict[str, Any]:
        url = f"{self.BASE}{path}"
        for attempt in range(retries):
            try:
                resp = self.s.get(url, params=params, timeout=30)
                if resp.status_code == 429:  # rate limit → 退避重試
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError):
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return {}

    def _user_id(self, username: str) -> str:
        """GET /twitter/user/{username} → user_id（數字字串）。"""
        username = username.lstrip("@")
        data = self._get(f"/twitter/user/{username}")
        uid = str(data.get("id_str") or data.get("id") or "")
        if not uid:
            raise RuntimeError(f"Cannot resolve user_id for @{username}")
        return uid

    def fetch_recent(self, handle: str, since_id: Optional[str] = None, max_pages: int = 2) -> List[RawTweet]:
        """抓 @{handle} 近期貼文（新→舊）。since_id 用於增量：跳過 id <= since_id 的舊文。

        timeline 由新到舊排序，遇到第一則 <= since_id 即停止（省成本）。
        """
        uid = self._user_id(handle)
        username = handle.lstrip("@")
        tweets: List[RawTweet] = []
        cursor: Optional[str] = None
        for _ in range(max_pages):
            params: Dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            data = self._get(f"/twitter/user/{uid}/tweets", params)
            batch = data.get("tweets") or []
            stop = False
            for t in batch:
                tid = str(t.get("id_str") or t.get("id") or "")
                if not tid:
                    continue
                if since_id and _le(tid, since_id):
                    stop = True  # 這則及之後都更舊
                    break
                text = t.get("full_text") or t.get("text") or ""
                created = t.get("tweet_created_at") or t.get("created_at") or ""
                url = f"https://x.com/{username}/status/{tid}"
                tweets.append(RawTweet(id=tid, text=text, created_at=created, url=url))
            if stop:
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return tweets
