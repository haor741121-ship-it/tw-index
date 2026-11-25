import json
import math
import random
import re
from datetime import datetime, timedelta, timezone
import requests

TARGET_HTML = "gemini-tw-index.html"
SNAPSHOT_ID = "gemini-snapshot"

TZ_TPE = timezone(timedelta(hours=8))
NOW = datetime.now(TZ_TPE)
TODAY_STR = NOW.strftime("%Y-%m-%d")
SHORT_DATE_STR = NOW.strftime("%m/%d")
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
        "range": "待 22 日模擬區間",
        "annualVol": 0.22,
        "annualDrift": 0.08,
        "horizonDays": 22,
        "targetPct": 0.0,
        "desc": "追蹤台灣50指數，與大盤高度連動，受權值電子與費半波動影響大。",
    },
    {
        "code": "00878 國泰永續高股息",
        "winRate": None,
        "refPrice": "待排程更新",
        "range": "待 22 日模擬區間",
        "annualVol": 0.14,
        "annualDrift": 0.06,
        "horizonDays": 22,
        "targetPct": 0.0,
        "desc": "高股息成分股含金融與傳產，波動通常低於純市值型標的（需納入除息調整）。",
    },
    {
        "code": "8086 宏捷科",
        "winRate": None,
        "refPrice": "待排程更新",
        "range": "待 22 日模擬區間",
        "annualVol": 0.42,
        "annualDrift": 0.05,
        "horizonDays": 22,
        "targetPct": 0.0,
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


def fetch_usd_twd() -> float | None:
    """自動抓取美元兌新台幣匯率（先試鉅亨網 FX，再試 Frankfurter 公開 API）"""
    try:
        url1 = "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/FX:USD:TWD"
        r1 = requests.get(url1, timeout=8)
        r1.raise_for_status()
        for row in r1.json().get("data", []):
            if row.get("0") == "FX:USD:TWD" and row.get("6") is not None:
                val = float(row["6"])
                if 25.0 <= val <= 40.0:
                    return round(val, 2)
    except Exception as exc:
        print(f"[WARN] 鉅亨網 USD/TWD 抓取失敗，改試備援匯率 API: {exc}")

    try:
        url2 = "https://api.frankfurter.app/latest?from=USD&to=TWD"
        r2 = requests.get(url2, timeout=8)
        r2.raise_for_status()
        rate = r2.json().get("rates", {}).get("TWD")
        if rate is not None:
            val = float(rate)
            if 25.0 <= val <= 40.0:
                return round(val, 2)
    except Exception as exc:
        print(f"[WARN] 備援 USD/TWD 抓取失敗，保留既有匯率: {exc}")

    return None


def _parse_num(raw) -> float | None:
    if raw is None:
        return None
    cleaned = str(raw).replace(",", "").replace("%", "").replace("億", "").replace("張", "").strip()
    if not cleaned or cleaned in {"-", "--", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_twse_margin(existing_margin: dict) -> dict:
    """嘗試從證交所 MI_MARGN 抓取上市融資融券餘額與維持率，失敗則安全保留既有值"""
    out = {**DEFAULT_MARGIN, **(existing_margin or {})}
    date_compact = NOW.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/margin/MI_MARGN?date={date_compact}&selectType=ALL&response=json"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("stat") != "OK":
            return out

        tables = payload.get("tables", [])
        for tbl in tables:
            fields = tbl.get("fields", [])
            rows = tbl.get("data", [])
            if not fields or not rows:
                continue
            joined_fields = "".join(str(x) for x in fields)
            if "融資" in joined_fields and "融券" in joined_fields and len(rows) >= 2:
                row_amt = rows[0]
                row_sh = rows[1]
                if len(row_amt) >= 6:
                    prev_amt_yi = (_parse_num(row_amt[4]) or 0.0) / 100000.0
                    curr_amt_yi = _parse_num(row_amt[5])
                    if curr_amt_yi is not None:
                        curr_amt_yi = round(curr_amt_yi / 100000.0, 2)
                        diff_amt = round(curr_amt_yi - prev_amt_yi, 2)
                        sign = "+" if diff_amt >= 0 else ""
                        out["marginBalance"] = curr_amt_yi
                        out["marginBalanceChg"] = f"{sign}{diff_amt:.2f}億"
                        out["date"] = SHORT_DATE_STR
                if len(row_sh) >= 6:
                    prev_sh = _parse_num(row_sh[4])
                    curr_sh = _parse_num(row_sh[5])
                    if curr_sh is not None:
                        out["shortBalance"] = int(round(curr_sh))
                        if prev_sh is not None:
                            diff_sh = int(round(curr_sh - prev_sh))
                            sign = "+" if diff_sh >= 0 else ""
                            out["shortBalanceChg"] = f"{sign}{diff_sh:,}張"
                        out["date"] = SHORT_DATE_STR
            elif "維持率" in joined_fields:
                for r in rows:
                    line = " ".join(str(x) for x in r)
                    if "大盤" in line or "整體" in line or "維持率" in line:
                        for cell in r:
                            num = _parse_num(cell)
                            if num is not None and 80.0 <= num <= 250.0:
                                out["maintenanceRatio"] = round(num, 2)
                                out["date"] = SHORT_DATE_STR
                                break
        return out
    except Exception as exc:
        print(f"[WARN] 證交所融資融券／維持率抓取略過，保留既有值: {exc}")
        return out


def compute_win_stats(item: dict, seed_salt: int = 20261125) -> dict:
    """依標的年化波動率、漂移率、持有日數與目標漲幅計算勝率與預期區間"""
    updated_item = dict(item)
    vol = float(updated_item.get("annualVol") or 0.25)
    drift = float(updated_item.get("annualDrift") or 0.06)
    days = int(updated_item.get("horizonDays") or 22)
    target_pct = float(updated_item.get("targetPct") or 0.0)

    dt = days / 252.0
    mu_dt = (drift - 0.5 * vol * vol) * dt
    sig_dt = vol * math.sqrt(dt)

    rng = random.Random(f"{updated_item.get('code', '')}-{seed_salt}")
    wins = 0
    returns = []
    n_sim = 4000
    for _ in range(n_sim):
        z = rng.gauss(0.0, 1.0)
        ret = math.exp(mu_dt + sig_dt * z) - 1.0
        returns.append(ret)
        if ret >= target_pct:
            wins += 1

    returns.sort()
    p10 = returns[int(0.10 * (n_sim - 1))] * 100.0
    p90 = returns[int(0.90 * (n_sim - 1))] * 100.0
    win_rate = round((wins / n_sim) * 100.0, 1)

    updated_item["winRate"] = win_rate
    s10 = "+" if p10 >= 0 else ""
    s90 = "+" if p90 >= 0 else ""
    updated_item["range"] = f"{days}日P10~P90：{s10}{p10:.1f}% ~ {s90}{p90:.1f}%"
    return updated_item


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
    fx_val = fetch_usd_twd()

    if close_val is not None and prev_val is not None:
        snap["taiexClose"] = close_val
        snap["taiexPrev"] = prev_val
    else:
        print("[INFO] 保留既有 taiexClose 與 taiexPrev")

    if fx_val is not None:
        snap["usdTwd"] = fx_val

    hist = snap.get("history10d")
    if not isinstance(hist, list) or len(hist) == 0:
        hist = [dict(item) for item in DEFAULT_HISTORY_10D]
    hist = hist[-10:]
    if isinstance(snap.get("taiexClose"), (int, float)):
        hist[-1]["taiex"] = snap["taiexClose"]
    if fx_val is not None:
        hist[-1]["usdTwd"] = fx_val
    snap["history10d"] = hist

    existing_margin = snap.get("margin") if isinstance(snap.get("margin"), dict) else {}
    snap["margin"] = fetch_twse_margin(existing_margin)

    win_items = snap.get("win")
    if not isinstance(win_items, list) or len(win_items) == 0:
        win_items = [dict(item) for item in DEFAULT_WIN_ITEMS]
    salt = int(NOW.strftime("%Y%m%d"))
    snap["win"] = [compute_win_stats(w, seed_salt=salt) for w in win_items]
    snap["winMeta"] = f"排程同步時間：{TIME_STR}｜22 日模擬勝率與 P10~P90 區間"
    snap["updated"] = TIME_STR

    new_html = replace_snapshot_json(html, SNAPSHOT_ID, snap)
    with open(TARGET_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"已更新 {TARGET_HTML}（#{SNAPSHOT_ID}）於 {TIME_STR}")


if __name__ == "__main__":
    main()
