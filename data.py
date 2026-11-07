"""Lấy dữ liệu chứng khoán Việt Nam.
Chỉ số cơ bản: bạn tự nhập trong app, lưu ở co_ban.csv.
Nguồn giá: VNDirect -> DNSE (Entrade). Giá thống nhất theo đơn vị NGHÌN ĐỒNG."""
import time
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import requests

# Danh sách VN30 (thành phần thay đổi theo kỳ, hãy tự cập nhật nếu cần)
VN30 = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
COLS = ["open", "high", "low", "close", "volume"]


def _get_json(url, params, header_sets):
    """Thử lần lượt nhiều bộ header; trả JSON hợp lệ đầu tiên có dữ liệu."""
    last = ""
    for h in header_sets:
        try:
            r = requests.get(url, params=params, headers=h, timeout=20)
            j = r.json()
            if j.get("t"):
                return j
            last = f"HTTP {r.status_code}: {r.text[:120]}"
        except Exception as e:
            last = str(e)[:150]
    raise ValueError(last)


def _ohlc_from_tv(j) -> pd.DataFrame:
    """Chuyển JSON dạng {t,o,h,l,c,v} thành DataFrame theo ngày."""
    t = pd.to_datetime(j["t"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh")
    df = pd.DataFrame({
        "time": t.tz_localize(None).normalize(),
        "open": j["o"], "high": j["h"], "low": j["l"], "close": j["c"], "volume": j["v"],
    })
    return df.set_index("time")


def _ts(d: date) -> int:
    return int(time.mktime(d.timetuple()))


def _vndirect(symbol, start, end):
    url = "https://dchart-api.vndirect.com.vn/dchart/history"
    params = {"resolution": "D", "symbol": symbol,
              "from": _ts(start), "to": _ts(end) + 86400}
    headers = [
        {},  # header mặc định của requests
        {"User-Agent": BROWSER_UA, "Accept": "text/html,application/json,*/*"},
        {"User-Agent": BROWSER_UA, "Referer": "https://dchart.vndirect.com.vn/",
         "Origin": "https://dchart.vndirect.com.vn"},
    ]
    return _ohlc_from_tv(_get_json(url, params, headers))


def _dnse(symbol, start, end):
    url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
    params = {"symbol": symbol, "resolution": "1D",
              "from": _ts(start), "to": _ts(end) + 86400}
    headers = [{}, {"User-Agent": BROWSER_UA, "Accept": "application/json, */*"}]
    return _ohlc_from_tv(_get_json(url, params, headers))


SOURCES = [("VNDirect", _vndirect), ("DNSE", _dnse)]


def get_price(symbol: str, years: int = 2) -> pd.DataFrame:
    symbol = symbol.upper().strip()
    end = date.today()
    start = end - timedelta(days=365 * years)
    errors = []
    for name, fn in SOURCES:
        try:
            df = fn(symbol, start, end)
            df = df[COLS].astype(float).sort_index()
            df = df[~df.index.duplicated(keep="last")].dropna()
            if len(df) < 30:
                raise ValueError(f"chỉ có {len(df)} phiên")
            if df["close"].median() > 1000:  # nguồn trả theo đồng -> đổi sang nghìn đồng
                df[["open", "high", "low", "close"]] /= 1000
            df.attrs["source"] = name
            return df
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError("Không lấy được giá. " + " | ".join(errors))


FUND_FILE = Path(__file__).with_name("co_ban.csv")
FUND_COLS = ["ma", "pe", "pb", "roe", "de", "cap_nhat"]


def load_fund_table() -> pd.DataFrame:
    if FUND_FILE.exists():
        df = pd.read_csv(FUND_FILE, dtype={"ma": str})
        return df.reindex(columns=FUND_COLS)
    return pd.DataFrame(columns=FUND_COLS)


def get_ratios(symbol: str) -> dict | None:
    """Đọc chỉ số cơ bản bạn đã nhập trong app (lưu ở file co_ban.csv)."""
    df = load_fund_table()
    row = df[df["ma"].str.upper() == symbol.upper()]
    if row.empty:
        return None
    r = row.iloc[-1]
    out = {k: (float(r[k]) if pd.notna(r[k]) else None) for k in ("pe", "pb", "roe", "de")}
    return out if any(v is not None for v in out.values()) else None


def save_ratios(symbol: str, pe=None, pb=None, roe=None, de=None):
    df = load_fund_table()
    df = df[df["ma"].str.upper() != symbol.upper()]
    new = pd.DataFrame([{"ma": symbol.upper(), "pe": pe, "pb": pb, "roe": roe, "de": de,
                         "cap_nhat": date.today().isoformat()}])
    df = pd.concat([df, new], ignore_index=True) if not df.empty else new
    df.to_csv(FUND_FILE, index=False, encoding="utf-8-sig")
