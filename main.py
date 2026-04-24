import yfinance as yf
import pandas as pd
import numpy as np
import json
import os

STATE_FILE = "state.json"

# =========================
# STATE LOAD / SAVE
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
# MARKET DATA (V10.6保留)
# =========================

def get_risk_cap():
    try:
        nasdaq = yf.download("^IXIC", period="3mo", progress=False)
        vix = yf.download("^VIX", period="1mo", progress=False)

        nasdaq_ma20 = nasdaq["Close"].rolling(20).mean().iloc[-1]
        nasdaq_price = nasdaq["Close"].iloc[-1]
        vix_value = vix["Close"].iloc[-1]

        if nasdaq_price > nasdaq_ma20 and vix_value < 20:
            return 1.0, "RISK_ON"
        elif vix_value > 25:
            return 0.3, "RISK_OFF"
        else:
            return 0.6, "NEUTRAL"

    except:
        return 0.5, "UNKNOWN"

# =========================
# DATA FETCH
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
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]

    df["OBV"] = obv

    return df

# =========================
# TREND ENGINE (V10.6保留)
# =========================

def is_trending_up(df):

    if df is None or len(df) < 60:
        return False

    close = df["Close"].iloc[-1]

    try:
        cond1 = close > df["MA20"].iloc[-1] > df["MA60"].iloc[-1]
        cond2 = close > df["High"].rolling(20).max().iloc[-2]
        cond3 = df["OBV"].iloc[-1] > df["OBV"].rolling(20).mean().iloc[-1]

        return cond1 and cond2 and cond3

    except:
        return False

# =========================
# RISK CONTROL
# =========================

def risk_control(df, entry_price):

    price = df["Close"].iloc[-1]

    if price < df["MA20"].iloc[-1]:
        return "STOP"

    if entry_price > 0 and price < entry_price * 0.95:
        return "EXIT"

    return "HOLD"

# =========================
# STATE MACHINE (V10.7核心)
# =========================

def next_state(current_state, trend, risk_signal):

    # EXIT優先
    if risk_signal == "EXIT":
        return "FLAT"

    if risk_signal == "STOP":
        return current_state

    # ===== STATE TRANSITION =====

    if current_state == "FLAT":
        if trend:
            return "ENTRY"
        return "FLAT"

    if current_state == "ENTRY":
        return "ADD_1"

    if current_state == "ADD_1":
        return "ADD_2"

    if current_state == "ADD_2":
        return "FULL"

    if current_state == "FULL":
        return "FULL"

    return "FLAT"

# =========================
# POSITION SIZE (保留V10.6)
# =========================

POSITION_MAP = {
    "FLAT": 0,
    "ENTRY": 0.2,
    "ADD_1": 0.3,
    "ADD_2": 0.4,
    "FULL": 1.0
}

# =========================
# MAIN
# =========================

def run():

    df = fetch_data()

    if df is None:
        print("❌ No data")
        return

    df = add_indicators(df)

    state = load_state()

    risk_cap, risk_status = get_risk_cap()

    trend = is_trending_up(df)

    risk_signal = risk_control(df, state["entry_price"])

    price = df["Close"].iloc[-1]

    # =========================
    # STATE MACHINE UPDATE
    # =========================

    new_state = next_state(state["position_state"], trend, risk_signal)

    # entry price handling
    if state["position_state"] == "FLAT" and new_state == "ENTRY":
        state["entry_price"] = price

    if new_state == "FLAT":
        state["entry_price"] = 0
        state["last_add_price"] = 0

    if new_state in ["ADD_1", "ADD_2"]:
        state["last_add_price"] = price

    state["position_state"] = new_state

    save_state(state)

    # =========================
    # OUTPUT
    # =========================

    position = POSITION_MAP[new_state] * risk_cap

    print("===== V10.7 STATE MACHINE =====")
    print(f"Price: {price:.2f}")
    print(f"Risk: {risk_status} ({risk_cap})")
    print(f"Trend: {trend}")
    print(f"State: {new_state}")
    print(f"Action: {risk_signal}")
    print(f"Position: {round(position*100,2)}%")

# =========================

if __name__ == "__main__":
    run()
