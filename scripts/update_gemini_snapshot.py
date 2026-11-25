import json
import math
import random
import re
from datetime import datetime, timedelta, timezone
import requests

TARGET_HTML = "gemini-tw-index.html"
SNAPSHOT_ID = "gemini-snapshot"
TWD_FX_BASE = 32.5

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
    {"date": "11/11", "taiex": None, "twdIndex": None},
    {"date": "11/12", "taiex": None, "twdIndex": None},
    {"date": "11/13", "taiex": None, "twdIndex": None},
    {"date": "11/16", "taiex": None, "twdIndex": None},
    {"date": "11/17", "taiex": None, "twdIndex": None},
    {"date": "11/18", "taiex": None, "twdIndex": None},
    {"date": "11/19", "taiex": None, "twdIndex": None},
    {"date": "11/20", "taiex": None, "twdIndex": None},
    {"date": "11/23", "taiex": None, "twdIndex": None},
    {"date": "11/24", "taiex": 40122.35, "twdIndex": None},
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
        "winRate": 53.8,
        "range": "20日可能區間：-7.9% ~ +9.7%",
        "annualVol": 0.24,
        "annualDrift": 0.09,
        "horizonDays": 20,
        "targetPct": 0.0,
        "desc": "與大盤高度連動，波動與預期報酬適中。",
    },
    {
        "code": "00878 國泰永續高股息",
        "winRate": 55.1,
        "range": "20日可能區間：-4.1% ~ +5.4%",
        "annualVol": 0.13,
        "annualDrift": 0.065,
        "horizonDays": 20,
        "targetPct": 0.0,
        "desc": "波動最小、短線較抗震，三檔中勝率最高。",
    },
    {
        "code": "8086 宏捷科",
        "winRate": 50.2,
        "range": "20日可能區間：-15.4% ~ +17.9%",
        "annualVol": 0.45,
        "annualDrift": 0.07,
        "horizonDays": 20,
        "targetPct": 0.0,
        "desc": "個股振幅大，20 日賺賠接近五五波，上下波動最劇烈。",
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


def fetch_cnyes_twd_index(fx_base: float = TWD_FX_BASE) -> float | None:
    """從鉅亨網外匯報價 API 抓取 USD/TWD 並換算為台幣指數（基期 32.50 = 100）"""
    url = "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/FX:USD:TWD"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        for row in rows:
            if row.get("0") == "FX:USD:TWD" and row.get("6") is not None:
                fx_val = float(row["6"])
                if 25.0 <= fx_val <= 40.0 and fx_base > 0:
                    return round((fx_base / fx_val) * 100.0, 2)
        return None
    except Exception as exc:
        print(f"[WARN] 無法從鉅亨網取得台幣指數，保留原快照數值: {exc}")
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
    """依標的年化波動率、漂移率、持有日數與目標漲幅計算勝率與可能漲跌區間"""
    updated_item = dict(item)
    vol = float(updated_item.get("annualVol") or 0.24)
    drift = float(updated_item.get("annualDrift") or 0.07)
    days = int(updated_item.get("horizonDays") or 20)
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
    updated_item["range"] = f"{days}日可能區間：{s10}{p10:.1f}% ~ {s90}{p90:.1f}%"
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
    fx_base = float(snap.get("twdFxBase") or TWD_FX_BASE)
    close_val, prev_val = fetch_taiex_close()
    twd_idx_val = fetch_cnyes_twd_index(fx_base=fx_base)

    if close_val is not None and prev_val is not None:
        snap["taiexClose"] = close_val
        snap["taiexPrev"] = prev_val
    else:
        print("[INFO] 保留既有 taiexClose 與 taiexPrev")

    if twd_idx_val is not None:
        snap["twdIndex"] = twd_idx_val

    hist = snap.get("history10d")
    if not isinstance(hist, list) or len(hist) == 0:
        hist = [dict(item) for item in DEFAULT_HISTORY_10D]
    hist = hist[-10:]
    if isinstance(snap.get("taiexClose"), (int, float)):
        hist[-1]["taiex"] = snap["taiexClose"]
    if twd_idx_val is not None:
        hist[-1]["twdIndex"] = twd_idx_val
    snap["history10d"] = hist

    existing_margin = snap.get("margin") if isinstance(snap.get("margin"), dict) else {}
    snap["margin"] = fetch_twse_margin(existing_margin)

    default_map = {item["code"]: item for item in DEFAULT_WIN_ITEMS}
    win_items = snap.get("win")
    if not isinstance(win_items, list) or len(win_items) == 0:
        win_items = [dict(item) for item in DEFAULT_WIN_ITEMS]
    else:
        merged_win = []
        for w in win_items:
            base = dict(default_map.get(w.get("code"), {}))
            base.update({
                k: v for k, v in w.items()
                if k not in {"annualVol", "annualDrift", "horizonDays", "targetPct"}
            })
            merged_win.append(base)
        win_items = merged_win

    salt = int(NOW.strftime("%Y%m%d"))
    snap["win"] = [compute_win_stats(w, seed_salt=salt) for w in win_items]
    snap["winMeta"] = f"排程同步：{TIME_STR}｜現在買進、持有 20 個交易日勝率"
    snap["updated"] = TIME_STR

    new_html = replace_snapshot_json(html, SNAPSHOT_ID, snap)
    with open(TARGET_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"已更新 {TARGET_HTML}（#{SNAPSHOT_ID}）於 {TIME_STR}")


if __name__ == "__main__":
    main()
