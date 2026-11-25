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

HOLIDAYS = {
    "2026-12-25",
    "2027-01-01",
}

DEFAULT_HISTORY_10D = [
    {"date": "11/12", "taiex": None, "usdTwd": 32.94, "marginBal": 5334.75, "marginChg": -76.83, "shortBal": 210522, "shortChg": 1503, "maintenanceRatio": 167.22, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/13", "taiex": None, "usdTwd": 32.88, "marginBal": 5365.99, "marginChg": 31.24, "shortBal": 208773, "shortChg": -1749, "maintenanceRatio": 170.67, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/16", "taiex": 41040.08, "usdTwd": 32.96, "marginBal": 5244.98, "marginChg": -121.01, "shortBal": 217384, "shortChg": 8611, "maintenanceRatio": 158.50, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/17", "taiex": 40092.11, "usdTwd": 32.91, "marginBal": 5087.21, "marginChg": -157.77, "shortBal": 207959, "shortChg": -9425, "maintenanceRatio": 153.71, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/18", "taiex": 40194.91, "usdTwd": 32.93, "marginBal": 5080.27, "marginChg": -6.95, "shortBal": 193544, "shortChg": -14415, "maintenanceRatio": 156.22, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/19", "taiex": 38426.89, "usdTwd": 33.03, "marginBal": 4843.68, "marginChg": -236.58, "shortBal": 209819, "shortChg": 16275, "maintenanceRatio": 147.90, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/20", "taiex": 36033.29, "usdTwd": 32.95, "marginBal": 4352.27, "marginChg": -491.41, "shortBal": 199791, "shortChg": -10028, "maintenanceRatio": 140.40, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/23", "taiex": 36811.89, "usdTwd": 32.85, "marginBal": 4338.08, "marginChg": -14.20, "shortBal": 172957, "shortChg": -26834, "maintenanceRatio": 148.46, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/24", "taiex": 40122.35, "usdTwd": 32.94, "marginBal": 4535.05, "marginChg": 196.97, "shortBal": 186613, "shortChg": 13656, "maintenanceRatio": None, "foreign": -503.90, "trust": 84.04, "dealer": -826.12, "instTotal": -1230.11},
    {"date": "11/25", "taiex": 38195.43, "usdTwd": 33.13, "marginBal": None, "marginChg": None, "shortBal": None, "shortChg": None, "maintenanceRatio": None, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
]

DEFAULT_NEWS = {
    "bullish": [
        "【政策・金融】證交所自 2026/11/24 起將信用交易擔保維持率最低標準由 130% 調降至 120%，並取消 11/24 前低於 130% 追繳紀錄與處分，緩解槓桿斷頭壓力。",
        "【國際】黃仁勳回任輝達執行長一度帶動全球與台股出現強彈，顯示 AI 算力與晶片龍頭話題仍具市場關注度。",
    ],
    "bearish": [
        "【國際・半導體】隔夜費城半導體指數重挫近 8%，亞股與半導體供應鏈同步承壓，11/25 台股盤中一度重挫逾 3,400 點、收跌 1,926.92 點。",
        "【政策・關稅】美國 301 關稅與新關稅措施雜音升溫，加上外資現貨調節與期貨空單部位偏高，壓抑外資風險偏好。",
        "【能源・金融】全球能源價格、匯率波動與金融市場避險情緒升溫，資金在劇烈震盪下傾向縮減高 Beta 風險部位。",
    ],
    "summary": "總結：短期政策調降維持率至 120% 發揮防斷頭緩衝作用，但國際半導體修正、美方關稅變數與外資籌碼尚未明朗前，大盤仍處高波動震盪期；操作上應避免過度槓桿，採分批與紀律控管風險。",
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
    url = "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/FX:USD:TWD"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        for row in rows:
            if row.get("0") == "FX:USD:TWD" and row.get("6") is not None:
                val = float(row["6"])
                if 25.0 <= val <= 40.0:
                    return round(val, 2)
        return None
    except Exception as exc:
        print(f"[WARN] 無法取得 1 美元兌台幣匯率，保留原快照數值: {exc}")
        return None


def _parse_twse_num(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def fetch_twse_inst_for_date(date_obj: datetime) -> dict | None:
    """從證交所 BFI82U 抓取單日三大法人買賣超（換算為億元）"""
    day_str = date_obj.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={day_str}&response=json"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("stat") != "OK":
            return None

        foreign = 0.0
        trust = 0.0
        dealer = 0.0
        total = None

        for row in payload.get("data", []):
            if len(row) < 4:
                continue
            name = str(row[0])
            diff = _parse_twse_num(row[3])
            if diff is None:
                continue
            diff_yi = diff / 1e8  # 元 -> 億元

            if "合計" in name:
                total = diff_yi
            elif "外資" in name:
                foreign += diff_yi
            elif "投信" in name:
                trust += diff_yi
            elif "自營商" in name:
                dealer += diff_yi

        if total is None:
            total = foreign + trust + dealer

        return {
            "foreign": round(foreign, 2),
            "trust": round(trust, 2),
            "dealer": round(dealer, 2),
            "instTotal": round(total, 2),
        }
    except Exception as exc:
        print(f"[WARN] 無法取得 {day_str} 三大法人資料: {exc}")
        return None


def fill_inst_10d(hist: list[dict]) -> list[dict]:
    """往回掃描近 18 天日曆日，把對應日期的三大法人買賣超補進 history10d"""
    target_dates = {item.get("date") for item in hist if item.get("date")}
    inst_map: dict[str, dict] = {}

    for offset in range(18):
        d = NOW - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        short_d = d.strftime("%m/%d")
        if short_d not in target_dates or short_d in inst_map:
            continue
        res = fetch_twse_inst_for_date(d)
        if res is not None:
            inst_map[short_d] = res

    updated = []
    for item in hist:
        row = dict(item)
        d_key = row.get("date")
        if d_key in inst_map:
            row.update(inst_map[d_key])
        updated.append(row)
    return updated


def compute_win_stats(item: dict, seed_salt: int = 20261125) -> dict:
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
    hist[-1]["date"] = SHORT_DATE_STR
    hist = fill_inst_10d(hist)
    snap["history10d"] = hist

    if not isinstance(snap.get("news"), dict):
        snap["news"] = dict(DEFAULT_NEWS)

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
    snap["tradeDate"] = TODAY_STR
    snap["updated"] = TIME_STR

    new_html = replace_snapshot_json(html, SNAPSHOT_ID, snap)
    with open(TARGET_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"已更新 {TARGET_HTML}（#{SNAPSHOT_ID}）於 {TIME_STR}")


if __name__ == "__main__":
    main()
