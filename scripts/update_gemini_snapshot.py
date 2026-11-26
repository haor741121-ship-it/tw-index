import json
import math
import random
import re
import time
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
    {"date": "11/13", "taiex": 43675.12, "usdTwd": 32.88, "marginBal": 5365.99, "marginChg": 31.24, "shortBal": 208773, "shortChg": -1749, "maintenanceRatio": 170.67, "foreign": 288.37, "trust": 95.39, "dealer": 68.92, "instTotal": 452.68, "foreignFutNet": -100870},
    {"date": "11/16", "taiex": 41040.08, "usdTwd": 32.96, "marginBal": 5244.98, "marginChg": -121.01, "shortBal": 217384, "shortChg": 8611, "maintenanceRatio": 158.5, "foreign": -701.89, "trust": -183.02, "dealer": -259.03, "instTotal": -1143.94, "foreignFutNet": -96787},
    {"date": "11/17", "taiex": 40092.11, "usdTwd": 32.91, "marginBal": 5087.21, "marginChg": -157.77, "shortBal": 207959, "shortChg": -9425, "maintenanceRatio": 153.71, "foreign": -380.94, "trust": -38.21, "dealer": -156.96, "instTotal": -576.11, "foreignFutNet": -97896},
    {"date": "11/18", "taiex": 40194.91, "usdTwd": 32.93, "marginBal": 5080.27, "marginChg": -6.95, "shortBal": 193544, "shortChg": -14415, "maintenanceRatio": 156.22, "foreign": -765.64, "trust": 166.12, "dealer": -42.01, "instTotal": -641.53, "foreignFutNet": -99438},
    {"date": "11/19", "taiex": 38426.89, "usdTwd": 33.03, "marginBal": 4843.68, "marginChg": -236.58, "shortBal": 209819, "shortChg": 16275, "maintenanceRatio": 147.9, "foreign": -243.12, "trust": 43.9, "dealer": -233.03, "instTotal": -432.25, "foreignFutNet": -99219},
    {"date": "11/20", "taiex": 36033.29, "usdTwd": 32.95, "marginBal": 4352.27, "marginChg": -491.41, "shortBal": 199791, "shortChg": -10028, "maintenanceRatio": 140.4, "foreign": -95.11, "trust": -73.47, "dealer": -340.83, "instTotal": -509.41, "foreignFutNet": -97863},
    {"date": "11/23", "taiex": 36811.89, "usdTwd": 32.85, "marginBal": 4338.08, "marginChg": -14.2, "shortBal": 172957, "shortChg": -26834, "maintenanceRatio": 148.46, "foreign": -289.48, "trust": -41.55, "dealer": -190.01, "instTotal": -521.04, "foreignFutNet": None},
    {"date": "11/24", "taiex": 40122.35, "usdTwd": 32.94, "marginBal": 4535.05, "marginChg": 196.97, "shortBal": 186613, "shortChg": 13656, "maintenanceRatio": None, "foreign": -503.9, "trust": 97.63, "dealer": -810.25, "instTotal": -1216.52, "foreignFutNet": -103182},
    {"date": "11/25", "taiex": 38195.43, "usdTwd": 33.13, "marginBal": None, "marginChg": None, "shortBal": None, "shortChg": None, "maintenanceRatio": None, "foreign": -1236.55, "trust": 535.32, "dealer": -128.33, "instTotal": -829.56, "foreignFutNet": None},
    {"date": "11/26", "taiex": 39151.81, "usdTwd": 33.13, "marginBal": None, "marginChg": None, "shortBal": None, "shortChg": None, "maintenanceRatio": None, "foreign": -491.81, "trust": 212.13, "dealer": 128.65, "instTotal": -151.03, "foreignFutNet": None},
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
        "winRate": 54.4,
        "range": "20日可能區間：-7.5% ~ +10.0%",
        "annualVol": 0.24,
        "annualDrift": 0.09,
        "horizonDays": 20,
        "targetPct": 0.0,
        "desc": "與大盤高度連動，波動與預期報酬適中。",
    },
    {
        "code": "00878 國泰永續高股息",
        "winRate": 55.8,
        "range": "20日可能區間：-4.1% ~ +5.4%",
        "annualVol": 0.13,
        "annualDrift": 0.065,
        "horizonDays": 20,
        "targetPct": 0.0,
        "desc": "波動最小、短線較抗震，三檔中勝率最高。",
    },
    {
        "code": "8086 宏捷科",
        "winRate": 49.3,
        "range": "20日可能區間：-15.2% ~ +18.2%",
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


def is_pre_market(dt: datetime) -> bool:
    """台股開盤前（09:00 前）視為尚未開始當日交易，避免誤把前一日資料標成當日"""
    return dt.hour < 9


def _parse_num(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").replace("%", "").replace("億", "").replace("張", "").strip()
    if not s or s in {"-", "--", "N/A", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


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


def fetch_kgi_maintenance_10d() -> dict[str, dict]:
    """從凱基證券大盤動態表抓取免費融資融券與融資維持率"""
    url = "https://www.kgi.com.tw/zh-tw/product-market/stock-market-overview/tw-stock-market/tw-stock-market-detail?a=B658010E71E243C4A1D6B5F7BE914BDC&b=5D48401A7CE148CD8ABAC965F9B5AFBF"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text)
        # 抓取格式：11/25 -193.67 4,341.38 -17,248 169,365 151.61
        pattern = re.compile(
            r"\b(\d{1,2}/\d{1,2})\s+([+-]?[\d,.]+)\s+([\d,.]+)\s+([+-]?[\d,]+)\s+([\d,]+)\s+([\d.]+)\b"
        )
        result: dict[str, dict] = {}
        for m in pattern.finditer(text):
            mm, dd = m.group(1).split("/")
            short_d = f"{int(mm):02d}/{int(dd):02d}"
            if short_d in result:
                continue
            m_chg = _parse_num(m.group(2))
            m_bal = _parse_num(m.group(3))
            s_chg = _parse_num(m.group(4))
            s_bal = _parse_num(m.group(5))
            ratio = _parse_num(m.group(6))
            if ratio is not None and 50.0 <= ratio <= 300.0:
                result[short_d] = {
                    "marginChg": round(m_chg, 2) if m_chg is not None else None,
                    "marginBal": round(m_bal, 2) if m_bal is not None else None,
                    "shortChg": int(round(s_chg)) if s_chg is not None else None,
                    "shortBal": int(round(s_bal)) if s_bal is not None else None,
                    "maintenanceRatio": round(ratio, 2),
                }
        print(f"[INFO] 凱基證券成功取得 {len(result)} 天資券與維持率資料")
        return result
    except Exception as exc:
        print(f"[WARN] 凱基證券抓取失敗: {exc}")
        return {}


def fetch_finmind_margin_10d() -> dict[str, dict]:
    """從 FinMind 抓取近 20 天大盤融資融券餘額與增減（主力來源）"""
    start_str = (NOW - timedelta(days=20)).strftime("%Y-%m-%d")
    end_str = NOW.strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockTotalMarginPurchaseShortSale",
        "start_date": start_str,
        "end_date": end_str,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        if not rows:
            print("[WARN] FinMind 融資融券回傳空資料")
            return {}

        result: dict[str, dict] = {}
        for r in rows:
            d_raw = str(r.get("date", ""))
            if len(d_raw) < 10:
                continue
            short_d = f"{d_raw[5:7]}/{d_raw[8:10]}"
            name = str(r.get("name", ""))
            curr = _parse_num(r.get("TodayBalance"))
            prev = _parse_num(r.get("YesBalance"))
            if curr is None:
                continue

            if short_d not in result:
                result[short_d] = {}

            if name == "MarginPurchaseMoney":
                div = 1e8 if curr > 1e10 else 1e5
                curr_yi = round(curr / div, 2)
                result[short_d]["marginBal"] = curr_yi
                if prev is not None:
                    result[short_d]["marginChg"] = round(curr_yi - (prev / div), 2)
            elif name == "ShortSale":
                curr_int = int(round(curr))
                result[short_d]["shortBal"] = curr_int
                if prev is not None:
                    result[short_d]["shortChg"] = int(round(curr - prev))

        print(f"[INFO] FinMind 成功取得 {len(result)} 天融資融券資料")
        return result
    except Exception as exc:
        print(f"[WARN] FinMind 融資融券抓取失敗: {exc}")
        return {}


def fetch_twse_margin_for_date(date_obj: datetime) -> dict | None:
    """從證交所 MI_MARGN 抓取單日上市融資融券餘額與增減（備援來源）"""
    date_compact = date_obj.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/margin/MI_MARGN?date={date_compact}&selectType=ALL&response=json"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.twse.com.tw/zh/marginTrading/MI_MARGN.html",
    }
    try:
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("stat") != "OK":
            return None

        out: dict = {}
        for tbl in payload.get("tables", []):
            fields = tbl.get("fields", [])
            rows = tbl.get("data", [])
            if not fields or not rows:
                continue
            joined_fields = "".join(str(x) for x in fields)
            if "融資" in joined_fields and "融券" in joined_fields and len(rows) >= 2:
                row_amt = rows[0]
                row_sh = rows[1]
                if len(row_amt) >= 6:
                    prev_amt = _parse_num(row_amt[4])
                    curr_amt = _parse_num(row_amt[5])
                    if curr_amt is not None:
                        curr_yi = round(curr_amt / 100000.0, 2)
                        out["marginBal"] = curr_yi
                        if prev_amt is not None:
                            prev_yi = prev_amt / 100000.0
                            out["marginChg"] = round(curr_yi - prev_yi, 2)
                if len(row_sh) >= 6:
                    prev_sh = _parse_num(row_sh[4])
                    curr_sh = _parse_num(row_sh[5])
                    if curr_sh is not None:
                        curr_int = int(round(curr_sh))
                        out["shortBal"] = curr_int
                        if prev_sh is not None:
                            out["shortChg"] = int(round(curr_sh - prev_sh))

        if any(k in out for k in ("marginBal", "shortBal")):
            return out
        return None
    except Exception as exc:
        print(f"[WARN] 證交所 {date_compact} 融資融券抓取失敗: {exc}")
        return None


def fill_margin_10d(hist: list[dict], kgi_map: dict[str, dict]) -> list[dict]:
    """優先用 FinMind，再由凱基證券與證交所 MI_MARGN 備援補齊融資融券"""
    target_dates = {
        item.get("date")
        for item in hist
        if item.get("date")
        and (item.get("marginBal") is None or item.get("shortBal") is None)
    }
    if not target_dates:
        return hist

    margin_map = fetch_finmind_margin_10d()

    for d_key in target_dates:
        if d_key in kgi_map:
            slot = margin_map.setdefault(d_key, {})
            for k in ("marginBal", "marginChg", "shortBal", "shortChg"):
                if slot.get(k) is None and kgi_map[d_key].get(k) is not None:
                    slot[k] = kgi_map[d_key][k]

    missing_dates = {
        d for d in target_dates
        if d not in margin_map
        or margin_map[d].get("marginBal") is None
        or margin_map[d].get("shortBal") is None
    }

    if missing_dates:
        for offset in range(18):
            d = NOW - timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            short_d = d.strftime("%m/%d")
            if short_d not in missing_dates:
                continue
            res = fetch_twse_margin_for_date(d)
            if res is not None:
                margin_map.setdefault(short_d, {}).update(res)
            time.sleep(0.8)

    updated = []
    for item in hist:
        row = dict(item)
        d_key = row.get("date")
        if d_key in margin_map:
            for k in ("marginBal", "marginChg", "shortBal", "shortChg"):
                val = margin_map[d_key].get(k)
                if row.get(k) is None and val is not None:
                    row[k] = val
        updated.append(row)
    return updated


def fetch_finmind_maintenance_10d() -> dict[str, float]:
    """從 FinMind 抓取台灣大盤融資維持率（備援）"""
    start_str = (NOW - timedelta(days=20)).strftime("%Y-%m-%d")
    end_str = NOW.strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanTotalExchangeMarginMaintenance",
        "start_date": start_str,
        "end_date": end_str,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        if not rows:
            return {}

        result: dict[str, float] = {}
        for r in rows:
            d_raw = str(r.get("date", ""))
            if len(d_raw) < 10:
                continue
            short_d = f"{d_raw[5:7]}/{d_raw[8:10]}"

            val = _parse_num(r.get("TotalExchangeMarginMaintenance"))
            if val is None:
                for k, v in r.items():
                    if k == "date":
                        continue
                    cand = _parse_num(v)
                    if cand is not None and 50.0 <= cand <= 300.0:
                        val = cand
                        break
            if val is not None:
                result[short_d] = round(val, 2)
        return result
    except Exception as exc:
        print(f"[WARN] FinMind 融資維持率備援抓取失敗: {exc}")
        return {}


def fill_maintenance_10d(hist: list[dict], kgi_map: dict[str, dict]) -> list[dict]:
    """優先用凱基證券補齊融資維持率，仍有缺漏再嘗試 FinMind"""
    has_missing = any(item.get("maintenanceRatio") is None for item in hist)
    if not has_missing:
        return hist

    ratio_map: dict[str, float] = {}
    for d_key, vals in kgi_map.items():
        if vals.get("maintenanceRatio") is not None:
            ratio_map[d_key] = vals["maintenanceRatio"]

    still_missing = any(
        item.get("maintenanceRatio") is None and item.get("date") not in ratio_map
        for item in hist
    )
    if still_missing:
        fm_map = fetch_finmind_maintenance_10d()
        for d_key, val in fm_map.items():
            if d_key not in ratio_map:
                ratio_map[d_key] = val

    updated = []
    for item in hist:
        row = dict(item)
        d_key = row.get("date")
        if row.get("maintenanceRatio") is None and d_key in ratio_map:
            row["maintenanceRatio"] = ratio_map[d_key]
        updated.append(row)
    return updated


def fetch_finmind_inst_10d() -> dict[str, dict]:
    start_str = (NOW - timedelta(days=20)).strftime("%Y-%m-%d")
    end_str = NOW.strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockTotalInstitutionalInvestors",
        "start_date": start_str,
        "end_date": end_str,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        if not rows:
            print("[WARN] FinMind 三大法人回傳空資料")
            return {}

        daily: dict[str, dict[str, float | None]] = {}
        for r in rows:
            d_raw = str(r.get("date", ""))
            if len(d_raw) < 10:
                continue
            short_d = f"{d_raw[5:7]}/{d_raw[8:10]}"
            name = str(r.get("name", ""))
            buy = float(r.get("buy") or 0)
            sell = float(r.get("sell") or 0)
            net_yi = (buy - sell) / 1e8

            if short_d not in daily:
                daily[short_d] = {"foreign": 0.0, "trust": 0.0, "dealer": 0.0, "instTotal": None}

            if name in ("Foreign_Investor", "Foreign_Dealer_Self"):
                daily[short_d]["foreign"] = (daily[short_d]["foreign"] or 0.0) + net_yi
            elif name == "Investment_Trust":
                daily[short_d]["trust"] = (daily[short_d]["trust"] or 0.0) + net_yi
            elif name in ("Dealer_self", "Dealer_Hedging"):
                daily[short_d]["dealer"] = (daily[short_d]["dealer"] or 0.0) + net_yi
            elif name == "total":
                daily[short_d]["instTotal"] = net_yi

        result: dict[str, dict] = {}
        for d_key, vals in daily.items():
            f_val = vals["foreign"] or 0.0
            t_val = vals["trust"] or 0.0
            d_val = vals["dealer"] or 0.0
            tot = vals["instTotal"] if vals["instTotal"] is not None else (f_val + t_val + d_val)
            result[d_key] = {
                "foreign": round(f_val, 2),
                "trust": round(t_val, 2),
                "dealer": round(d_val, 2),
                "instTotal": round(tot, 2),
            }
        print(f"[INFO] FinMind 成功取得 {len(result)} 天三大法人資料")
        return result
    except Exception as exc:
        print(f"[WARN] FinMind 三大法人抓取失敗: {exc}")
        return {}


def fetch_twse_inst_for_date(date_obj: datetime) -> dict | None:
    day_str = date_obj.strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={day_str}&response=json"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html",
    }
    try:
        resp = requests.get(url, timeout=10, headers=headers)
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
            diff = _parse_num(row[3])
            if diff is None:
                continue
            diff_yi = diff / 1e8

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
        print(f"[WARN] 證交所 {day_str} 三大法人抓取失敗: {exc}")
        return None


