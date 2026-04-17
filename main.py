# === V9.3 QUANT FUND ENGINE (STABLE + SPLIT FIX) ===
import yfinance as yf
import pandas as pd
import ta
import requests
import os
from datetime import datetime, timezone, timedelta

# =========================
# SAFE DOWNLOAD
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
        print(f"❌ {ticker} error:", e)
        return None


# =========================
# 🔥 00631L 拆分修正（升級版）
# =========================
def fix_00631L_split(df):
    try:
        if len(df) < 50:
            return df

        recent_price = df["Close"].iloc[-1]
        max_price = df["Close"].max()

        # 判斷是否存在拆分斷層
        if max_price / recent_price > 10:
            print("⚠️ 偵測到 00631L 拆分斷層，進行修正")

            mask = df["Close"] > recent_price * 5

            df.loc[mask, "Close"] = df.loc[mask, "Close"] / 22

        return df

    except Exception as e:
        print("❌ split fix error:", e)
        return df


# =========================
# DATA
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

        # 🔥 套用拆分修正
        if k == "00631L":
            df = fix_00631L_split(df)

        data[k] = df

    return data


# =========================
# INDICATORS
# =========================
def add_indicators(df):
    close = df["Close"]

    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()

    bb = ta.volatility.BollingerBands(close, 20, 2)
    df["BB_UPPER"] = bb.bollinger_hband()
    df["BB_LOWER"] = bb.bollinger_lband()

    df["RSI"] = ta.momentum.RSIIndicator(close, 14).rsi()
    df["DEV"] = (close - df["MA10"]) / df["MA10"]

    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(
        close, df["Volume"]
    ).on_balance_volume()

    return df


# =========================
# SCORE ENGINE
# =========================
def score_engine(rsi, dev, price, ma10, bb_up, bb_low, vix, chip):
    score = 50

    if price > ma10:
        score += 10
    else:
        score -= 10

    if 50 < rsi < 65:
        score += 15
    elif rsi > 75:
        score -= 20

    if dev > 0.05:
        score -= 15
    elif dev < -0.05:
        score += 15

    if price < bb_low:
        score += 10
    elif price > bb_up:
        score -= 15

    if vix > 25:
        score *= 0.7

    if chip:
        score += 10
    else:
        score -= 5

    return max(0, min(100, score))


# =========================
# ANALYZE
# =========================
def analyze(df, vix):
    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    dev = df["DEV"].iloc[-1]
    bb_up = df["BB_UPPER"].iloc[-1]
    bb_low = df["BB_LOWER"].iloc[-1]

    obv_now = df["OBV"].iloc[-1]
    obv_ma = df["OBV"].rolling(5).mean().iloc[-1]
    chip = obv_now > obv_ma

    score = score_engine(rsi, dev, price, ma10, bb_up, bb_low, vix, chip)

    if score >= 80:
        tag = "🚀 主升段"
    elif score >= 65:
        tag = "🟢 強勢"
    elif score >= 50:
        tag = "🟡 可布局"
    elif score >= 30:
        tag = "⚠️ 觀望"
    else:
        tag = "❌ 風險"

    return {
        "price": price,
        "rsi": rsi,
        "bb_up": bb_up,
        "bb_low": bb_low,
        "chip": chip,
        "score": score,
        "tag": tag,
        "pos": int(min(score / 100 * 40, 40)),
        "stop": ma10 * 0.95
    }


# =========================
# FORMAT
# =========================
def format_block(name, desc, res):
    return f"""
📊 {name} — {desc}

🏷️ {res['tag']} ({res['score']:.0f}/100)
💰 {res['price']:.2f}
RSI:{res['rsi']:.1f} | 籌碼:{'強' if res['chip'] else '弱'}
📦 倉位:{res['pos']}%
📉 支撐:{res['bb_low']:.2f}
📈 壓力:{res['bb_up']:.2f}
🛑 風控:{res['stop']:.2f}
"""


# =========================
# MAIN
# =========================
def run():
    data = get_data()

    if not all(k in data for k in ["0050", "00631L"]):
        print("❌ core data missing")
        return

    processed = {k: add_indicators(v) for k, v in data.items()}

    vix_val = processed.get("VIX", {}).get("Close", pd.Series([20])).iloc[-1]

    etf = analyze(processed["00631L"], vix_val)
    stock = analyze(processed["6770"], vix_val)

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"""
📊 V9.3 QUANT REPORT ({now})

{format_block("00631L", "元大台灣50正2", etf)}
{format_block("6770", "力積電", stock)}
"""

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        print(msg)
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=10)
        print("✅ sent" if res.status_code == 200 else res.text)
    except Exception as e:
        print("❌", e)


if __name__ == "__main__":
    run()
