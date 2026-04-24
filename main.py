# === V10.9 QUANT ENGINE (FULL CHINESE REPORT + DATA ENGINE) ===

import yfinance as yf
import pandas as pd
import ta
import requests
import os
import json
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"

# =====================================================
# 中文狀態說明
# =====================================================

STATE_DESC = {
    "FLAT": "0（空倉狀態）",
    "ENTRY": "0.2（試單 / 初始進場）",
    "ADD_1": "0.3（確認趨勢加碼）",
    "ADD_2": "0.4（主升段加碼）",
    "FULL": "1.0（滿倉 / 趨勢極限）"
}

SIGNAL_DESC = {
    "HOLD": "觀望",
    "🟡 ENTRY": "試單 / 初始進場",
    "🟢 STRONG": "趨勢強勢",
    "🟢 FULL TREND": "主升段",
    "🔴 TREND BROKEN": "趨勢破壞 / 減碼",
    "🔴 TAKE PROFIT": "獲利了結"
}

MARKET_DESC = {
    "STRONG_BULL": "多頭趨勢（科技+半導體同步強勢）",
    "BEAR": "空頭趨勢（風險資產走弱）",
    "MIXED": "分歧市場（結構不一致）",
    "UNKNOWN": "未知狀態"
}

MACRO_DESC = {
    "RISK_ON": "資金寬鬆（流動性充裕，偏多環境）",
    "RISK_OFF": "資金收縮（風險升高，防禦環境）",
    "NEUTRAL": "中性環境（無明確方向）"
}

# =====================================================
# DATA ENGINE（穩定版）
# =====================================================

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

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()

    except:
        return None


def add_indicators(df):

    df = df.copy()

    close = df["Close"]
    volume = df["Volume"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    close = pd.Series(close).astype(float)
    volume = pd.Series(volume).astype(float)

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    df["RSI"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(
        close, volume
    ).on_balance_volume()

    df["DEV"] = (close - df["MA10"]) / df["MA10"]

    return df.dropna()

# =====================================================
# 趨勢破壞判斷
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
# STATE ENGINE
# =====================================================

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))

def update_state(state, ticker, score, tb):

    if ticker not in state:
        state[ticker] = "FLAT"

    cur = state[ticker]

    if tb or score < 40:
        if cur == "FULL":
            new = "ADD_2"
        elif cur == "ADD_2":
            new = "ADD_1"
        elif cur == "ADD_1":
            new = "ENTRY"
        else:
            new = "FLAT"
    else:
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
        signal = "🟢 STRONG TREND"
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
# FORMAT (中文報告版)
# =====================================================

def format_block(name, r):

    if r is None:
        return f"\n====================\n📊 {name}\n❌ 無資料\n"

    # ===== 趨勢破壞中文說明 =====
    tb_text = (
        "否（仍然完整，可持有/加碼）"
        if not r['tb']
        else "是（已破壞，應減碼/出場）"
    )

    return f"""
====================
📊 {name}

🏷️ 狀態: {r['state']} - {STATE_DESC.get(r['state'], "")}
📡 訊號: {SIGNAL_DESC.get(r['signal'], r['signal'])}

💰 價格: {r['price']:.2f}
📊 分數: {r['score']:.0f}
📦 倉位: {r['pos']}%

📊 RSI: {r['rsi']:.1f}

⚠️ 趨勢破壞: {tb_text}
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

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"""
📊 V10.9 QUANT REPORT ({now})

"""

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
