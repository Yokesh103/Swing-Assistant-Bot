# -*- coding: utf-8 -*-
"""
Swing Assistant Pro - NSE + AI + Auto Reports + Qty Tracking + Full Status + Auto Backup
Author: Yokesh | Version: 4.3 (Render Webhook Edition - Full Commands)
"""

import os
import time
import schedule
import threading
import requests
import pandas as pd
import yfinance as yf
import ta
from datetime import datetime, date, time as dt_time
from nsepython import nse_eq
import telebot
from flask import Flask, request
from ai_probability import load_ai_model, predict_prob

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
EXCEL_FILE = os.getenv("EXCEL_FILE", "Swing_Assistant_Data.xlsx")
BACKUP_FOLDER = os.getenv("BACKUP_FOLDER", "backups")
MARKET_OPEN, MARKET_CLOSE = dt_time(9, 15), dt_time(15, 30)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")
tracking_active = True
pd.options.mode.chained_assignment = None

# ---------------- WEB SERVER (REQUIRED BY RENDER) ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Swing Assistant Pro is running (Render Webhook Mode)"

@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ---------------- UTILITIES ----------------
def ensure_excel():
    cols = ["Stock", "Buy", "Target", "SL", "Qty", "Date",
            "Status", "LastPrice", "Prob", "P/L"]
    if not os.path.exists(EXCEL_FILE):
        pd.DataFrame(columns=cols).to_excel(EXCEL_FILE, index=False)
    else:
        df = pd.read_excel(EXCEL_FILE)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df.to_excel(EXCEL_FILE, index=False)

def get_live_price(symbol):
    sym = symbol.upper().replace(".NS", "").strip()
    try:
        data = nse_eq(sym)
        price = data["priceInfo"]["lastPrice"]
        if price:
            return float(price)
    except Exception:
        pass
    try:
        hist = yf.Ticker(f"{sym}.NS").history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

def compute_indicators(symbol):
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="3mo", interval="1d")
        df["rsi"] = ta.momentum.rsi(df["Close"], window=14)
        df["ema20"] = ta.trend.ema_indicator(df["Close"], window=20)
        df["ema50"] = ta.trend.ema_indicator(df["Close"], window=50)
        return df.iloc[-1].to_dict()
    except Exception:
        return {"rsi": None, "ema20": None, "ema50": None}

# ---------------- TELEGRAM COMMANDS ----------------
@bot.message_handler(commands=['start', 'help'])
def start_help_cmd(m):
    msg = (
        "👋 *Welcome to Swing Assistant Pro (NSE)*\n\n"
        "💡 *Commands:*\n"
        "• `/go` — Start live tracking\n"
        "• `/pause` — Pause tracking\n"
        "• `/check` — Bot status\n"
        "• `/track SYMBOL BUY TARGET SL QTY` — Add new stock\n"
        "• `/update SYMBOL TARGET SL [QTY]` — Update values\n"
        "• `/remove SYMBOL` — Remove stock\n"
        "• `/info SYMBOL` — Show one stock\n"
        "• `/list` — Show all holdings\n"
        "• `/today` — Daily P/L summary\n"
        "• `/statusfull` or `/sf` — Full bot health\n"
        "• `/ping` — Check bot status\n\n"
        "☀ Morning summary at 9:00 AM\n"
        "🌇 Evening report at 3:31 PM\n"
        "🗓 Weekly summary Saturday 4:00 PM\n"
        "💾 Nightly backup at 11:30 PM"
    )
    bot.reply_to(m, msg)

@bot.message_handler(commands=['ping'])
def ping_cmd(m):
    bot.reply_to(m, f"✅ Bot is alive! Server time: {datetime.now().strftime('%H:%M:%S')}")

@bot.message_handler(commands=['go'])
def go_cmd(m):
    global tracking_active
    tracking_active = True
    bot.reply_to(m, "🚀 Tracking activated (every 1 minute).")

@bot.message_handler(commands=['pause'])
def pause_cmd(m):
    global tracking_active
    tracking_active = False
    bot.reply_to(m, "⏸️ Tracking paused.")

@bot.message_handler(commands=['check'])
def check_cmd(m):
    state = "✅ Active" if tracking_active else "⏸️ Paused"
    bot.reply_to(m, f"📊 Bot status: {state}")

@bot.message_handler(commands=['track'])
def track_cmd(m):
    try:
        parts = m.text.split()
        if len(parts) < 6:
            bot.reply_to(m, "⚠️ Usage: /track SYMBOL BUY TARGET SL QTY")
            return
        _, s, b, t, sl, qty = parts[:6]
        df = pd.read_excel(EXCEL_FILE)
        df.loc[len(df)] = [s.upper(), float(b), float(t), float(sl),
                           float(qty), date.today(), "🕒 Active", None, None, 0]
        df.to_excel(EXCEL_FILE, index=False)
        bot.reply_to(m, f"✅ Added {s.upper()} | Buy ₹{b} | Target ₹{t} | SL ₹{sl} | Qty {qty}")
    except Exception as e:
        bot.reply_to(m, f"❌ Error adding stock: {e}")

