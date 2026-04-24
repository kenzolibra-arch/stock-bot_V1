# === V10.9 QUANT ENGINE (DATA ENGINE STABLE VERSION) ===

import yfinance as yf
import pandas as pd
import ta
import requests
import os
import json
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"

# =====================================================
# STATE
# =====================================================

STATE_DESC = {
    "FLAT": "0（空倉狀態）",
    "ENTRY": "0.2（試單）",
    "ADD_1": "0.3（確認趨勢加碼）",
    "ADD_2": "0.4（主升段加碼）",
    "FULL": "1.0（滿倉）"
}

# =====================================================
# SAFE DATA ENGINE (CORE FIX)
# =====================================================

def clean_series(x):
    """
    🧠 V10.9 핵心：統一 1D data
    """
    if isinstance(x, pd.DataFrame):
        x = x.iloc[:, 0]
    return pd.Series(x).squeeze()

def safe_download(ticker):
    try:
        df = yf.download(
            ticker,
            period="1y",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if df is None or df.empty:
            return None

        # remove multiindex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()

        return df

    except:
        return None

# =====================================================
# INDICATORS (FIXED)
# =====================================================

def add_indicators(df):

    df = df.copy()

    close = df["Close"]

    # ✅ 強制 Series（關鍵）
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.Series(close).astype(float)

    volume = df["Volume"]

    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    volume = pd.Series(volume).astype(float)

    # =====================
    # INDICATORS (FIXED)
    # =====================

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    # ✅ RSI FIX (IMPORTANT)
    df["RSI"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    # OBV
    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

    return df.dropna()

# =====================================================
# STATE ENGINE
# =====================================================

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))

# =====================================================
# TREND BREAK (V10.8 LOGIC)
# =====================================================

def trend_broken(df):

    try:
        price = df["Close"].iloc[-1]
        ma20 = df["MA20"].iloc[-1]
        ma10 = df["MA10"].iloc[-1]

        obv = df["OBV"].iloc[-1]
        obv_ma = df["OBV"].rolling(20).mean().iloc[-1]

        if price < ma20 and ma10 < ma20:
            return True

        if obv < obv_ma:
            return True

        return False

    except:
        return False

# =====================================================
# SCORE ENGINE
# =====================================================

def score_engine(price, ma10, rsi):

    score = 50

    if price > ma10:
        score += 10
    else:
        score -= 10

    if rsi > 65:
        score += 10
    if rsi < 50:
        score -= 10

    return max(0, min(100, score))

# =====================================================
# STATE MACHINE (V10.8 + SAFE DATA)
# =====================================================

def update_state(state, ticker, score, tb):

    if ticker not in state:
        state[ticker] = "FLAT"

    cur = state[ticker]

    # 🔴 EXIT LOGIC
    if tb or score < 40:
        if cur == "FULL":
            new = "ADD_2"
        elif cur == "ADD_2":
            new = "ADD_1"
        elif cur == "ADD_1":
            new = "ENTRY"
        else:
            new = "FLAT"

        state[ticker] = new
        return state, new

    # 🟢 ENTRY LOGIC
    if score >= 80:
        new = "FULL"
    elif score >= 65:
        new = "ADD_2"
    elif score >= 50:
        new = "ADD_1"
    elif score >= 35:
        new = "ENTRY"
    else:
        new = "FLAT"

    state[ticker] = new
    return state, new

def position_map(s):
    return {
        "FLAT": 0,
        "ENTRY": 0.2,
        "ADD_1": 0.3,
        "ADD_2": 0.4,
        "FULL": 1.0
    }.get(s, 0)

# =====================================================
# ANALYZE
# =====================================================

def analyze(df, state, ticker):

    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]

    score = score_engine(price, ma10, rsi)

    tb = trend_broken(df)

    state, pos_state = update_state(state, ticker, score, tb)

    pos = int(position_map(pos_state) * 40)

    signal = "HOLD"
    if tb:
        signal = "🔴 TREND BROKEN"
    elif pos_state == "FULL":
        signal = "🟢 FULL TREND"
    elif pos_state == "ADD_2":
        signal = "🟢 STRONG"
    elif pos_state == "ENTRY":
        signal = "🟡 ENTRY"

    return {
        "price": price,
        "score": score,
        "state": pos_state,
        "pos": pos,
        "signal": signal,
        "rsi": rsi,
        "tb": tb
    }, state

# =====================================================
# FORMAT (clean separation)
# =====================================================

def format_block(name, r):

    if r is None:
        return f"\n====================\n📊 {name}\n❌ NO DATA\n"

    return f"""
====================
📊 {name}

🧠 State: {r['state']}
📡 Signal: {r['signal']}

💰 Price: {r['price']:.2f}
📊 Score: {r['score']:.0f}
📦 Pos: {r['pos']}%

📊 RSI: {r['rsi']:.1f}
⚠️ Trend Broken: {r['tb']}
====================
"""

# =====================================================
# RUN
# =====================================================

def run():

    assets = {
        "0050": "0050.TW",
        "00631L": "00631L.TW",
        "00662": "00662.TW",
        "00646": "00646.TW",
        "00735": "00735.TW",
        "6770": "6770.TW"
    }

    data = {}

    for k, v in assets.items():
        df = safe_download(v)
        if df is not None:
            df = add_indicators(df)
            if df is not None and len(df) > 30:
                data[k] = df

    state = load_state()

    results = {}

    for k, df in data.items():
        res, state = analyze(df, state, k)
        results[k] = res

    save_state(state)

    msg = "📊 V10.9 DATA ENGINE REPORT\n"

    for k in results:
        msg += format_block(k, results[k])

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        print(msg)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=10)

# =====================================================

if __name__ == "__main__":
    run()
