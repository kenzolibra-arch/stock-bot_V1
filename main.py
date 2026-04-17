# === V10.2 QUANT ENGINE (GLOBAL FILTER VERSION) ===
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
        df = yf.download(ticker, period="1y", interval="1d", progress=False, threads=False)
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except:
        return None


# =========================
# SPLIT FIX
# =========================
def fix_00631L_split(df):
    try:
        if len(df) < 50:
            return df

        if df["Close"].max() / df["Close"].iloc[-1] > 10:
            mask = df["Close"] > df["Close"].iloc[-1] * 5
            df.loc[mask, "Close"] /= 22

        return df
    except:
        return df


# =========================
# DATA
# =========================
def get_data():
    assets = {
        "0050": "0050.TW",
        "00631L": "00631L.TW",
        "00662": "00662.TW",
        "00646": "00646.TW",
        "00735": "00735.TW",
        "6770": "6770.TW",
        "NASDAQ": "^IXIC",
        "VIX": "^VIX"
    }

    data = {}
    for k, v in assets.items():
        df = safe_download(v)
        if df is None:
            continue

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

    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(close, df["Volume"]).on_balance_volume()

    return df.dropna()


# =========================
# 🌍 NASDAQ TREND FILTER
# =========================
def get_market_trend(nasdaq_df):
    try:
        close = nasdaq_df["Close"]
        ma20 = close.rolling(20).mean()

        if close.iloc[-1] > ma20.iloc[-1]:
            return "BULL"
        else:
            return "BEAR"
    except:
        return "UNKNOWN"


# =========================
# SCORE ENGINE（加入全球濾網）
# =========================
def score_engine(rsi, dev, price, ma10, bb_up, bb_low, vix, chip, market_trend):
    score = 50

    score += 10 if price > ma10 else -10

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

    # 🔴 VIX風控
    if vix > 25:
        score *= 0.7

    # 🔴 NASDAQ 空頭壓制（關鍵）
    if market_trend == "BEAR":
        score -= 10

    score += 10 if chip else -5

    return max(0, min(100, score))


# =========================
# 🚀 主升段（全球版）
# =========================
def is_bull_run(df, score, vix, market_trend, is_stock=False):
    try:
        ma10_now = df["MA10"].iloc[-1]
        ma10_prev = df["MA10"].iloc[-2]

        obv_now = df["OBV"].iloc[-1]
        obv_prev = df["OBV"].iloc[-2]

        score_th = 85 if is_stock else 80

        return (
            score >= score_th and
            df["Close"].iloc[-1] > ma10_now and
            ma10_now > ma10_prev and
            obv_now > obv_prev and
            vix < 22 and
            market_trend == "BULL"   # 🔥 全球同步
        )
    except:
        return False


# =========================
# ANALYZE
# =========================
def analyze(df, vix, market_trend):
    if df is None or len(df) < 30:
        return None

    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    dev = df["DEV"].iloc[-1]

    obv_now = df["OBV"].iloc[-1]
    obv_ma = df["OBV"].rolling(5).mean().iloc[-1]
    chip = obv_now > obv_ma

    score = score_engine(
        rsi, dev, price, ma10,
        df["BB_UPPER"].iloc[-1],
        df["BB_LOWER"].iloc[-1],
        vix, chip, market_trend
    )

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
        "pos": int(min(score / 100 * 40, 40)),
        "stop": ma10 * 0.95,
        "rsi": rsi,
        "chip": chip
    }


# =========================
# FORMAT
# =========================
def format_block(name, res, bull=False):
    if res is None:
        return f"\n📊 {name}\n❌ 無資料\n"

    flag = "🚀 主升段狙擊\n" if bull else ""

    return f"""
📊 {name}
{flag}
🏷️ {res['tag']} ({res['score']:.0f})
💰 {res['price']:.2f}
RSI:{res['rsi']:.1f} | 籌碼:{'強' if res['chip'] else '弱'}
📦 倉位:{res['pos']}%
🛑 停損:{res['stop']:.2f}
"""


# =========================
# MAIN
# =========================
def run():
    data = get_data()
    processed = {k: add_indicators(v) for k, v in data.items() if v is not None}

    # 🌍 市場狀態
    market_trend = get_market_trend(processed.get("NASDAQ"))
    vix = processed.get("VIX", {}).get("Close", pd.Series([20])).iloc[-1]

    assets = ["0050", "00631L", "00662", "00646", "00735", "6770"]
    results = {k: analyze(processed.get(k), vix, market_trend) for k in assets}

    bull_flags = {}
    for k in assets:
        bull_flags[k] = (
            k in processed and
            results[k] is not None and
            is_bull_run(
                processed[k],
                results[k]["score"],
                vix,
                market_trend,
                is_stock=(k == "6770")
            )
        )

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"📊 V10.2 QUANT REPORT ({now})\n"
    msg += f"\n🌍 市場狀態：{market_trend} | VIX:{vix:.1f}\n"

    hot = [k for k, v in bull_flags.items() if v]
    if hot:
        msg += "\n🚀【主升段清單】\n" + " / ".join(hot) + "\n"

    for k in assets:
        msg += format_block(k, results[k], bull_flags[k])

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        print(msg)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=10)

    print("✅ sent" if res.status_code == 200 else res.text)


if __name__ == "__main__":
    run()
