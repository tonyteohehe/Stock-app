"""App phân tích cổ phiếu cá nhân. Chạy bằng lệnh:  streamlit run app.py"""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data import FUND_FILE, VN30, get_price, get_ratios, save_ratios
from indicators import analyze

st.set_page_config(page_title="Phân tích cổ phiếu", layout="wide")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")  # máy chủ trên mạng chạy giờ UTC, luôn quy về giờ VN
AI_LIMIT_PER_SESSION = 10            # giới hạn lượt AI mỗi người mỗi lần mở app


def secret(name: str, default: str = "") -> str:
    """Đọc cấu hình: ưu tiên Secrets của Streamlit Cloud, sau đó biến môi trường."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # chạy trên máy không có file secrets
        pass
    return os.getenv(name, default)


# ---------------------------------------------------------------- mật khẩu
APP_PASSWORD = secret("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("authed"):
    st.title("🔒 Đăng nhập")
    pw = st.text_input("Mật khẩu", type="password")
    if pw:
        if pw == APP_PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        st.error("Sai mật khẩu")
    st.stop()

st.title("📈 Trợ lý phân tích cổ phiếu cá nhân")
st.caption("Công cụ tham khảo cá nhân, không phải khuyến nghị đầu tư. Giá: VNDirect / DNSE. Cơ bản: bạn tự nhập.")


CACHE_MINUTES = 5  # giá được lưu tạm 5 phút; bấm "Làm mới" để tải lại ngay


@st.cache_data(ttl=CACHE_MINUTES * 60, show_spinner=False)
def load_price(symbol: str, years: int):
    return get_price(symbol, years), datetime.now(VN_TZ)


def load(symbol: str, years: int):
    # Chỉ số cơ bản đọc mới mỗi lần để thấy ngay khi bạn sửa
    price, _ = load_price(symbol, years)
    return price, get_ratios(symbol)


def market_status() -> str:
    now = datetime.now(VN_TZ)
    t = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return "⚪ Cuối tuần - thị trường nghỉ"
    if 9 * 60 <= t < 11 * 60 + 30 or 13 * 60 <= t < 14 * 60 + 45:
        return "🟢 Đang trong phiên - nến hôm nay chưa chốt"
    if 14 * 60 + 45 <= t < 15 * 60:
        return "🟡 Phiên ATC / sắp đóng cửa"
    return "⚪ Ngoài giờ giao dịch"


def chart(d: pd.DataFrame, symbol: str):
    d = d.tail(250)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.15, 0.15, 0.2], vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(x=d.index, open=d.open, high=d.high, low=d.low,
                                 close=d.close, name=symbol), 1, 1)
    for ma, color in (("ma20", "orange"), ("ma50", "blue"), ("ma200", "purple")):
        fig.add_trace(go.Scatter(x=d.index, y=d[ma], name=ma.upper(),
                                 line=dict(width=1, color=color)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.bb_upper, name="BB trên",
                             line=dict(width=0.5, dash="dot", color="gray")), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.bb_lower, name="BB dưới",
                             line=dict(width=0.5, dash="dot", color="gray")), 1, 1)
    fig.add_trace(go.Bar(x=d.index, y=d.volume, name="Khối lượng",
                         marker_color="lightslategray"), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.rsi, name="RSI"), 3, 1)
    fig.add_hline(y=70, line_dash="dot", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", row=3, col=1)
    fig.add_trace(go.Bar(x=d.index, y=d.macd_hist, name="MACD hist"), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.macd, name="MACD"), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.macd_signal, name="Signal"), 4, 1)
    fig.update_layout(height=800, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


def ai_comment(symbol: str, res: dict) -> str:
    """Nhờ Claude viết nhận định. AI chỉ diễn giải số liệu đã tính sẵn."""
    import anthropic
    payload = {
        "ma": symbol,
        "diem": res["scores"],
        "xep_hang": res["rating"],
        "nhan_xet": res["notes"],
        "muc_gia": res["levels"],
    }
    prompt = (
        "Bạn là chuyên viên phân tích chứng khoán. Dưới đây là kết quả phân tích ĐÃ TÍNH SẴN "
        f"cho mã {symbol}. Viết nhận định ngắn gọn bằng tiếng Việt gồm: (1) tóm tắt xu hướng, "
        "(2) dòng tiền, (3) sức khỏe tài chính, (4) điểm mua/bán và cắt lỗ tham khảo, "
        "(5) rủi ro chính. CHỈ dùng số liệu được cung cấp, không tự bịa thêm số.\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )
    client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ---------------------------------------------------------------- giao diện
tab1, tab2 = st.tabs(["🔍 Phân tích một mã", "📋 Quét danh sách"])

with st.sidebar:
    years = st.slider("Số năm dữ liệu", 1, 5, 2)
    st.write(market_status())
    if st.button("🔄 Làm mới dữ liệu", use_container_width=True):
        load_price.clear()
        st.rerun()
    st.caption(f"Giá tự làm mới sau {CACHE_MINUTES} phút. Dữ liệu trong phiên có thể trễ vài phút.")
    has_ai = bool(secret("ANTHROPIC_API_KEY"))
    st.write("AI nhận định:", "✅ đã bật" if has_ai else "⚪ chưa có API key")

    st.divider()
    st.caption("Dữ liệu cơ bản (co_ban.csv)")
    if FUND_FILE.exists():
        st.download_button("⬇️ Tải về bản sao", FUND_FILE.read_bytes(), "co_ban.csv",
                           "text/csv", use_container_width=True)
    up = st.file_uploader("⬆️ Khôi phục từ file", type="csv", label_visibility="collapsed")
    if up is not None and st.button("Ghi đè dữ liệu cơ bản", use_container_width=True):
        FUND_FILE.write_bytes(up.getvalue())
        st.success("Đã khôi phục.")
        st.rerun()

with tab1:
    symbol = st.text_input("Mã cổ phiếu", "FPT").upper().strip()
    if symbol:
        try:
            with st.spinner("Đang tải dữ liệu..."):
                price, ratios = load(symbol, years)
                _, fetched_at = load_price(symbol, years)
            res = analyze(price, ratios)
        except Exception as e:
            st.error(f"Không tải được dữ liệu {symbol}: {e}")
            st.stop()

        last_day = price.index[-1].strftime("%d/%m/%Y")
        st.caption(f"Nến mới nhất: **{last_day}** · Giá: **{price['close'].iloc[-1]:,.2f}** nghìn đ · "
                   f"Tải lúc {fetched_at:%H:%M:%S} · Nguồn: {price.attrs.get('source', '?')}")

        sc = res["scores"]
        cols = st.columns(5)
        for col, (k, v) in zip(cols, sc.items()):
            col.metric(k, "N/A" if v is None else f"{v}/100")
        cols[4].markdown(f"**{res['rating']}**")

        with st.expander("✏️ Nhập / sửa chỉ số cơ bản" + ("" if ratios else " (chưa có dữ liệu)"),
                         expanded=ratios is None):
            st.caption("Lấy số liệu quý gần nhất trên CafeF, Vietstock hoặc app công ty chứng khoán "
                       "của bạn. Ô nào không có thì để 0.")
            cur = ratios or {}
            f1, f2, f3, f4 = st.columns(4)
            pe = f1.number_input("P/E", value=float(cur.get("pe") or 0), step=0.1)
            pb = f2.number_input("P/B", value=float(cur.get("pb") or 0), step=0.1)
            roe = f3.number_input("ROE (%)", value=float(cur.get("roe") or 0), step=0.5)
            de = f4.number_input("Nợ vay / Vốn chủ", value=float(cur.get("de") or 0), step=0.1)
            if st.button("💾 Lưu và chấm điểm lại"):
                save_ratios(symbol, pe or None, pb or None, roe or None, de or None)
                st.rerun()

        st.plotly_chart(chart(res["data"], symbol), use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        for col, k in zip((c1, c2, c3), ("Kỹ thuật", "Dòng tiền", "Cơ bản")):
            col.subheader(k)
            for n in res["notes"][k]:
                col.write("• " + n)
        c4.subheader("Mức giá")
        for k, v in res["levels"].items():
            c4.write(f"• {k}: **{v}**")

        used = st.session_state.get("ai_used", 0)
        if has_ai and used >= AI_LIMIT_PER_SESSION:
            st.info(f"Đã dùng hết {AI_LIMIT_PER_SESSION} lượt AI cho lần mở app này.")
        elif has_ai and st.button(f"🤖 AI viết nhận định (còn {AI_LIMIT_PER_SESSION - used} lượt)"):
            st.session_state["ai_used"] = used + 1
            with st.spinner("AI đang phân tích..."):
                try:
                    st.markdown(ai_comment(symbol, res))
                except Exception as e:
                    st.error(f"Lỗi gọi AI: {e}")

with tab2:
    raw = st.text_area("Danh sách mã (cách nhau bằng dấu phẩy)", ", ".join(VN30))
    if st.button("Quét"):
        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        rows, bar = [], st.progress(0.0)
        for i, s in enumerate(symbols):
            try:
                p, r = load(s, years)
                res = analyze(p, r)
                rows.append({"Mã": s, **res["scores"], "Xếp hạng": res["rating"],
                             "Giá": res["levels"]["Giá đóng cửa"]})
            except Exception as e:
                rows.append({"Mã": s, "Xếp hạng": f"Lỗi: {e}"})
            bar.progress((i + 1) / len(symbols))
        df = pd.DataFrame(rows)
        if "Tổng" in df.columns:
            df = df.sort_values("Tổng", ascending=False, na_position="last")
        st.dataframe(df, use_container_width=True, hide_index=True)
