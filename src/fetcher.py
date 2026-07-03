"""Fetcher — 抓取目標 X 帳號的公開貼文。

可插拔設計：實作 Fetcher protocol 即可換資料來源
（SocialData → 官方 X API → Apify）。主流程只依賴 fetch_recent()。
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


class SocialDataFetcher:
    """SocialData.tools 後端爬蟲 API（$0.0002/tweet，pay-per-use，Bearer token）。

    依 docs.socialdata.tools：
      - 先 GET /twitter/user?username=... 取 user_id
      - 再 GET /twitter/user-tweets?user_id=... 取貼文（since_id 增量過濾）
    認證：header Authorization: Bearer <SOCIALDATA_API_KEY>
    實際 endpoint 欄位名以官方文件為準，實作時已對齊。
    """

    BASE = "https://socialdata.tools"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("SOCIALDATA_API_KEY")
        if not self.api_key:
            raise RuntimeError("SOCIALDATA_API_KEY not set")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _get(self, path: str, params: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
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
        username = username.lstrip("@")
        data = self._get("/twitter/user", {"username": username})
        uid = str((data.get("user") or {}).get("id") or data.get("id") or "")
        if not uid:
            raise RuntimeError(f"Cannot resolve user_id for @{username}")
        return uid

    def fetch_recent(self, handle: str, since_id: Optional[str] = None) -> List[RawTweet]:
        uid = self._user_id(handle)
        username = handle.lstrip("@")
        tweets: List[RawTweet] = []
        pagination_token: Optional[str] = None
        # 最多抓 2 頁（控制成本；增量情境下通常 1 頁即足夠）
        for _ in range(2):
            params: Dict[str, Any] = {"user_id": uid}
            if since_id:
                params["since_id"] = since_id
            if pagination_token:
                params["pagination_token"] = pagination_token
            data = self._get("/twitter/user-tweets", params)
            batch = data.get("tweets") or data.get("data") or []
            for t in batch:
                tid = str(t.get("id_str") or t.get("id") or "")
                if not tid:
                    continue
                text = t.get("full_text") or t.get("text") or ""
                created = t.get("createdAt") or t.get("created_at") or ""
                url = f"https://x.com/{username}/status/{tid}"
                tweets.append(RawTweet(id=tid, text=text, created_at=created, url=url))
            pagination_token = data.get("next_token") or data.get("pagination_token")
            if not pagination_token:
                break
        return tweets
