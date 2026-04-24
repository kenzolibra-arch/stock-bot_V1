import yfinance as yf
import pandas as pd
import numpy as np
import json
import os

STATE_FILE = "state.json"

# =========================
# 工具函數
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
# 技術指標
# =========================

def add_indicators(df):
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()

    # OBV
    obv = [0]
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
            obv.append(obv[-1] + df['Volume'].iloc[i])
        elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
            obv.append(obv[-1] - df['Volume'].iloc[i])
        else:
            obv.append(obv[-1])
    df['OBV'] = obv

    return df

# =========================
# 市場風控（V10.6）
# =========================

def get_risk_cap():
    try:
        nasdaq = yf.download("^IXIC", period="3mo", progress=False)
        vix = yf.download("^VIX", period="1mo", progress=False)

        nasdaq_ma20 = nasdaq['Close'].rolling(20).mean().iloc[-1]
        nasdaq_price = nasdaq['Close'].iloc[-1]

        vix_value = vix['Close'].iloc[-1]

        if nasdaq_price > nasdaq_ma20 and vix_value < 20:
            return 1.0, "RISK_ON"
        elif vix_value > 25:
            return 0.3, "RISK_OFF"
        else:
            return 0.6, "NEUTRAL"

    except:
        return 0.5, "UNKNOWN"

# =========================
# 趨勢判定
# =========================

def is_trending_up(df):
    cond1 = df['Close'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]
    cond2 = df['Close'].iloc[-1] > df['High'].rolling(20).max().iloc[-2]
    cond3 = df['OBV'].iloc[-1] > df['OBV'].rolling(20).mean().iloc[-1]

    return cond1 and cond2 and cond3

# =========================
# 加碼條件
# =========================

def should_add(df, last_add_price):
    price = df['Close'].iloc[-1]

    if last_add_price == 0:
        return True

    cond1 = price > last_add_price
    cond2 = price > df['MA5'].iloc[-1]
    cond3 = price >= last_add_price * 1.03

    return cond1 and cond2 and cond3

# =========================
# 風控
# =========================

def risk_control(df, entry_price):
    price = df['Close'].iloc[-1]

    if price < df['MA20'].iloc[-1]:
        return "STOP_ADD"

    if entry_price != 0 and price < entry_price * 0.95:
        return "REDUCE"

    return "HOLD"

# =========================
# 倉位階段
# =========================

POSITION_STAGES = {
    "INIT": 0.2,
    "ADD_1": 0.3,
    "ADD_2": 0.4,
    "FULL": 1.0
}

# =========================
# 主策略
# =========================

def run():
    ticker = "0050.TW"

    df = yf.download(ticker, period="6mo", progress=False)
    df = add_indicators(df)

    state = load_state()

    risk_cap, risk_status = get_risk_cap()

    trend = is_trending_up(df)
    risk = risk_control(df, state["entry_price"])

    action = "HOLD"

    # === 初始化進場 ===
    if state["entry_price"] == 0 and trend:
        state["entry_price"] = df['Close'].iloc[-1]
        state["last_add_price"] = df['Close'].iloc[-1]
        state["stage"] = "INIT"
        action = "INITIAL_ENTRY"

    # === 風控 ===
    elif risk == "REDUCE":
        state = {
            "stage": "INIT",
            "entry_price": 0,
            "last_add_price": 0
        }
        action = "EXIT"

    elif risk == "STOP_ADD":
        action = "STOP_ADD"

    # === 加碼 ===
    elif trend and should_add(df, state["last_add_price"]):

        if state["stage"] == "INIT":
            state["stage"] = "ADD_1"
        elif state["stage"] == "ADD_1":
            state["stage"] = "ADD_2"
        elif state["stage"] == "ADD_2":
            state["stage"] = "FULL"

        state["last_add_price"] = df['Close'].iloc[-1]
        action = f"ADD_{state['stage']}"

    position = POSITION_STAGES[state["stage"]] * risk_cap

    save_state(state)

    print("===== V11 SIGNAL =====")
    print(f"Ticker: {ticker}")
    print(f"Risk: {risk_status} (cap={risk_cap})")
    print(f"Trend: {trend}")
    print(f"Action: {action}")
    print(f"Stage: {state['stage']}")
    print(f"Position: {round(position*100,2)}%")
    print(f"Price: {df['Close'].iloc[-1]}")

# =========================

if __name__ == "__main__":
    run()