def fetch_taifex_foreign_fut_net(date_obj: datetime) -> int | None:
    """嘗試從期交所查詢單日外資台指期（TX）未平倉多空淨口數，無法取得則回傳 None"""
    y_str = date_obj.strftime("%Y")
    m_str = date_obj.strftime("%m")
    d_str = date_obj.strftime("%d")
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    payload = {
        "queryType": "1",
        "goDraw": "",
        "queryDate": f"{y_str}/{m_str}/{d_str}",
        "commodityId": "TX",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.taifex.com.tw/cht/3/futContractsDate",
    }
    try:
        resp = requests.post(url, data=payload, timeout=10, headers=headers)
        resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text)
        m = re.search(
            r"(?:外資及陸資|外資)\s+([+-]?[\d,]+)\s+([+-]?[\d,]+)\s+([+-]?[\d,]+)\s+([+-]?[\d,]+)\s+([+-]?[\d,]+)\s+([+-]?[\d,]+)",
            text,
        )
        if m:
            net_val = _parse_num(m.group(6))
            if net_val is not None:
                return int(round(net_val))
        return None
    except Exception as exc:
        print(f"[WARN] 查詢期交所 {y_str}/{m_str}/{d_str} 外資期貨淨口數失敗: {exc}")
        return None


def fill_inst_10d(hist: list[dict]) -> list[dict]:
    inst_map = fetch_finmind_inst_10d()
    target_dates = {item.get("date") for item in hist if item.get("date")}

    if len(inst_map) == 0:
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
            time.sleep(1.2)

    fut_map: dict[str, int] = {}
    for offset in range(18):
        d = NOW - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        short_d = d.strftime("%m/%d")
        if short_d not in target_dates or short_d in fut_map:
            continue
        f_net = fetch_taifex_foreign_fut_net(d)
        if f_net is not None:
            fut_map[short_d] = f_net
        time.sleep(0.5)

    updated = []
    for item in hist:
        row = dict(item)
        d_key = row.get("date")
        if d_key in inst_map:
            row.update(inst_map[d_key])
        if d_key in fut_map:
            row["foreignFutNet"] = fut_map[d_key]
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
    pre_mkt = is_pre_market(NOW)

    close_val, prev_val = fetch_taiex_close()
    fx_val = fetch_usd_twd()

    if not pre_mkt:
        if close_val is not None and prev_val is not None:
            snap["taiexClose"] = close_val
            snap["taiexPrev"] = prev_val
        else:
            print("[INFO] 保留既有 taiexClose 與 taiexPrev")

        if fx_val is not None:
            snap["usdTwd"] = fx_val
        snap["tradeDate"] = TODAY_STR
    else:
        print(f"[INFO] 盤前時段（{TIME_STR}），保留既有基準日與收盤數值，不覆蓋 {snap.get('tradeDate')}")

    hist = snap.get("history10d")
    if not isinstance(hist, list) or len(hist) == 0:
        hist = [dict(item) for item in DEFAULT_HISTORY_10D]

    if not pre_mkt and (close_val is not None or fx_val is not None):
        if hist[-1].get("date") != SHORT_DATE_STR:
            hist.append({
                "date": SHORT_DATE_STR,
                "taiex": close_val,
                "usdTwd": fx_val,
                "marginBal": None,
                "marginChg": None,
                "shortBal": None,
                "shortChg": None,
                "maintenanceRatio": None,
                "foreign": None,
                "trust": None,
                "dealer": None,
                "instTotal": None,
                "foreignFutNet": None,
            })
        else:
            if close_val is not None:
                hist[-1]["taiex"] = close_val
            if fx_val is not None:
                hist[-1]["usdTwd"] = fx_val

    hist = hist[-10:]
    hist = fill_inst_10d(hist)

    need_kgi = any(
        item.get("maintenanceRatio") is None
        or item.get("marginBal") is None
        or item.get("shortBal") is None
        for item in hist
    )
    kgi_map = fetch_kgi_maintenance_10d() if need_kgi else {}

    hist = fill_margin_10d(hist, kgi_map)
    hist = fill_maintenance_10d(hist, kgi_map)
    snap["history10d"] = hist

    latest_fut = None
    latest_fut_date = ""
    for row in reversed(hist):
        if row.get("foreignFutNet") is not None:
            latest_fut = row.get("foreignFutNet")
            latest_fut_date = row.get("date") or ""
            break
    if latest_fut is not None:
        snap["foreignFuturesNet"] = latest_fut
        snap["foreignFuturesDate"] = latest_fut_date

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
    snap["updated"] = TIME_STR

    new_html = replace_snapshot_json(html, SNAPSHOT_ID, snap)
    with open(TARGET_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"已更新 {TARGET_HTML}（#{SNAPSHOT_ID}）於 {TIME_STR}")


if __name__ == "__main__":
    main()
