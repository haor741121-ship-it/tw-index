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
    except Exception as exc:
        print(f"[WARN] 無法取得加權指數報價，保留原快照數值: {exc}")
        return None, None


def replace_snapshot_json(html: str, script_id: str, data: dict) -> str:
    pattern = rf'(<script\s+id="{re.escape(script_id)}"[^>]*>)(.*?)(</script>)'
    pretty = "\n  " + json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\n  ") + "\n  "
    updated_html, count = re.subn(pattern, rf"\g<1>{pretty}\g<3>", html, count=1, flags=re.S)
    if count == 0:
        raise RuntimeError(f"找不到 #{script_id} 區塊")
    return updated_html


def main() -> None:
    skip, msg = should_skip(NOW)
    if skip:
        print(msg)
        return

    with open(TARGET_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    match = re.search(rf'<script\s+id="{SNAPSHOT_ID}"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise RuntimeError(f"{TARGET_HTML} 缺少 #{SNAPSHOT_ID}")

    snap = json.loads(match.group(1))
    close_val, prev_val = fetch_taiex_close()

    if close_val is not None and prev_val is not None:
        snap["taiexClose"] = close_val
        snap["taiexPrev"] = prev_val
    else:
        print("[INFO] 保留既有 taiexClose 與 taiexPrev")

    if not isinstance(snap.get("win"), list) or len(snap["win"]) == 0:
        snap["win"] = DEFAULT_WIN_ITEMS

    snap["winMeta"] = f"排程同步時間：{TIME_STR}｜0050 / 00878 / 8086 勝率追蹤"
    snap["updated"] = TIME_STR

    new_html = replace_snapshot_json(html, SNAPSHOT_ID, snap)
    with open(TARGET_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"已更新 {TARGET_HTML}（#{SNAPSHOT_ID}）於 {TIME_STR}")


if __name__ == "__main__":
    main()
