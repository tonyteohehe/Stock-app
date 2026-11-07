"""Tính chỉ báo kỹ thuật, dòng tiền và chấm điểm. Toàn bộ là code thuần, không dùng AI."""
import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """df cần các cột: open, high, low, close, volume (index là ngày)."""
    d = df.copy()
    c = d["close"]

    for n in (20, 50, 200):
        d[f"ma{n}"] = c.rolling(n).mean()

    # RSI 14 (Wilder)
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    # MACD 12-26-9
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_signal"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_signal"]

    # Bollinger Bands 20, 2
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    d["bb_upper"] = mid + 2 * std
    d["bb_lower"] = mid - 2 * std

    # ATR 14
    tr = pd.concat(
        [d["high"] - d["low"], (d["high"] - c.shift()).abs(), (d["low"] - c.shift()).abs()],
        axis=1,
    ).max(axis=1)
    d["atr"] = tr.rolling(14).mean()

    # Khối lượng & dòng tiền
    d["vol_ma20"] = d["volume"].rolling(20).mean()
    d["obv"] = (np.sign(delta).fillna(0) * d["volume"]).cumsum()
    d["obv_ma20"] = d["obv"].rolling(20).mean()

    tp = (d["high"] + d["low"] + c) / 3
    mf = tp * d["volume"]
    pos = mf.where(tp > tp.shift(), 0).rolling(14).sum()
    neg = mf.where(tp < tp.shift(), 0).rolling(14).sum()
    d["mfi"] = 100 - 100 / (1 + pos / neg.replace(0, np.nan))

    d["high_52w"] = d["high"].rolling(250, min_periods=60).max()
    return d


# ---------------------------------------------------------------- chấm điểm
def technical_score(d: pd.DataFrame):
    last, prev = d.iloc[-1], d.iloc[-2]
    s, notes = 0, []

    # Xu hướng (40 điểm)
    for n in (20, 50, 200):
        if pd.notna(last[f"ma{n}"]) and last["close"] > last[f"ma{n}"]:
            s += 10
            notes.append(f"Giá trên MA{n}")
        elif pd.notna(last[f"ma{n}"]):
            notes.append(f"Giá dưới MA{n}")
    if pd.notna(last["ma50"]) and last["ma20"] > last["ma50"]:
        s += 10
        notes.append("MA20 > MA50 (xu hướng ngắn hạn tốt)")

    # Động lượng (30 điểm)
    rsi = last["rsi"]
    if 50 <= rsi <= 70:
        s += 15
        notes.append(f"RSI {rsi:.0f}: động lượng tích cực")
    elif 30 <= rsi < 50:
        s += 8
        notes.append(f"RSI {rsi:.0f}: trung tính/yếu")
    elif rsi > 70:
        s += 5
        notes.append(f"RSI {rsi:.0f}: QUÁ MUA, rủi ro điều chỉnh")
    else:
        s += 10
        notes.append(f"RSI {rsi:.0f}: QUÁ BÁN, có thể hồi phục")
    if last["macd_hist"] > 0:
        s += 10
        notes.append("MACD trên đường tín hiệu")
    if last["macd_hist"] > prev["macd_hist"]:
        s += 5
        notes.append("Histogram MACD đang tăng")

    # Cấu trúc giá (30 điểm)
    chg20 = d["close"].iloc[-1] / d["close"].iloc[-21] - 1 if len(d) > 21 else 0
    if chg20 > 0:
        s += 15
    notes.append(f"Biến động 20 phiên: {chg20:+.1%}")
    if pd.notna(last["high_52w"]):
        gap = last["close"] / last["high_52w"] - 1
        if gap > -0.10:
            s += 15
        notes.append(f"Cách đỉnh 52 tuần: {gap:.1%}")
    return min(s, 100), notes


