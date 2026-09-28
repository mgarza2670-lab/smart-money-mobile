"""Smart Money System - regelmotor + backtest (resultater i R)."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Params:
    swing_n: int = 3          # candles på hver side af en swing
    range_bars: int = 96      # antal 1H-candles i rangen
    sweep_lookback: int = 60  # max alder (15M-candles) på swing der sweepes
    max_wait: int = 8         # candles fra sweep til displacement
    disp_atr: float = 1.5     # displacement: candle-krop >= x * ATR
    sl_buf_atr: float = 0.1   # buffer bag sweep-extreme, i ATR
    rr: float = 2.0           # target i R
    spread: float = 0.3       # omkostning i pris (XAUUSD)


def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def add_range(df, p):
    """Range fra afsluttede 1H-candles (ingen lookahead). Mid = 50%."""
    d = df.set_index("time")
    h1 = d.resample("1h").agg({"high": "max", "low": "min"}).dropna()
    h1["rh"] = h1.high.rolling(p.range_bars).max().shift(1)
    h1["rl"] = h1.low.rolling(p.range_bars).min().shift(1)
    h1["mid"] = (h1.rh + h1.rl) / 2
    out = df.copy()
    out[["rh", "rl", "mid"]] = h1[["rh", "rl", "mid"]].reindex(d.index.floor("1h")).to_numpy()
    return out


def backtest(df, p=Params()):
    """df: 15M-data med kolonnerne time, open, high, low, close. Returnerer (trades, df)."""
    df = add_range(df.sort_values("time").reset_index(drop=True), p)
    df["atr"] = atr(df)
    O, H, L, C = (df[c].to_numpy() for c in ("open", "high", "low", "close"))
    A, M, RH, RL = (df[c].to_numpy() for c in ("atr", "mid", "rh", "rl"))
    n, N = p.swing_n, len(df)
    hi = lo = None            # seneste bekræftede swing high/low: (pris, index)
    state, busy, trades = None, -1, []

    for t in range(N):
        j = t - n             # swing bekræftes n candles senere
        if j >= n:
            if H[j] == H[j - n:j + n + 1].max():
                hi = (H[j], j)
            if L[j] == L[j - n:j + n + 1].min():
                lo = (L[j], j)
        if t <= busy or np.isnan(A[t]) or np.isnan(M[t]):
            continue

        if state is None:   # 1) location + liquidity + sweep
            if hi and t - hi[1] <= p.sweep_lookback and H[t] > hi[0] and C[t] < hi[0] and C[t] > M[t]:
                state = dict(d=-1, i=t, x=H[t], lvl=hi[0])
            elif lo and t - lo[1] <= p.sweep_lookback and L[t] < lo[0] and C[t] > lo[0] and C[t] < M[t]:
                state = dict(d=1, i=t, x=L[t], lvl=lo[0])
            continue

        if t - state["i"] > p.max_wait:
            state = None
            continue
        d = state["d"]      # 2) displacement + BOS = confirmation
        if d == -1:
            state["x"] = max(state["x"], H[t])
            ok = O[t] - C[t] >= p.disp_atr * A[t] and lo is not None and C[t] < lo[0]
            stop = state["x"] + p.sl_buf_atr * A[t]
        else:
            state["x"] = min(state["x"], L[t])
            ok = C[t] - O[t] >= p.disp_atr * A[t] and hi is not None and C[t] > hi[0]
            stop = state["x"] - p.sl_buf_atr * A[t]
        if not ok:
            continue

        entry, risk = C[t], abs(C[t] - stop)
        if risk <= 0:
            state = None
            continue
        target = entry + d * p.rr * risk
        r, k = None, N - 1
        for k in range(t + 1, N):   # SL først hvis begge rammes i samme candle
            hit_sl = H[k] >= stop if d == -1 else L[k] <= stop
            hit_tp = L[k] <= target if d == -1 else H[k] >= target
            if hit_sl:
                r = -1.0
                break
            if hit_tp:
                r = p.rr
                break
        if r is None:
            r = d * (C[N - 1] - entry) / risk
        r -= p.spread / risk
        pct = (entry - RL[t]) / (RH[t] - RL[t]) * 100 if RH[t] > RL[t] else np.nan
        trades.append(dict(
            entry_time=df.time[t], exit_time=df.time[k], retning="LONG" if d == 1 else "SHORT",
            entry=entry, sl=stop, tp=target, r=round(r, 2),
            forklaring=(f"Location: {'Discount' if d == 1 else 'Premium'} ({pct:.0f}% af range) | "
                        f"Liquidity: {'sell' if d == 1 else 'buy'}-side @ {state['lvl']:.2f} | Sweep: ja | "
                        f"Displacement: {abs(C[t]-O[t])/A[t]:.1f}x ATR | BOS: ja"),
        ))
        busy, state = k, None
    df.attrs.update(state=state, hi=hi, lo=lo)   # afventende setup ved sidste candle
    return pd.DataFrame(trades), df


def stats(tr):
    if tr.empty:
        return {}
    w, l = tr.r[tr.r > 0], tr.r[tr.r <= 0]
    eq = tr.r.cumsum()
    return {
        "Trades": len(tr),
        "Win rate %": round(len(w) / len(tr) * 100, 1),
        "Gns. win (R)": round(w.mean(), 2) if len(w) else 0,
        "Gns. loss (R)": round(l.mean(), 2) if len(l) else 0,
        "Expectancy (R)": round(tr.r.mean(), 3),
        "Profit factor": round(w.sum() / abs(l.sum()), 2) if len(l) and l.sum() else None,
        "Max drawdown (R)": round((eq.cummax() - eq).max(), 2),
        "Total (R)": round(tr.r.sum(), 1),
    }
