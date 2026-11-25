import json
import re
from datetime import datetime, timezone, timedelta
import requests

TARGET_HTML = "gemini-tw-index.html"
SNAPSHOT_ID = "gemini-snapshot"

TZ_TPE = timezone(timedelta(hours=8))
NOW = datetime.now(TZ_TPE)
TODAY_STR = NOW.strftime("%Y-%m-%d")
TIME_STR = NOW.strftime("%Y-%m-%d %H:%M")

# 證交所非週末休市日（2026 剩餘與 2027 元旦，後續依公告補充）
HOLIDAYS = {
    "2026-12-25",
    "2027-01-01",
}


def should_skip(dt: datetime) -> tuple[bool, str]:
    if dt.weekday() >= 5:
        return True, f"今天台北時間 {TODAY_STR} 為週末休市，本輪跳過"
    if TODAY_STR in HOLIDAYS:
        return True, f"今天台北時間 {TODAY_STR} 為國定假日休市，本輪跳過"
    return False, ""


def fetch_taiex_close() -> tuple[float | None, float | None]:
    """從鉅亨網報價 API 取得加權指數現價／收盤與昨收，失敗時回傳 (None, None)"""
    url = "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/TWS:TSE01:INDEX"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        for row in rows:
            if row.get("0") == "TWS:TSE01:INDEX":
                close_val = row.get("6")
                prev_val = row.get("21")
                if close_val is not None and prev_val is not None:
                    return float(close_val), float(prev_val)
        return None, None