def money_flow_score(d: pd.DataFrame):
    last = d.iloc[-1]
    s, notes = 0, []

    if last["obv"] > last["obv_ma20"]:
        s += 30
        notes.append("OBV trên trung bình 20 phiên: tiền đang vào")
    else:
        notes.append("OBV dưới trung bình 20 phiên: tiền đang rút")

    mfi = last["mfi"]
    if 50 <= mfi <= 80:
        s += 25
        notes.append(f"MFI {mfi:.0f}: dòng tiền tích cực")
    elif 20 <= mfi < 50:
        s += 12
        notes.append(f"MFI {mfi:.0f}: dòng tiền yếu")
    elif mfi > 80:
        s += 10
        notes.append(f"MFI {mfi:.0f}: dòng tiền quá nóng")
    else:
        s += 15
        notes.append(f"MFI {mfi:.0f}: bị bán quá mức")

    # So sánh khối lượng phiên tăng và phiên giảm trong 10 phiên gần nhất
    r = d.tail(10)
    up = r.loc[r["close"] > r["close"].shift(), "volume"].sum()
    down = r.loc[r["close"] < r["close"].shift(), "volume"].sum()
    ratio = up / down if down else 2
    if ratio > 1.2:
        s += 25
    elif ratio > 1:
        s += 15
    notes.append(f"KL phiên tăng/phiên giảm (10 phiên): {ratio:.2f}")

    vol_x = last["volume"] / last["vol_ma20"] if last["vol_ma20"] else 1
    up_day = last["close"] >= d["close"].iloc[-2]
    if vol_x > 1.5 and up_day:
        s += 20
        notes.append(f"Khối lượng đột biến x{vol_x:.1f} kèm giá tăng")
    elif vol_x > 1.5:
        notes.append(f"CẢNH BÁO: khối lượng đột biến x{vol_x:.1f} kèm giá giảm")
    else:
        s += 8
        notes.append(f"Khối lượng so với TB20: x{vol_x:.1f}")
    return min(s, 100), notes


def fundamental_score(r: dict | None):
    """r gồm các khóa: pe, pb, roe, de (một số có thể thiếu)."""
    if not r:
        return None, ["Không lấy được dữ liệu cơ bản"]
    s, n_items, notes = 0, 0, []

    roe = r.get("roe")
    if roe is not None:
        n_items += 1
        s += 30 if roe >= 15 else 18 if roe >= 10 else 5
        notes.append(f"ROE {roe:.1f}%")
    pe = r.get("pe")
    if pe is not None and pe > 0:
        n_items += 1
        s += 25 if pe < 12 else 15 if pe < 20 else 5
        notes.append(f"P/E {pe:.1f}")
    elif pe is not None:
        notes.append("P/E âm (doanh nghiệp đang lỗ)")
    pb = r.get("pb")
    if pb is not None:
        n_items += 1
        s += 20 if pb < 1.5 else 12 if pb < 3 else 4
        notes.append(f"P/B {pb:.2f}")
    de = r.get("de")
    if de is not None:
        n_items += 1
        s += 25 if de < 1 else 12 if de < 2 else 3
        notes.append(f"Nợ/Vốn chủ {de:.2f}")

    if n_items == 0:
        return None, notes or ["Không đủ dữ liệu cơ bản"]
    # Quy đổi về thang 100 nếu thiếu một số chỉ tiêu
    max_pts = {"roe": 30, "pe": 25, "pb": 20, "de": 25}
    available = sum(max_pts[k] for k in max_pts if r.get(k) is not None)
    return round(s / available * 100), notes


WEIGHTS = {"fund": 0.40, "tech": 0.35, "flow": 0.25}


def composite(tech, flow, fund):
    parts = {"tech": tech, "flow": flow, "fund": fund}
    used = {k: v for k, v in parts.items() if v is not None}
    w = sum(WEIGHTS[k] for k in used)
    total = sum(WEIGHTS[k] * v for k, v in used.items()) / w
    return round(total)


def rating(score: float) -> str:
    if score >= 70:
        return "TÍCH CỰC - cân nhắc mua"
    if score >= 55:
        return "KHÁ - đưa vào theo dõi"
    if score >= 40:
        return "TRUNG LẬP - đứng ngoài"
    return "TIÊU CỰC - tránh / cân nhắc bán"


def analyze(price_df: pd.DataFrame, ratios: dict | None):
    d = add_indicators(price_df)
    t, tn = technical_score(d)
    f, fn = money_flow_score(d)
    b, bn = fundamental_score(ratios)
    total = composite(t, f, b)
    last = d.iloc[-1]
    return {
        "data": d,
        "scores": {"Kỹ thuật": t, "Dòng tiền": f, "Cơ bản": b, "Tổng": total},
        "rating": rating(total),
        "notes": {"Kỹ thuật": tn, "Dòng tiền": fn, "Cơ bản": bn},
        "levels": {
            "Giá đóng cửa": float(round(last["close"], 2)),
            "Hỗ trợ (đáy 20 phiên)": float(round(d["low"].tail(20).min(), 2)),
            "Kháng cự (đỉnh 20 phiên)": float(round(d["high"].tail(20).max(), 2)),
            "Cắt lỗ gợi ý (giá - 2×ATR)": float(round(last["close"] - 2 * last["atr"], 2)),
        },
    }
