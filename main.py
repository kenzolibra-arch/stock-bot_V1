import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

# === Telegram 設定 ===
TOKEN = "你的BOT_TOKEN"
CHAT_ID = "你的CHAT_ID"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        res = requests.post(url, data=payload)
        print("Telegram status:", res.text)
    except Exception as e:
        print("Telegram error:", e)

# === 抓資料 ===
def get_data():
    df = yf.download("0050.TW", period="3mo", interval="1d")
    df.dropna(inplace=True)
    return df

# === 計算指標 ===
def calculate_signals(df):
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "觀望"

    if latest["MA20"] > latest["MA60"] and prev["MA20"] <= prev["MA60"]:
        signal = "📈 黃金交叉（偏多）"
    elif latest["MA20"] < latest["MA60"] and prev["MA20"] >= prev["MA60"]:
        signal = "📉 死亡交叉（偏空）"

    return signal, latest

# === 主程式 ===
def run():
    print("🚀 Bot started")

    df = get_data()
    signal, latest = calculate_signals(df)

    price = latest["Close"]
    ma20 = latest["MA20"]
    ma60 = latest["MA60"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    message = f"""
📊 0050 每日監控

🕒 時間：{now}
💰 收盤價：{price:.2f}
📈 MA20：{ma20:.2f}
📉 MA60：{ma60:.2f}

📍 訊號：{signal}

✅ 系統正常運作中
"""

    send_telegram(message)

if __name__ == "__main__":
    run()
