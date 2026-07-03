# Serenity Tracker

追蹤 **[Serenity (@aleabitoreddit)](https://x.com/aleabitoreddit)**（AI 半導體供應鏈分析師）在 X 的公開股票觀點：每小時抓新貼文 → LLM 抽取被提及的股票 ticker 並分類看多／看空／中立 → 累積成可搜尋的歷史弧線 → 互動式 dashboard 部署在 GitHub Pages。

🔗 **Live Dashboard**: https://cadmusyiu.github.io/serenity-tracker/

## 架構

```
[SocialData API] → fetcher ─┐
                             ├→ classify (Z.AI LLM) → merge → data/mentions.jsonl
                             │                                     │
                             │                          build ←────┘ (聚合)
                             │                              │
                             │                   dashboard (Jinja2)
                             │                              │
                             └─────────────────→ docs/ → GitHub Pages
                          GH Actions 每小時 :07 觸發
```

## 模組

| 檔案 | 職責 |
|------|------|
| `src/fetcher.py` | SocialData.tools 後端 API（可插拔 `Fetcher` protocol） |
| `src/classify.py` | Z.AI (Anthropic-compatible) LLM 抽 ticker + 分類立場 |
| `src/merge.py` | 去重合併進 `mentions.jsonl` + 維護 `state.json` |
| `src/build.py` | 聚合（日/週/月/季）|
| `src/dashboard.py` | Jinja2 渲染主頁 + 每股 detail 頁 |
| `src/main.py` | 編排器（`--sample` 用假資料；否則跑 live 管線） |

## 本機跑

```bash
pip install -r requirements.txt
python tests/test_logic.py        # 13 個單元測試
python src/main.py --sample       # 用 sample/ 假資料產 dashboard → docs/
open docs/index.html
```

## Phase 2：接真實資料

設三個 repo secrets（`gh secret set` 或 GH 設定頁）：

- `SOCIALDATA_API_KEY` — https://socialdata.tools 註冊 + 充值（$0.0002/tweet）
- `ZAI_API_KEY` — https://z.ai 的 key
- `ZAI_BASE_URL` — 預設 `https://api.z.ai/api/anthropic`
- `ZAI_MODEL` — 如 `glm-4.6`

設好後 `workflow_dispatch` 手動觸發一次驗證全鏈路，確認無誤即每小時 cron 自動跑。

## ⚠️ 免責聲明

立場標籤（看多／看空／中立）為 **AI 推斷**，可能不準。僅彙整公開貼文，**非投資建議**。本工具與 Serenity 無任何關聯，純研究用途。一切請回[原文](https://x.com/aleabitoreddit)並獨立查證。
