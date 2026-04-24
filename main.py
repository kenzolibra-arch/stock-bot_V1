# === V10.8 QUANT ENGINE (EXIT ENGINE UPGRADE) ===

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
    "ENTRY": "0.2（試單 / 初始進場）",
    "ADD_1": "0.3（確認趨勢加碼）",
    "ADD_2": "0.4（主升段加碼）",
    "FULL": "1.0（滿倉 / 趨勢極限）"
}

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))

# =====================================================
# POSITION STATE MACHINE (UP + DOWN)
# =====================================================

def update_state(state, ticker, score, trend_broken):

    if ticker not in state:
        state[ticker] = "FLAT"

    current = state[ticker]

    # =========================
    # DOWNGRADE LOGIC (NEW)
    # =========================

    if trend_broken or score < 40:
        if current == "FULL":
            new_state = "ADD_2"
        elif current == "ADD_2":
            new_state = "ADD_1"
        elif current == "ADD_1":
            new_state = "ENTRY"
        else:
            new_state = "FLAT"
        state[ticker] = new_state
        return state, new_state

    # =========================
    # UPGRADE LOGIC
    # =========================

    if score >= 80:
        new_state = "FULL"
    elif score >= 65:
        new_state = "ADD_2"
    elif score >= 50:
        new_state = "ADD_1"
    elif score >= 35:
        new_state = "ENTRY"
    else:
        new_state = "FLAT"

    state[ticker] = new_state
    return state, new_state

def position_map(state):
    return {
        "FLAT": 0,
        "ENTRY": 0.2,
        "ADD_1": 0.3,
        "ADD_2": 0.4,
        "FULL": 1.0
    }.get(state, 0)

# =====================================================
# DATA
# =====================================================

def safe_download(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df is None or df.empty:
            return None
        return df.dropna()
    except:
        return None

def add_indicators(df):

    close = df["Close"]

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    df["RSI"] = ta.momentum.RSIIndicator(close, 14).rsi()
    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(close, df["Volume"]).on_balance_volume()

    return df.dropna()

# =====================================================
# TREND BREAK DETECTION (NEW)
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
# SCORE
# =====================================================

def score_engine(price, ma10, rsi, market_state, macro_state):

    score = 50

    if price > ma10:
        score += 10
    else:
        score -= 10

    if rsi > 65:
        score += 10
    if rsi < 50:
        score -= 10

    if market_state == "BEAR":
        score -= 15

    if macro_state == "RISK_ON":
        score += 5

    return max(0, min(100, score))

# =====================================================
# ANALYZE
# =====================================================

def analyze(df, score, state, ticker):

    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]

    tb = trend_broken(df)

    state, pos_state = update_state(state, ticker, score, tb)

    pos = int(position_map(pos_state) * 40)

    signal = "HOLD"
    if tb:
        signal = "🔴 TREND BROKEN / REDUCE"
    elif pos_state == "FULL" and score < 70:
        signal = "🔴 TAKE PROFIT"
    elif pos_state == "ADD_2":
        signal = "🟢 STRONG TREND"
    elif pos_state == "ENTRY":
        signal = "🟡 BUILD POSITION"

    return {
        "price": price,
        "score": score,
        "state": pos_state,
        "pos": pos,
        "signal": signal,
        "ma10": ma10,
        "rsi": rsi,
        "tb": tb
    }, state

# =====================================================
# FORMAT (IMPROVED SEPARATION)
# =====================================================

def format_block(name, r):

    if r is None:
        return f"\n====================\n📊 {name}\n❌ 無資料\n"

    return f"""
====================
📊 {name}

🏷️ State: {r['state']}
📡 Signal: {r['signal']}

💰 Price: {r['price']:.2f}
📊 Score: {r['score']:.0f}
📦 Position: {r['pos']}%

📉 MA10: {r['ma10']:.2f}
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
            data[k] = add_indicators(df)

    state = load_state()

    results = {}

    for k, df in data.items():

        score = 50  # simplified (可再接 macro V10.7)
        res, state = analyze(df, score, state, k)
        results[k] = res

    save_state(state)

    msg = "📊 V10.8 EXIT ENGINE REPORT\n"

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
