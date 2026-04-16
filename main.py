# === V9.4.1 QUANT FUND ENGINE (STABLE FINAL) ===
import yfinance as yf
import pandas as pd
import ta
import requests
import os
import json
from datetime import datetime, timezone, timedelta

STATE_FILE = "last_signal.json"

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
# SPLIT FIX（00631L）
# =========================
def fix_00631L_split(df):
    if len(df) < 50:
        return df
    recent = df["Close"].iloc[-1]
    if df["Close"].max() / recent > 10:
        print("⚠️ 偵測到 00631L 拆分，已修正")
        mask = df["Close"] > recent * 5
        df.loc[mask, "Close"] = df.loc[mask, "Close"] / 22
    return df

# =========================
# DATA
# =========================
def get_data():
    assets = {
        "0050": "0050.TW",
        "00631L": "00631L.TW",
        "6770": "6770.TW",
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

    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(
        close, df["Volume"]
    ).on_balance_volume()

    return df

# =========================
# 主升段偵測
# =========================
def detect_trend(df):
    ma10 = df["MA10"].iloc[-1]
    ma20 = df["MA20"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    price = df["Close"].iloc[-1]

    obv_now = df["OBV"].iloc[-1]
    obv_prev = df["OBV"].shift(3).iloc[-1]

    return bool(ma10 > ma20 and price > ma10 and rsi > 60 and obv_now > obv_prev)

# =========================
# SCORE
# =========================
def score_engine(rsi, dev, price, ma10, bb_up, bb_low, vix, chip):
    score = 50

    if price > ma10: score += 10
    else: score -= 10

    if 50 < rsi < 65: score += 15
    elif rsi > 75: score -= 20

    if dev > 0.05: score -= 15
    elif dev < -0.05: score += 15

    if price < bb_low: score += 10
    elif price > bb_up: score -= 15

    if vix > 25: score *= 0.7

    if chip: score += 10
    else: score -= 5

    return float(max(0, min(100, score)))

# =========================
# ANALYZE（已修正 JSON 問題）
# =========================
def analyze(df, vix):
    price = float(df["Close"].iloc[-1])
    ma10 = float(df["MA10"].iloc[-1])
    rsi = float(df["RSI"].iloc[-1])
    dev = float(df["DEV"].iloc[-1])
    bb_up = float(df["BB_UPPER"].iloc[-1])
    bb_low = float(df["BB_LOWER"].iloc[-1])

    obv_now = df["OBV"].iloc[-1]
    obv_ma = df["OBV"].rolling(5).mean().iloc[-1]

    chip = bool(obv_now > obv_ma)  # 🔥 修正關鍵

    trend = detect_trend(df)

    score = score_engine(rsi, dev, price, ma10, bb_up, bb_low, vix, chip)

    if trend:
        tag = "🚀 主升段(早期)"
        score = max(score, 75)
    elif score >= 80:
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
        "score": float(score),
        "tag": str(tag),
        "pos": int(min(score / 100 * 40, 40)),
        "stop": float(ma10 * 0.95)
    }

# =========================
# 訊號變化判斷
# =========================
def should_notify(new, old):
    if not old:
        return True

    if new["tag"] != old.get("tag"):
        return True

    if abs(new["score"] - old.get("score", 0)) >= 10:
        return True

    if abs(new["pos"] - old.get("pos", 0)) >= 10:
        return True

    return False

# =========================
# FORMAT（保持你原本格式）
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
        print("❌ data missing")
        return

    processed = {k: add_indicators(v) for k, v in data.items()}

    vix = float(processed.get("VIX", {}).get("Close", pd.Series([20])).iloc[-1])

    etf = analyze(processed["00631L"], vix)
    stock = analyze(processed["6770"], vix)

    # === 讀取舊資料 ===
    old = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                old = json.load(f)
        except:
            old = {}

    notify = (
        should_notify(etf, old.get("00631L")) or
        should_notify(stock, old.get("6770"))
    )

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"""
📊 V9.4 QUANT REPORT ({now})

{format_block("00631L", "元大台灣50正2", etf)}
{format_block("6770", "力積電", stock)}
"""

    # === 儲存新狀態 ===
    with open(STATE_FILE, "w") as f:
        json.dump({
            "00631L": etf,
            "6770": stock
        }, f)

    if not notify:
        print("⏸️ 無變化，不推播")
        return

    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        print(msg)
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=10)
        print("✅ 發送成功" if res.status_code == 200 else res.text)
    except Exception as e:
        print("❌ 發送錯誤:", e)

if __name__ == "__main__":
    run()
