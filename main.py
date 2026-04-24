# === V10.7 QUANT ENGINE (FULL + MACRO EXPLAINED) ===

import yfinance as yf
import pandas as pd
import ta
import requests
import os
import json
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"

# =====================================================
# STATE MACHINE
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

def get_position_state(state, ticker, score):

    if ticker not in state:
        state[ticker] = "FLAT"

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
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

def get_data():
    assets = {
        "0050": "0050.TW",
        "00631L": "00631L.TW",
        "00662": "00662.TW",
        "00646": "00646.TW",
        "00735": "00735.TW",
        "6770": "6770.TW",
        "NASDAQ": "^IXIC",
        "SOX": "^SOX",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
        "OIL": "CL=F"
    }

    data = {}
    for k, v in assets.items():
        df = safe_download(v)
        if df is not None:
            data[k] = df
    return data

def add_indicators(df):

    close = df["Close"]

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    bb = ta.volatility.BollingerBands(close, 20, 2)
    df["BB_UPPER"] = bb.bollinger_hband()
    df["BB_LOWER"] = bb.bollinger_lband()

    df["RSI"] = ta.momentum.RSIIndicator(close, 14).rsi()
    df["DEV"] = (close - df["MA10"]) / df["MA10"]
    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(close, df["Volume"]).on_balance_volume()

    return df.dropna()

# =====================================================
# MARKET / MACRO
# =====================================================

def trend(df):
    return df["Close"].iloc[-1] > df["Close"].rolling(20).mean().iloc[-1]

def get_market_state(n, s):
    try:
        if trend(n) and trend(s):
            return "STRONG_BULL"
        elif not trend(n) and not trend(s):
            return "BEAR"
        return "MIXED"
    except:
        return "UNKNOWN"

def get_macro_state(dxy, oil):
    try:
        if not trend(dxy) and not trend(oil):
            return "RISK_ON"
        elif trend(dxy) and trend(oil):
            return "RISK_OFF"
        return "NEUTRAL"
    except:
        return "UNKNOWN"

def get_position_cap(macro_state):
    return {
        "RISK_ON": 40,
        "NEUTRAL": 30,
        "RISK_OFF": 20
    }.get(macro_state, 25)

# =====================================================
# SCORE ENGINE
# =====================================================

def score_engine(price, ma10, rsi, dev, bb_up, bb_low, vix, market_state, macro_state):

    score = 50

    score += 10 if price > ma10 else -10

    if 50 < rsi < 65:
        score += 15
    elif rsi > 75:
        score -= 20

    if dev < -0.05:
        score += 15
    elif dev > 0.05:
        score -= 15

    if price < bb_low:
        score += 10
    elif price > bb_up:
        score += 5 if market_state == "STRONG_BULL" else -10

    if vix > 25:
        score *= 0.7

    if market_state == "BEAR":
        score -= 15

    if macro_state == "RISK_OFF":
        score -= 10
    elif macro_state == "RISK_ON":
        score += 5

    return max(0, min(100, score))

# =====================================================
# ANALYZE
# =====================================================

def analyze(df, vix, market_state, macro_state, cap, state, ticker):

    if df is None or len(df) < 30:
        return None, state, "FLAT"

    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    dev = df["DEV"].iloc[-1]
    bb_up = df["BB_UPPER"].iloc[-1]
    bb_low = df["BB_LOWER"].iloc[-1]

    score = score_engine(price, ma10, rsi, dev, bb_up, bb_low, vix, market_state, macro_state)

    state, pos_state = get_position_state(state, ticker, score)

    pos = min(int(score / 100 * 40), cap)
    pos = max(pos, int(position_map(pos_state) * cap))

    tag = (
        "🚀 主升段" if score >= 80 else
        "🟢 強勢" if score >= 65 else
        "🟡 可布局" if score >= 50 else
        "⚠️ 觀望" if score >= 30 else
        "❌ 風險"
    )

    return {
        "price": price,
        "score": score,
        "tag": tag,
        "pos": pos,
        "cap": cap,
        "stop": ma10 * 0.95,
        "rsi": rsi,
        "bb_up": bb_up,
        "bb_low": bb_low,
        "state": pos_state
    }, state, pos_state

# =====================================================
# FORMAT (MACRO EXPLAINED HERE)
# =====================================================

def format_block(name, r):

    if r is None:
        return f"\n📊 {name}\n❌ 無資料\n"

    return f"""
📊 {name}
🏷️ {r['tag']} ({r['score']:.0f})
💰 {r['price']:.2f}

📦 倉位:{r['pos']}%（上限{r['cap']}%）
🧠 狀態:{r['state']} - {STATE_DESC.get(r['state'], "")}

RSI:{r['rsi']:.1f}
📉 下軌:{r['bb_low']:.2f} | 📈 上軌:{r['bb_up']:.2f}
🛑 停損:{r['stop']:.2f}
"""

# =====================================================
# RUN
# =====================================================

def run():

    data = get_data()
    p = {k: add_indicators(v) for k, v in data.items() if v is not None}

    market = get_market_state(p.get("NASDAQ"), p.get("SOX"))
    macro = get_macro_state(p.get("DXY"), p.get("OIL"))
    cap = get_position_cap(macro)

    vix = p.get("VIX")["Close"].iloc[-1]

    state = load_state()

    assets = ["0050", "00631L", "00662", "00646", "00735", "6770"]

    results = {}

    for k in assets:
        res, state, _ = analyze(
            p.get(k),
            vix,
            market,
            macro,
            cap,
            state,
            k
        )
        results[k] = res

    save_state(state)

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    # =====================================================
    # 🧠 MACRO EXPLAINED OUTPUT
    # =====================================================

    macro_desc = {
        "RISK_ON": "資金寬鬆（流動性充裕，偏多環境）",
        "RISK_OFF": "資金收縮（流動性緊縮，防禦環境）",
        "NEUTRAL": "中性環境（無明確方向）"
    }

    market_desc = {
        "STRONG_BULL": "多頭趨勢（科技+半導體同步強勢）",
        "BEAR": "空頭趨勢（風險資產走弱）",
        "MIXED": "分歧市場（結構不一致）",
        "UNKNOWN": "未知狀態"
    }

    msg = f"""
📊 V10.7 QUANT REPORT ({now})

🌍 市場：{market} - {market_desc.get(market, "")}
🌐 宏觀：{macro} - {macro_desc.get(macro, "")}
📦 倉位上限：{cap}% | VIX:{vix:.1f}

"""

    for k in assets:
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
