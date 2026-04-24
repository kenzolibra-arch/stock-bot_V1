import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests

STATE_FILE = "state.json"

# =========================
# TELEGRAM (CRON SAFE)
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        print("TG:", r.status_code)

    except Exception as e:
        print("TG ERROR:", e)

# =========================
# STATE (only persistence)
# =========================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    return {
        "position_state": "FLAT",
        "entry_price": 0,
        "last_add_price": 0
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# =========================
# DATA
# =========================

def fetch_data():
    df = yf.download("0050.TW", period="6mo", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    if len(df) < 80:
        return None

    return df

# =========================
# INDICATORS
# =========================

def add_indicators(df):

    close = df["Close"].values
    volume = df["Volume"].values

    df["MA5"] = pd.Series(close).rolling(5).mean()
    df["MA20"] = pd.Series(close).rolling(20).mean()
    df["MA60"] = pd.Series(close).rolling(60).mean()

    obv = np.zeros(len(df))

    for i in range(1, len(df)):
        if close[i] > close[i-1]:
            obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]:
            obv[i] = obv[i-1] - volume[i]
        else:
            obv[i] = obv[i-1]

    df["OBV"] = obv

    return df

# =========================
# MARKET RISK (V10.6保留)
# =========================

def get_risk_cap():
    try:
        nasdaq = yf.download("^IXIC", period="3mo", progress=False)
        vix = yf.download("^VIX", period="1mo", progress=False)

        if nasdaq.empty or vix.empty:
            return 0.5, "UNKNOWN"

        if nasdaq["Close"].rolling(20).mean().iloc[-1] < nasdaq["Close"].iloc[-1] and vix["Close"].iloc[-1] < 20:
            return 1.0, "RISK_ON"
        elif vix["Close"].iloc[-1] > 25:
            return 0.3, "RISK_OFF"
        else:
            return 0.6, "NEUTRAL"

    except:
        return 0.5, "UNKNOWN"

# =========================
# TREND
# =========================

def is_trending(df):

    if df is None or len(df) < 60:
        return False

    try:
        c = df["Close"].iloc[-1]

        return (
            c > df["MA20"].iloc[-1] > df["MA60"].iloc[-1]
            and c > df["High"].rolling(20).max().iloc[-2]
            and df["OBV"].iloc[-1] > df["OBV"].rolling(20).mean().iloc[-1]
        )

    except:
        return False

# =========================
# RISK CONTROL
# =========================

def risk_control(df, entry):

    price = df["Close"].iloc[-1]

    if price < df["MA20"].iloc[-1]:
        return "EXIT"

    if entry > 0 and price < entry * 0.95:
        return "LIQUIDATE"

    return "HOLD"

# =========================
# POSITION MAP
# =========================

POSITION_MAP = {
    "FLAT": 0,
    "ENTRY": 0.2,
    "ADD_1": 0.3,
    "ADD_2": 0.4,
    "FULL": 1.0
}

# =========================
# MAIN (CRON SAFE)
# =========================

def run():

    df = fetch_data()

    if df is None:
        print("No data")
        return

    df = add_indicators(df)

    state = load_state()

    risk_cap, risk_status = get_risk_cap()

    trend = is_trending(df)

    risk_signal = risk_control(df, state["entry_price"])

    price = df["Close"].iloc[-1]

    # =========================
    # STATE UPDATE (safe)
    # =========================

    new_state = state["position_state"]

    if risk_signal == "LIQUIDATE":
        new_state = "FLAT"

    elif state["position_state"] == "FLAT" and trend:
        new_state = "ENTRY"

    elif state["position_state"] == "ENTRY":
        new_state = "ADD_1"

    elif state["position_state"] == "ADD_1":
        new_state = "ADD_2"

    elif state["position_state"] == "ADD_2":
        new_state = "FULL"

    # update state
    if new_state == "FLAT":
        state["entry_price"] = 0
        state["last_add_price"] = 0
    elif state["position_state"] == "FLAT" and new_state == "ENTRY":
        state["entry_price"] = price

    state["position_state"] = new_state

    save_state(state)

    position = POSITION_MAP[new_state] * risk_cap

    # =========================
    # CRON OUTPUT (ONLY ONCE)
    # =========================

    msg = f"""
📊 V10.7 CRON REPORT

Price: {price:.2f}
State: {new_state}
Trend: {trend}
Risk: {risk_status}

Position: {round(position*100,2)}%
Signal: {risk_signal}
"""

    print(msg)

    send_telegram(msg)

# =========================

if __name__ == "__main__":
    run()