@bot.message_handler(commands=['update'])
def update_cmd(m):
    try:
        parts = m.text.split()
        if len(parts) < 4:
            bot.reply_to(m, "⚠️ Usage: /update SYMBOL TARGET SL [QTY]")
            return
        _, s, t, sl, *q = parts
        df = pd.read_excel(EXCEL_FILE)
        if s.upper() not in df["Stock"].values:
            bot.reply_to(m, f"⚠️ {s.upper()} not found.")
            return
        df.loc[df["Stock"] == s.upper(), ["Target", "SL"]] = [float(t), float(sl)]
        if q:
            df.loc[df["Stock"] == s.upper(), "Qty"] = float(q[0])
        df.to_excel(EXCEL_FILE, index=False)
        bot.reply_to(m, f"✅ Updated {s.upper()} | Target ₹{t} | SL ₹{sl} | Qty {q[0] if q else '(unchanged)'}")
    except Exception as e:
        bot.reply_to(m, f"❌ Error updating stock: {e}")

@bot.message_handler(commands=['remove'])
def remove_cmd(m):
    try:
        _, s = m.text.split()
        df = pd.read_excel(EXCEL_FILE)
        df = df[df["Stock"] != s.upper()]
        df.to_excel(EXCEL_FILE, index=False)
        bot.reply_to(m, f"🗑️ Removed {s.upper()}")
    except Exception as e:
        bot.reply_to(m, f"Error removing: {e}")

@bot.message_handler(commands=['info'])
def info_cmd(m):
    try:
        _, s = m.text.split()
        df = pd.read_excel(EXCEL_FILE)
        row = df[df["Stock"] == s.upper()]
        if row.empty:
            bot.reply_to(m, f"⚠️ {s.upper()} not found.")
            return
        r = row.iloc[0]
        msg = (
            f"📊 *{r['Stock']}*\n"
            f"Buy: ₹{r['Buy']} | Target: ₹{r['Target']} | SL: ₹{r['SL']}\n"
            f"Qty: {r['Qty']} | Last: ₹{r['LastPrice']} | P/L: ₹{r['P/L']}\n"
            f"Status: {r['Status']}"
        )
        bot.reply_to(m, msg)
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

@bot.message_handler(commands=['list'])
def list_cmd(m):
    df = pd.read_excel(EXCEL_FILE)
    msg = "📈 *Active Holdings:*\n"
    for _, r in df.iterrows():
        if r["Stock"] == "TOTAL": continue
        msg += f"{r['Stock']} | Buy ₹{r['Buy']} | Target ₹{r['Target']} | SL ₹{r['SL']} | Qty {r['Qty']}\n"
    bot.reply_to(m, msg)

@bot.message_handler(commands=['today'])
def today_cmd(m):
    df = pd.read_excel(EXCEL_FILE)
    msg = f"🌅 *Daily Summary — {date.today()}*\n"
    total_pl = 0
    for _, r in df.iterrows():
        if r["Stock"] == "TOTAL": continue
        pl = round((r["LastPrice"] - r["Buy"]) * r["Qty"], 2) if pd.notna(r["LastPrice"]) else 0
        msg += f"{r['Stock']}: ₹{pl} ({r['Status']}) | Qty: {r['Qty']}\n"
        total_pl += pl
    msg += f"\n💰 *Total Portfolio P/L:* ₹{round(total_pl,2)}"
    bot.reply_to(m, msg)

@bot.message_handler(commands=['statusfull', 'sf'])
def statusfull_cmd(m):
    try:
        df = pd.read_excel(EXCEL_FILE)
        if df.empty:
            bot.reply_to(m, "⚠️ No tracked stocks found.")
            return
        now = datetime.now().strftime("%d-%b %H:%M:%S")
        msg = f"📊 *Swing Assistant Health Check — {now}*\n\n"
        total_pl = df["P/L"].sum() if "P/L" in df else 0
        msg += f"💰 *Total Portfolio P/L:* ₹{round(total_pl,2)}"
        bot.reply_to(m, msg)
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")

# ---------------- TRACKER ----------------
def check_prices():
    global tracking_active
    if not tracking_active:
        return
    now = datetime.now()
    if not (MARKET_OPEN <= now.time() <= MARKET_CLOSE):
        return
    print(f"[INFO] Checking stock prices at {now.strftime('%H:%M:%S')}...")
    try:
        df = pd.read_excel(EXCEL_FILE)
        ai_model = load_ai_model()
        for i, r in df.iterrows():
            if r["Stock"] == "TOTAL":
                continue
            symbol = str(r["Stock"]).upper().strip()
            price = get_live_price(symbol)
            if not price:
                continue
            df.at[i, "LastPrice"] = price
            df.at[i, "P/L"] = round((price - r["Buy"]) * r["Qty"], 2)
            ind = compute_indicators(symbol)
            feat = {"dist_target": (r["Target"] - price) / r["Buy"],
                    "dist_sl": (price - r["SL"]) / r["Buy"],
                    "rsi": ind["rsi"],
                    "ema_ratio": (ind["ema20"] / ind["ema50"]) if ind["ema50"] else 1}
            prob = predict_prob(ai_model, feat) or 0
            df.at[i, "Prob"] = prob
        df.to_excel(EXCEL_FILE, index=False)
    except Exception as e:
        print(f"[ERROR] {e}")

def scheduler_thread():
    schedule.every(1).minutes.do(check_prices)
    while True:
        schedule.run_pending()
        time.sleep(10)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    ensure_excel()
    threading.Thread(target=scheduler_thread, daemon=True).start()

    # --- Webhook mode for Render ---
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://swing-assistant-bot.onrender.com")
    WEBHOOK_URL = f"{RENDER_URL}/webhook"

    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"[INFO] Webhook set: {WEBHOOK_URL}")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
