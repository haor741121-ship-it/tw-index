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

DEFAULT_HISTORY_10D = [
    {"date": "11/11", "taiex": None, "usdTwd": None},
    {"date": "11/12", "taiex": None, "usdTwd": None},
    {"date": "11/13", "taiex": None, "usdTwd": None},
    {"date": "11/16", "taiex": None, "usdTwd": None},
    {"date": "11/17", "taiex": None, "usdTwd": None},
    {"date": "11/18", "taiex": None, "usdTwd": None},
    {"date": "11/19", "taiex": None, "usdTwd": None},
    {"date": "11/20", "taiex": None, "usdTwd": None},
    {"date": "11/23", "taiex": None, "usdTwd": None},
    {"date": "11/24", "taiex": 40122.35, "usdTwd": None},
]

DEFAULT_MARGIN = {
    "date": "11/24",
    "marginBalance": None,
    "marginBalanceChg": "+196.97億",
    "shortBalance": None,
    "shortBalanceChg": "+13,656張",
    "maintenanceRatio": None,
    "thresholdNote": "追繳門檻 120%",
}

DEFAULT_WIN_ITEMS = [
    {
        "code": "0050 元大台灣50",
        "winRate": None,
        "refPrice": "待排程更新",
        "range": "待 22 日對數報酬與模擬計算",
        "desc": "追蹤台灣50指數，與大盤高度連動，受權值電子與費半波動影響大。",
    },
    {
        "code": "00878 國泰永續高股息",
        "winRate": None,
        "refPrice": "待排程更新",
        "range": "待 22 日對數報酬與模擬計算",
        "desc": "高股息成分股含金融與傳產，波動通常低於純市值型標的（需納入除息調整）。",
    },
    {
        "code": "8086 宏捷科",
        "winRate": None,
        "refPrice": "待排程更新",
        "range": "待 22 日對數報酬與模擬計算",
        "desc": "砷化鎵晶圓代工族群，個股 Beta 與自有波動較高，受手機 PA 需求與美股半導體氣氛影響。",
    },
]


def should_skip(dt: datetime) -> tuple[bool, str]:
    if dt.weekday() >= 5:
        return True, f"今天台北時間 {TODAY_STR} 為週末休市，本輪跳過"
    if TODAY_STR in HOLIDAYS:
        return True, f"今天台北時間 {TODAY_STR} 為國定假日休市，本輪跳過"
    return False, ""


def fetch_taiex_close() -> tuple[float | None, float | None]:
    """從
