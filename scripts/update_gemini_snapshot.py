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
    {"date": "11/11", "taiex": None, "marginBal": 5411.58, "marginChg": 44.79, "shortBal": 209019, "shortChg": -2112, "maintenanceRatio": 174.15, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/12", "taiex": None, "marginBal": 5334.75, "marginChg": -76.83, "shortBal": 210522, "shortChg": 1503, "maintenanceRatio": 167.22, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/13", "taiex": None, "marginBal": 5365.99, "marginChg": 31.24, "shortBal": 208773, "shortChg": -1749, "maintenanceRatio": 170.67, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/16", "taiex": 41040.08, "marginBal": 5244.98, "marginChg": -121.01, "shortBal": 217384, "shortChg": 8611, "maintenanceRatio": 158.50, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/17", "taiex": 40092.11, "marginBal": 5087.21, "marginChg": -157.77, "shortBal": 207959, "shortChg": -9425, "maintenanceRatio": 153.71, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/18", "taiex": 40194.91, "marginBal": 5080.27, "marginChg": -6.95, "shortBal": 193544, "shortChg": -14415, "maintenanceRatio": 156.22, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/19", "taiex": 38426.89, "marginBal": 4843.68, "marginChg": -236.58, "shortBal": 209819, "shortChg": 16275, "maintenanceRatio": 147.90, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/20", "taiex": 36033.29, "marginBal": 4352.27, "marginChg": -491.41, "shortBal": 199791, "shortChg": -10028, "maintenanceRatio": 140.40, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/23", "taiex": 36811.89, "marginBal": 4338.08, "marginChg": -14.20, "shortBal": 172957, "shortChg": -26834, "maintenanceRatio": 148.46, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
    {"date": "11/24", "taiex": 40122.35, "marginBal": 4535.05, "marginChg": 196.97, "shortBal": 186613, "shortChg": 13656, "maintenanceRatio": None, "foreign": None, "trust": None, "dealer": None, "instTotal": None},
]

DEFAULT_NEWS = {
    "bullish": [
        "證交所自 2026/11/24 起將信用交易擔保維持率最低標準由 130% 調降至 120%，並取消 11/24 前低於 130% 的追繳紀錄與處分，緩解短期斷頭賣壓。",
        "放寬可用具流動性與客觀評價之擔保品抵繳，提供融資戶資金緩衝空間。",
    ],
    "bearish": [
        "近期大盤與高槓桿部位震盪劇烈，維持率門檻調降雖延後追繳時點，但融資借款本金與帳面波動仍在。",
        "若國際股市或半導體族群持續修正，市場籌碼與風險偏好仍易受壓抑。",
    ],
    "summary": "總結：政策面调降維持率至 120% 屬短期防斷頭緩衝利多，有助降低集中殺盤；但盤勢高波動環境未除，操作仍宜控管槓桿、分批布局，並持續追蹤每日融資增減與三大法人動向。",
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

    if close_val is not None and prev_val is not None:
        snap["taiexClose"] = close_val
        snap["taiexPrev"] = prev_val
    else:
        print("[INFO] 保留既有 taiexClose 與 taiexPrev")

    hist = snap.get("history10d")
    if not isinstance(hist, list) or len(hist) == 0:
        hist = [dict(item) for item in DEFAULT_HISTORY_10D]
    hist = hist[-10:]
    if isinstance(snap.get("taiexClose"), (int, float)):
        hist[-1]["taiex"] = snap["taiexClose"]
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
