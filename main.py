# === V10.5 QUANT ENGINE (MACRO FILTER ADDED) ===
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
        "SOX": "^SOX",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
        "OIL": "CL=F"
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
# 🌍 市場濾網
# =========================
def get_market_state(nasdaq_df, sox_df):
    def trend(df):
        close = df["Close"]
        ma20 = close.rolling(20).mean()
        return close.iloc[-1] > ma20.iloc[-1]

    try:
        n = trend(nasdaq_df)
        s = trend(sox_df)

        if n and s:
            return "STRONG_BULL"
        elif not n and not s:
            return "BEAR"
        else:
            return "MIXED"
    except:
        return "UNKNOWN"


def market_label(s):
    return {
        "STRONG_BULL": "多頭共振",
        "MIXED": "分歧震盪",
        "BEAR": "空頭風險"
    }.get(s, "")


# =========================
# 🌐 宏觀濾網（新增）
# =========================
def get_macro_state(dxy_df, oil_df):
    try:
        def up(df):
            close = df["Close"]
            ma20 = close.rolling(20).mean()
            return close.iloc[-1] > ma20.iloc[-1]

        dxy_up = up(dxy_df)
        oil_up = up(oil_df)

        if not dxy_up and not oil_up:
            return "RISK_ON"
        elif dxy_up and oil_up:
            return "RISK_OFF"
        else:
            return "NEUTRAL"
    except:
        return "UNKNOWN"


def macro_label(s):
    return {
        "RISK_ON": "資金寬鬆",
        "RISK_OFF": "資金收縮",
        "NEUTRAL": "中性"
    }.get(s, "")


# =========================
# SCORE ENGINE（加入宏觀）
# =========================
def score_engine(rsi, dev, price, ma10, bb_up, bb_low,
                 vix, chip, market_state, macro_state):

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

    # 動態布林
    if price < bb_low:
        score += 10
    elif price > bb_up:
        if market_state == "STRONG_BULL":
            score += 5
        elif market_state == "BEAR":
            score -= 20
        else:
            score -= 10

    if vix > 25:
        score *= 0.7

    # 市場濾網
    if market_state == "BEAR":
        score -= 15
    elif market_state == "MIXED":
        score -= 5

    # 🌐 宏觀濾網（新增）
    if macro_state == "RISK_OFF":
        score -= 10
    elif macro_state == "RISK_ON":
        score += 5

    score += 10 if chip else -5

    return max(0, min(100, score))


# =========================
# 主升段（不被宏觀干擾）
# =========================
def is_bull_run(df, score, vix, market_state, is_stock=False):
    try:
        ma10_now = df["MA10"].iloc[-1]
        ma10_prev = df["MA10"].iloc[-2]

        obv_now = df["OBV"].iloc[-1]
        obv_prev = df["OBV"].iloc[-2]

        th = 85 if is_stock else 80

        return (
            score >= th and
            df["Close"].iloc[-1] > ma10_now and
            ma10_now > ma10_prev and
            obv_now > obv_prev and
            vix < 22 and
            market_state != "BEAR"
        )
    except:
        return False


# =========================
# ANALYZE
# =========================
def analyze(df, vix, market_state, macro_state):
    if df is None or len(df) < 30:
        return None

    price = df["Close"].iloc[-1]
    ma10 = df["MA10"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    dev = df["DEV"].iloc[-1]

    bb_up = df["BB_UPPER"].iloc[-1]
    bb_low = df["BB_LOWER"].iloc[-1]

    obv_now = df["OBV"].iloc[-1]
    obv_ma = df["OBV"].rolling(5).mean().iloc[-1]
    chip = obv_now > obv_ma

    score = score_engine(
        rsi, dev, price, ma10,
        bb_up, bb_low,
        vix, chip,
        market_state,
        macro_state
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
        "chip": chip,
        "bb_up": bb_up,
        "bb_low": bb_low
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
📉 下軌:{res['bb_low']:.2f} | 📈 上軌:{res['bb_up']:.2f}
🛑 停損:{res['stop']:.2f}
"""


# =========================
# MAIN
# =========================
def run():
    data = get_data()
    processed = {k: add_indicators(v) for k, v in data.items() if v is not None}

    market_state = get_market_state(processed.get("NASDAQ"), processed.get("SOX"))
    macro_state = get_macro_state(processed.get("DXY"), processed.get("OIL"))
    vix = processed.get("VIX", {}).get("Close", pd.Series([20])).iloc[-1]

    assets = ["0050", "00631L", "00662", "00646", "00735", "6770"]
    results = {
        k: analyze(processed.get(k), vix, market_state, macro_state)
        for k in assets
    }

    bull_flags = {}
    for k in assets:
        bull_flags[k] = (
            k in processed and
            results[k] is not None and
            is_bull_run(
                processed[k],
                results[k]["score"],
                vix,
                market_state,
                is_stock=(k == "6770")
            )
        )

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    msg = f"📊 V10.5 QUANT REPORT ({now})\n"
    msg += f"\n🌍 市場：{market_state}（{market_label(market_state)}）"
    msg += f"\n🌐 宏觀：{macro_state}（{macro_label(macro_state)}） | VIX:{vix:.1f}\n"

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
