import yfinance as yf
import pandas as pd
import numpy as np
import json
import os

STATE_FILE = "state.json"

# =========================
# STATE
# =========================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    return {
        "stage": "INIT",
        "entry_price": 0,
        "last_add_price": 0
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# =========================
# DATA LAYER (V11.2 CORE)
# =========================

def fetch_data(ticker):
    try:
        df = yf.download(ticker, period="6mo", progress=False)

        # flatten MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 必要欄位檢查
        required = ["Close", "High", "Low", "Volume"]
        if df is None or df.empty:
            return None

        for col in required:
            if col not in df.columns:
                return None

        df = df.dropna()

        # 最低資料門檻（關鍵）
        if len(df) < 80:
            return None

        return df

    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return None

# =========================
# INDICATORS (SAFE MODE)
# =========================

def add_indicators(df):

    close = df["Close"].values
    volume = df["Volume"].values

    df["MA5"] = pd.Series(close).rolling(5).mean()
    df["MA20"] = pd.Series(close).rolling(20).mean()
    df["MA60"] = pd.Series(close).rolling(60).mean()

    # OBV safe numpy
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
# RISK ENGINE (V10.6)
# =========================

def get_risk_cap():
    try:
        nasdaq = yf.download("^IXIC", period="3mo", progress=False)
        vix = yf.download("^VIX", period="1mo", progress=False)

        if nasdaq.empty or vix.empty:
            return 0.5, "UNKNOWN"

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
# TREND ENGINE (HARD SAFE)
# =========================

def is_trending_up(df):

    if df is None or len(df) < 60:
        return False

    try:
        close = df["Close"].iloc[-1]

        ma20 = df["MA20"].iloc[-1]
        ma60 = df["MA60"].iloc[-1]

        if np.isnan(close) or np.isnan(ma20) or np.isnan(ma60):
            return False

        cond1 = close > ma20 > ma60

        cond2 = close > df["High"].rolling(20).max().iloc[-2]

        cond3 = df["OBV"].iloc[-1] > df["OBV"].rolling(20).mean().iloc[-1]

        return cond1 and cond2 and cond3

    except:
        return False

# =========================
# ADD CONDITION
# =========================

def should_add(df, last_price):

    price = df["Close"].iloc[-1]

    if last_price == 0:
        return True

    return (
        price > last_price and
        price > df["MA5"].iloc[-1] and
        price >= last_price * 1.03
    )

# =========================
# RISK CONTROL
# =========================

def risk_control(df, entry_price):

    price = df["Close"].iloc[-1]

    if price < df["MA20"].iloc[-1]:
        return "STOP_ADD"

    if entry_price > 0 and price < entry_price * 0.95:
        return "REDUCE"

    return "HOLD"

# =========================
# POSITION MODEL
# =========================

POSITION_STAGES = {
    "INIT": 0.2,
    "ADD_1": 0.3,
    "ADD_2": 0.4,
    "FULL": 1.0
}

# =========================
# MAIN ENGINE
# =========================

def run():

    ticker = "0050.TW"

    df = fetch_data(ticker)

    if df is None:
        print("❌ Data invalid (fetch_data failed)")
        return

    df = add_indicators(df)

    # ===== DATA CONTRACT CHECK (V11.2 핵심) =====
    if df is None or df.empty:
        print("❌ Empty dataframe after indicators")
        return

    if len(df) < 80:
        print(f"❌ Not enough data: {len(df)}")
        return

    state = load_state()

    risk_cap, risk_status = get_risk_cap()

    trend = is_trending_up(df)
    risk = risk_control(df, state["entry_price"])

    price = df["Close"].iloc[-1]
    action = "HOLD"

    # =========================
    # ENTRY
    # =========================
    if state["entry_price"] == 0 and trend:
        state["entry_price"] = price
        state["last_add_price"] = price
        state["stage"] = "INIT"
        action = "INITIAL_ENTRY"

    # =========================
    # EXIT
    # =========================
    elif risk == "REDUCE":
        state = {
            "stage": "INIT",
            "entry_price": 0,
            "last_add_price": 0
        }
        action = "EXIT"

    elif risk == "STOP_ADD":
        action = "STOP_ADD"

    # =========================
    # ADD POSITION
    # =========================
    elif trend and should_add(df, state["last_add_price"]):

        if state["stage"] == "INIT":
            state["stage"] = "ADD_1"
        elif state["stage"] == "ADD_1":
            state["stage"] = "ADD_2"
        elif state["stage"] == "ADD_2":
            state["stage"] = "FULL"

        state["last_add_price"] = price
        action = f"ADD_{state['stage']}"

    position = POSITION_STAGES[state["stage"]] * risk_cap

    save_state(state)

    # =========================
    # OUTPUT
    # =========================

    print("===== V11.2 SIGNAL =====")
    print(f"Ticker: {ticker}")
    print(f"Price: {round(price,2)}")
    print(f"Risk: {risk_status} ({risk_cap})")
    print(f"Trend: {trend}")
    print(f"Action: {action}")
    print(f"Stage: {state['stage']}")
    print(f"Position: {round(position*100,2)}%")

# =========================

if __name__ == "__main__":
    run()
