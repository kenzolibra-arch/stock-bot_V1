# === V9.1.14 STABLE PRODUCTION VERSION ===
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import requests
import os
from datetime import datetime, timezone, timedelta

# =========================
# 1️⃣ 安全下載（核心修復）
# =========================
def safe_download(ticker):
    try:
        df = yf.download(
            ticker,
            period="1y",
            interval="1d",
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()

    except Exception as e:
        print(f"❌ {ticker} 下載失敗: {e}")
        return None


# =========================
# 2️⃣ 數據抓取
# =========================
def get_data():
    assets = {
        "0050": "0050.TW",
        "00631L": "00631L.TW",
        "6770": "6770.TW",
        "NASDAQ": "^IXIC",
        "VIX": "^VIX"
    }

    data = {}

    for k, v in assets.items():
        df = safe_download(v)
        if df is None:
            continue

        # 00631L 拆股修正
        if k == "00631L":
            try:
                current_p = df["Close"].iloc[-1]
                if df["Close"].max() / current_p > 10:
                    df.loc[df["Close"] > 80, "Close"] /= 22
            except:
                pass

        data[k] = df

    return data


# =========================
# 3️⃣ 技術指標
# =========================
def add_indicators(df):
    df = df.copy()

    close = df["Close"]

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
    df["BB_UPPER"] = bb.bollinger_hband()
    df["BB_LOWER"] = bb.bollinger_lband()

    df["RSI"] = ta.momentum.RSIIndicator(close, 14).rsi()
    df["DEV"] = (close - df["MA10"]) / df["MA10"]

    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(
        close, df["Volume"]
    ).on_balance_volume()

    return df


# =========================
# 4️⃣ 邏輯分析
# =========================
def get_logic(tag, rsi, chip, vix):
    if vix > 25:
        return f"⚠️ VIX高檔({vix:.1f})，市場風險升高"

    if tag == "🔴 SELL":
        return f"過熱區 RSI:{rsi:.1f}，避免追高"

    if tag == "🟢 DCA":
        return "超跌區，分批佈局較佳" + ("（籌碼強）" if chip else "")

    if tag == "🔵 BUY":
        return "趨勢轉強，可順勢加碼"

    return "震盪區間，觀望為主"


# =========================
# 5️⃣ 分析單一資產
# =========================
def analyze(df, vix):
    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    dev = df["DEV"].iloc[-1]
    bb_up = df["BB_UPPER"].iloc[-1]
    bb_low = df["BB_LOWER"].iloc[-1]

    obv_now = df["OBV"].iloc[-1]
    obv_prev = df["OBV"].rolling(5).mean().iloc[-1]

    chip_strong = obv_now > obv_prev

    # 訊號
    if price > bb_up or dev > 0.08 or rsi > 70:
        tag, score = "🔴 SELL", 0
    elif 0 < dev < 0.03 and rsi > 55:
        tag, score = "🔵 BUY", 2
    elif price < ma10 and (price < bb_low or rsi < 40):
        tag, score = "🟢 DCA", 3
    else:
        tag, score = "🟡 HOLD", 1

    return {
        "price": price,
        "ma10": ma10,
        "rsi": rsi,
        "dev": dev,
        "bb_up": bb_up,
        "bb_low": bb_low,
        "tag": tag,
        "chip": chip_strong,
        "pos": int(min((score / 3) * 30, 40)),
        "stop": ma10 * 0.95,
        "logic": get_logic(tag, rsi, chip_strong, vix)
    }


# =========================
# 6️⃣ 主流程
# =========================
def run():
    data = get_data()

    required = ["0050", "00631L"]
    if not all(k in data for k in required):
        print("❌ 核心數據不足，停止執行")
        return

    processed = {k: add_indicators(v) for k, v in data.items()}

    tw = processed["0050"].iloc[-1]
    us = processed.get("NASDAQ")
    vix = processed.get("VIX")

    vix_val = vix["Close"].iloc[-1] if vix is not None else 20

    tw_ok = tw["Close"] > tw["MA20"] and tw["RSI"] > 50
    us_ok = us["Close"].iloc[-1] > us["MA20"].iloc[-1] if us is not None else True

    if tw_ok and us_ok:
        regime = "🌕強多"
    elif tw_ok or us_ok:
        regime = "🌓震盪偏多"
    else:
        regime = "🌑防守"

    etf = analyze(processed["00631L"], vix_val)
    stock = analyze(processed["6770"], vix_val)

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"""
📊 V9.1.14 STABLE REPORT ({now})

🌎 市場：{regime} | VIX:{vix_val:.1f}

🚀 00631L
📌 {etf['tag']}
💰 {etf['price']:.2f}
RSI:{etf['rsi']:.1f} | 籌碼:{'強' if etf['chip'] else '弱'}
倉位:{etf['pos']}%
支撐:{etf['bb_low']:.2f}
壓力:{etf['bb_up']:.2f}
風控:{etf['stop']:.2f}
🧠 {etf['logic']}

💎 6770
📌 {stock['tag']}
💰 {stock['price']:.2f}
RSI:{stock['rsi']:.1f}
倉位:{stock['pos']}%
🧠 {stock['logic']}
"""

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        print(msg)
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.get(url, params={
            "chat_id": chat_id,
            "text": msg
        }, timeout=10)

        if res.status_code != 200:
            print("❌ Telegram error:", res.text)
        else:
            print("✅ Sent successfully")

    except Exception as e:
        print("❌ Telegram exception:", e)


if __name__ == "__main__":
    run()
