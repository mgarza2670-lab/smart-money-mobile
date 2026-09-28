"""Smart Money System – mobilvenlig version uden MetaTrader 5.

Kør lokalt:  streamlit run app.py
Eller deploy på Streamlit Cloud og åbn linket i telefonens browser.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from engine import Params, backtest, stats

st.set_page_config(
    page_title="Smart Money System",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.title("Smart Money System")
st.caption("Virker i browseren på telefon og PC. Ingen MetaTrader påkrævet.")

SYMBOLS = {
    "Guld (futures GC=F ≈ XAUUSD)": "GC=F",
    "Guld / USD (Yahoo)": "XAUUSD=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
}

TF_YF = {"15M": "15m", "1H": "60m", "1D": "1d"}


@st.cache_data(ttl=60, show_spinner="Henter priser…")
def fetch_yahoo(ticker: str, interval: str, lookback_days: int) -> pd.DataFrame:
    end = pd.Timestamp.utcnow()
    start = end - timedelta(days=lookback_days)
    raw = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=False,
        progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"Ingen data for {ticker} ({interval}). Prøv et andet symbol eller kortere periode.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.lower)
    need = {"open", "high", "low", "close"}
    if not need.issubset(set(raw.columns)):
        raise RuntimeError(f"Uventet dataformat: {list(raw.columns)}")
    out = raw[list(need)].dropna().reset_index()
    time_col = out.columns[0]
    out = out.rename(columns={time_col: "time"})
    out["time"] = pd.to_datetime(out["time"], utc=True).dt.tz_convert(None)
    return out[["time", "open", "high", "low", "close"]]


def load_csv(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    cols = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for want in ("time", "open", "high", "low", "close"):
        if want not in cols:
            raise RuntimeError(f"CSV mangler kolonnen '{want}'.")
        mapping[cols[want]] = want
    df = df.rename(columns=mapping)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    if df["time"].dt.tz is not None:
        df["time"] = df["time"].dt.tz_convert(None)
    return df[["time", "open", "high", "low", "close"]].dropna().sort_values("time")


with st.sidebar:
    st.subheader("Data")
    source = st.radio("Kilde", ["Yahoo Finance (live-ish)", "CSV"], horizontal=False)
    symbol_label = st.selectbox("Symbol", list(SYMBOLS), index=0)
    ticker = SYMBOLS[symbol_label]
    lookback = st.slider("Historik (dage, Yahoo 15M max ~59)", 10, 59, 45)
    csv = st.file_uploader("CSV (time,open,high,low,close)", type="csv") if source == "CSV" else None

    st.subheader("Position")
    balance = st.number_input("Konto (USD)", 100.0, 10_000_000.0, 10_000.0)
    risk_pct = st.number_input("Risiko pr. trade (%)", 0.1, 5.0, 1.0, 0.1)
    contract = st.number_input("Kontraktstørrelse (oz/lot)", 1, 1000, 100)

    st.subheader("Regler")
    p = Params(
        swing_n=int(st.number_input("Swing (candles)", 1, 10, 3)),
        range_bars=int(st.number_input("Range (1H-candles)", 24, 500, 96)),
        disp_atr=float(st.number_input("Displacement (x ATR)", 0.5, 5.0, 1.5, 0.1)),
        rr=float(st.number_input("Target (R)", 1.0, 6.0, 2.0, 0.5)),
        spread=float(st.number_input("Spread (pris)", 0.0, 5.0, 0.3, 0.1)),
    )
    st.caption("Yahoo 15-min data er forsinket og dækker typisk kun ~2 måneder.")


def checklist(n: int) -> str:
    names = ["Location", "Liquidity", "Sweep", "Displacement", "BOS"]
    return "  ".join(("✅ " if i < n else "⬜ ") + x for i, x in enumerate(names))


def get_base() -> pd.DataFrame:
    if source == "CSV":
        if csv is None:
            raise RuntimeError("Upload en CSV først, eller skift til Yahoo Finance.")
        return load_csv(csv)
    return fetch_yahoo(ticker, "15m", lookback)


tab_live, tab_chart, tab_bt = st.tabs(["Live signaler", "Chart", "Backtest"])


def draw(chart: pd.DataFrame, trades: pd.DataFrame, calc: pd.DataFrame, show: int) -> None:
    c = chart.tail(show)
    fig = go.Figure(go.Candlestick(x=c.time, open=c.open, high=c.high, low=c.low, close=c.close, name="Pris"))
    row = calc.dropna(subset=["mid"])
    if len(row):
        for name, y in (
            ("Range High", row.rh.iloc[-1]),
            ("Mid Range", row.mid.iloc[-1]),
            ("Range Low", row.rl.iloc[-1]),
        ):
            fig.add_hline(y=y, line_dash="dot", annotation_text=name)
    if len(trades):
        t = trades[trades.entry_time >= c.time.iloc[0]]
        for side, sym, col in (("LONG", "triangle-up", "green"), ("SHORT", "triangle-down", "red")):
            s = t[t.retning == side]
            fig.add_trace(
                go.Scatter(
                    x=s.entry_time,
                    y=s.entry,
                    mode="markers",
                    name=side,
                    text=s.forklaring,
                    marker=dict(symbol=sym, size=12, color=col),
                )
            )
    fig.update_layout(height=480, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)


with tab_live:
    st.write("Tryk opdater for at hente seneste 15-min candles og køre reglerne.")
    if st.button("Opdater signaler", type="primary", use_container_width=True):
        st.session_state["run_live"] = True
    if st.session_state.get("run_live"):
        try:
            data = get_base()
            trades, calc = backtest(data, p)
            last = calc.iloc[-1]
            if pd.isna(last.mid):
                st.info("Ikke nok data til at beregne range endnu. Øg historik eller upload mere CSV.")
            else:
                pct = (last.close - last.rl) / (last.rh - last.rl) * 100
                zone = "Premium" if last.close > last.mid else "Discount"
                st.caption(
                    f"Sidste 15M: {last.time:%d-%m %H:%M} | Pris {last.close:.2f} | {zone} ({pct:.0f}% af range)"
                )
                fresh = trades[trades.entry_time >= calc.time.iloc[-8]] if len(trades) else trades
                state = calc.attrs.get("state")
                pending = state and (len(calc) - 1 - state["i"] <= p.max_wait)
                if len(fresh):
                    s = fresh.iloc[-1]
                    st.success(f"SIGNAL: {s.retning}")
                    lots = balance * risk_pct / 100 / (abs(s.entry - s.sl) * contract)
                    a, b, c, d = st.columns(4)
                    a.metric("Entry", f"{s.entry:.2f}")
                    b.metric("Stop Loss", f"{s.sl:.2f}")
                    c.metric("Take Profit", f"{s.tp:.2f}")
                    d.metric("Lot (ca.)", f"{lots:.2f}")
                    st.write(checklist(5))
                    st.caption(s.forklaring)
                elif pending:
                    d = state["d"]
                    st.warning(
                        f"Sweep taget ({'buy' if d == -1 else 'sell'}-side @ {state['lvl']:.2f}). "
                        f"Afventer displacement og BOS → mulig {'SHORT' if d == -1 else 'LONG'}."
                    )
                    st.write(checklist(3))
                else:
                    st.info("NO TRADE – vent på næste sweep.")
                    st.write(checklist(1 if abs(pct - 50) >= 10 else 0))
                st.subheader("Seneste signaler i datasættet")
                if len(trades):
                    st.dataframe(trades.tail(20), use_container_width=True)
                else:
                    st.caption("Ingen trades med de valgte parametre.")
        except Exception as e:
            st.error(str(e))
    else:
        st.info("Tryk på knappen ovenfor. Yahoo-data er ikke tick-live som MT5.")


with tab_chart:
    show = st.slider("Candles", 80, 800, 250)
    view = st.selectbox("Timeframe til visning", list(TF_YF), index=0)
    if st.button("Tegn chart", use_container_width=True):
        try:
            base = get_base()
            trades, calc = backtest(base, p)
            if view == "15M":
                chart = base
            else:
                chart = fetch_yahoo(ticker, TF_YF[view], 365 if view == "1D" else 59)
            draw(chart, trades, calc, show)
        except Exception as e:
            st.error(str(e))


with tab_bt:
    st.write("Kører reglerne på hele det indlæste 15-min datasæt.")
    if st.button("Kør backtest", type="primary", use_container_width=True):
        try:
            data = get_base()
            st.session_state.bt = backtest(data, p) + (data,)
        except Exception as e:
            st.error(str(e))
    if "bt" in st.session_state:
        tr, calc, data = st.session_state.bt
        st.caption(f"{len(data)} candles · {data.time.iloc[0]} → {data.time.iloc[-1]}")
        if tr.empty:
            st.warning("Ingen trades med disse parametre.")
        else:
            st.dataframe(pd.Series(stats(tr)).to_frame("Værdi"))
            st.line_chart(tr.set_index("exit_time").r.cumsum(), height=200)
            st.subheader("Journal")
            st.dataframe(tr, use_container_width=True)
            st.download_button("Download journal (CSV)", tr.to_csv(index=False), "journal.csv")

st.divider()
st.caption(
    "Regelbaserede signaler, ikke en garanti. Appen handler ikke selv. "
    "Yahoo-priser ≠ din brokers XAUUSD-pris. Tjek altid selv før du handler."
)
