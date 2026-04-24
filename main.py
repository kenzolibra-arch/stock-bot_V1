import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests

STATE_FILE = "state.json"

# =====================================================
# TELEGRAM
# =====================================================

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        print("TG:", r.status_code)

    except Exception as e:
        print("TG ERROR:", e)

# =====================================================
# STATE
# =====================================================

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))

    return {
        "state": "FLAT",
        "entry": 0
    }

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))

# =====================================================
# DATA
# =====================================================

def fetch():
    df = yf.download("0050.TW", period="6mo", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    return df if len(df) > 80 else None

# =====================================================
# INDICATORS
# =====================================================

def add_ind(df):

    c = df["Close"].values
    v = df["Volume"].values

    df["MA20"] = pd.Series(c).rolling(20).mean()
    df["MA60"] = pd.Series(c).rolling(60).mean()

    obv = np.zeros(len(df))

    for i in range(1, len(df)):
        if c[i] > c[i-1]:
            obv[i] = obv[i-1] + v[i]
        elif c[i] < c[i-1]:
            obv[i] = obv[i-1] - v[i]
        else:
            obv[i] = obv[i-1]

    df["OBV"] = obv

    return df

# =====================================================
# GLOBAL MARKET (V10.6保留)
# =====================================================

def market():

    try:
        nq = yf.download("^IXIC", period="3mo", progress=False)
        vix = yf.download("^VIX", period="1mo", progress=False)

        nq_ma = nq["Close"].rolling(20).mean().iloc[-1]
        nq_p = nq["Close"].iloc[-1]
        v = vix["Close"].iloc[-1]

        if nq_p > nq_ma and v < 20:
            return 1.0, "RISK_ON"

        if v > 25:
            return 0.3, "RISK_OFF"

        return 0.6, "NEUTRAL"

    except:
        return 0.5, "UNKNOWN"

# =====================================================
# TREND
# =====================================================

def trend(df):

    try:
        c = df["Close"].iloc[-1]

        return (
            c > df["MA20"].iloc[-1] > df["MA60"].iloc[-1]
            and df["OBV"].iloc[-1] > df["OBV"].rolling(20).mean().iloc[-1]
        )

    except:
        return False

# =====================================================
# RISK CONTROL
# =====================================================

def risk(df, entry):

    p = df["Close"].iloc[-1]

    if p < df["MA20"].iloc[-1]:
        return "EXIT"

    if entry > 0 and p < entry * 0.95:
        return "LIQUIDATE"

    return "HOLD"

# =====================================================
# STATE MACHINE
# =====================================================

def next_state(s, t, r):

    if r == "LIQUIDATE":
        return "FLAT"

    if s == "FLAT" and t:
        return "ENTRY"

    if s == "ENTRY":
        return "ADD_1"

    if s == "ADD_1":
        return "ADD_2"

    if s == "ADD_2":
        return "FULL"

    return s

# =====================================================
# POSITION
# =====================================================

POS = {
    "FLAT": 0,
    "ENTRY": 0.2,
    "ADD_1": 0.3,
    "ADD_2": 0.4,
    "FULL": 1.0
}

# =====================================================
# MAIN (V10.6 FORMAT + V10.7 EXTENSION)
# =====================================================

def run():

    df = fetch()

    if df is None:
        print("no data")
        return

    df = add_ind(df)

    state = load_state()

    cap, risk_state = market()

    t = trend(df)

    r = risk(df, state["entry"])

    price = df["Close"].iloc[-1]

    new_state = next_state(state["state"], t, r)

    if state["state"] == "FLAT" and new_state == "ENTRY":
        state["entry"] = price

    if new_state == "FLAT":
        state["entry"] = 0

    state["state"] = new_state

    save_state(state)

    position = POS[new_state] * cap

    # =====================================================
    # V10.6 FORMAT REPORT (保留原結構)
    # =====================================================

    msg = f"""
=============================
📊 V10.6 MARKET REPORT + V10.7 UPGRADE
=============================

🌍 大環境分析
- Risk State: {risk_state}
- Risk Cap: {cap}

📈 個股分析 (0050.TW)
- Price: {price:.2f}
- Trend: {t}
- Risk Signal: {r}

📊 技術面
- MA20: {df['MA20'].iloc[-1]:.2f}
- MA60: {df['MA60'].iloc[-1]:.2f}

🧠 交易狀態 (V10.7 STATE MACHINE)
- State: {new_state}
- Entry Price: {state['entry']}

💰 倉位控制
- Position: {round(position*100,2)}%

📌 訊號說明
- ENTRY / ADD / FULL 為加碼階段
- FLAT 為空倉
=============================
"""

    print(msg)

    send_telegram(msg)

# =====================================================

if __name__ == "__main__":
    run()
