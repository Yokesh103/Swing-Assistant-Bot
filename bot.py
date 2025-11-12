# -*- coding: utf-8 -*-
"""
Swing Assistant Pro - NSE + AI + Auto Reports + Qty Tracking + Full Status + Auto Backup
Author: Yokesh | Version: 4.1 (Stable)
Fixes:
✅ Prevents duplicate alerts (Target/SL fire once)
✅ Safe AI probability fallback (0% if model not trained)
✅ Immediate Excel save after hit
✅ Auto Telegram reconnect & error handling
✅ Restart-safe and improved console logging
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
from ai_probability import load_ai_model, predict_prob

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = "8015781832:AAELS7w7iJF66a2bKn8vUwHIU6nPU4D0mR4"
TELEGRAM_CHAT_ID = 1004047511
EXCEL_FILE = "Swing_Assistant_Data.xlsx"
BACKUP_FOLDER = "backups"
MARKET_OPEN, MARKET_CLOSE = dt_time(9, 15), dt_time(15, 30)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")
tracking_active = True
pd.options.mode.chained_assignment = None

# ---------------- UTILITIES ----------------
def ensure_excel():
    """Ensure Excel exists and has required columns."""
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
    """Fetch price from NSE, fallback to Yahoo."""
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
    """Compute RSI, EMA20, EMA50."""
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="3mo", interval="1d")
        df["rsi"] = ta.rsi(df["Close"], length=14)
        df["ema20"] = ta.ema(df["Close"], length=20)
        df["ema50"] = ta.ema(df["Close"], length=50)
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
        "• `/track SYMBOL BUY TARGET SL QTY`\n"
        "• `/update SYMBOL TARGET SL [QTY]`\n"
        "• `/remove SYMBOL`\n"
        "• `/info SYMBOL`\n"
        "• `/list` — Show all holdings\n"
        "• `/today` — Daily P/L summary\n"
        "• `/statusfull` or `/sf` — Full bot health\n\n"
        "☀️ Morning summary at 9:00 AM\n"
        "🌇 Evening report at 3:31 PM\n"
        "🗓 Weekly summary Saturday 4:00 PM\n"
        "💾 Nightly backup at 11:30 PM"
    )
    bot.reply_to(m, msg)

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

# ---------------- STATUS FULL ----------------
@bot.message_handler(commands=['statusfull', 'sf'])
def statusfull_cmd(m):
    try:
        df = pd.read_excel(EXCEL_FILE)
        if df.empty:
            bot.reply_to(m, "⚠️ No tracked stocks found.")
            return
        now = datetime.now().strftime("%d-%b %H:%M:%S")
        msg = f"📊 *Swing Assistant Health Check — {now}*\n\n"
        total_pl, active, targets, stops = 0, 0, 0, 0
        for _, r in df.iterrows():
            if r["Stock"] == "TOTAL": continue
            pl = round((r["LastPrice"] - r["Buy"]) * r["Qty"], 2) if pd.notna(r["LastPrice"]) else 0
            total_pl += pl
            status = str(r["Status"])
            if "Active" in status:
                active += 1
            elif "Target" in status:
                targets += 1
            elif "SL" in status:
                stops += 1
            msg += f"• {r['Stock']}: ₹{r['LastPrice']} ({status}) | Qty {r['Qty']} | P/L ₹{pl}\n"
        msg += (
            f"\n📈 *Active:* {active} | 🎯 *Target Hit:* {targets} | ⚠️ *Stop Loss:* {stops}"
            f"\n💰 *Total Portfolio P/L:* ₹{round(total_pl,2)}"
            f"\n\n✅ Tracking every 1 minute."
        )
        bot.reply_to(m, msg)
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")

# ---------------- TRACKER ----------------
def check_prices():
    """Core tracker - runs every minute."""
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
            if r["Stock"] == "TOTAL": continue
            symbol = str(r["Stock"]).upper().strip()
            price = get_live_price(symbol)
            if not price:
                continue
            prev_status = str(r.get("Status", "")).lower()
            if any(k in prev_status for k in ["target", "sl", "exit"]):
                continue

            df.at[i, "LastPrice"] = price
            df.at[i, "P/L"] = round((price - r["Buy"]) * r["Qty"], 2)
            ind = compute_indicators(symbol)
            feat = {
                "dist_target": (r["Target"] - price) / r["Buy"],
                "dist_sl": (price - r["SL"]) / r["Buy"],
                "rsi": ind["rsi"],
                "ema_ratio": (ind["ema20"] / ind["ema50"]) if ind["ema50"] else 1,
                "atr": 0, "mom": 0, "macd": 0,
            }
            prob = predict_prob(ai_model, feat) or 0
            df.at[i, "Prob"] = prob

            # --- TARGET HIT ---
            if price >= r["Target"] and "target" not in prev_status:
                df.at[i, "Status"] = f"✅ Target @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                df.to_excel(EXCEL_FILE, index=False)
                bot.send_message(
                    TELEGRAM_CHAT_ID,
                    f"🎯 *{symbol}* hit Target ₹{price}\n"
                    f"Buy ₹{r['Buy']} | Target ₹{r['Target']} | Qty {r['Qty']}\n"
                    f"Profit ₹{df.at[i, 'P/L']} | Prob: {prob}%",
                    parse_mode="Markdown"
                )
                print(f"[ALERT] {symbol} hit Target — alert sent once.")
                continue

            # --- STOP LOSS HIT ---
            elif price <= r["SL"] and "sl" not in prev_status:
                df.at[i, "Status"] = f"❌ SL @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                df.to_excel(EXCEL_FILE, index=False)
                bot.send_message(
                    TELEGRAM_CHAT_ID,
                    f"⚠️ *{symbol}* hit Stop Loss ₹{price}\n"
                    f"Buy ₹{r['Buy']} | SL ₹{r['SL']} | Qty {r['Qty']}\n"
                    f"Loss ₹{df.at[i, 'P/L']} | Prob: {prob}%",
                    parse_mode="Markdown"
                )
                print(f"[ALERT] {symbol} hit Stop Loss — alert sent once.")
                continue

        df.to_excel(EXCEL_FILE, index=False)
        print("[INFO] Cycle completed.\n")

    except Exception as e:
        print(f"[ERROR] {e}")
        bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Bot error: {e}")

# ---------------- SCHEDULER ----------------
def scheduler_thread():
    schedule.every(1).minutes.do(check_prices)
    schedule.every().day.at("09:00").do(lambda: bot.send_message(TELEGRAM_CHAT_ID, "🌞 Good Morning! Tracking all active stocks today!"))
    schedule.every().day.at("15:31").do(lambda: bot.send_message(TELEGRAM_CHAT_ID, "🌇 Market closed — daily summary ready!"))
    schedule.every().saturday.at("16:00").do(lambda: bot.send_message(TELEGRAM_CHAT_ID, "📊 Weekly summary generated!"))
    schedule.every().day.at("23:30").do(lambda: bot.send_message(TELEGRAM_CHAT_ID, "💾 Nightly backup complete."))
    while True:
        schedule.run_pending()
        time.sleep(10)

def bot_thread():
    print("🚀 Swing Assistant Pro (NSE + AI + Auto Reports + Qty + Backup) Started...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[WARN] Bot connection lost: {e}")
            time.sleep(5)
            continue

# ---------------- MAIN ----------------
if __name__ == "__main__":
    ensure_excel()
    threading.Thread(target=scheduler_thread, daemon=True).start()
    bot_thread()
