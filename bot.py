# -*- coding: utf-8 -*-
"""
Swing Assistant Pro – NSE + AI + Auto Reports + Qty Tracking + Email Reports
Author: Yokesh  |  Version: 4.5 (Render Webhook + Email)
"""

import os, time, threading, schedule, smtplib
from datetime import datetime, date, time as dt_time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import pandas as pd, yfinance as yf, ta
from nsepython import nse_eq
from flask import Flask, request
import telebot
from ai_probability import load_ai_model, predict_prob

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO   = os.getenv("EMAIL_TO")
EXCEL_FILE = os.getenv("EXCEL_FILE", "Swing_Assistant_Data.xlsx")
BACKUP_FOLDER = os.getenv("BACKUP_FOLDER", "backups")
MARKET_OPEN, MARKET_CLOSE = dt_time(9, 15), dt_time(15, 30)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown")
tracking_active = True
pd.options.mode.chained_assignment = None

# ---------------- WEB SERVER ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Swing Assistant Pro is running (Render Webhook + Email Mode)"

@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ---------------- EMAIL UTILITY ----------------
def send_email(subject, body, attachment_path=None):
    """Send email with optional Excel attachment."""
    try:
        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = EMAIL_USER, EMAIL_TO, subject
        msg.attach(MIMEText(body, "plain"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            msg.attach(part)

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg)
        print(f"[INFO] Email sent to {EMAIL_TO}: {subject}")
    except Exception as e:
        print(f"[ERROR] Email failed: {e}")

# ---------------- UTILITIES ----------------
def ensure_excel():
    cols = ["Stock","Buy","Target","SL","Qty","Date",
            "Status","LastPrice","Prob","P/L"]
    if not os.path.exists(EXCEL_FILE):
        pd.DataFrame(columns=cols).to_excel(EXCEL_FILE, index=False)
    else:
        df = pd.read_excel(EXCEL_FILE)
        for c in cols:
            if c not in df.columns: df[c] = None
        df.to_excel(EXCEL_FILE, index=False)

def get_live_price(symbol):
    sym = symbol.upper().replace(".NS","").strip()
    try:
        p = nse_eq(sym)["priceInfo"]["lastPrice"];  return float(p)
    except: pass
    try:
        hist = yf.Ticker(f"{sym}.NS").history(period="1d", interval="1m")
        if not hist.empty: return float(hist["Close"].iloc[-1])
    except: pass
    return None

def compute_indicators(symbol):
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="3mo", interval="1d")
        df["rsi"] = ta.momentum.rsi(df["Close"],14)
        df["ema20"]=ta.trend.ema_indicator(df["Close"],20)
        df["ema50"]=ta.trend.ema_indicator(df["Close"],50)
        return df.iloc[-1].to_dict()
    except: return {"rsi":None,"ema20":None,"ema50":None}

# ---------------- EMAIL + SUMMARY FUNCTIONS ----------------
def log_daily_report():
    """Append daily P/L to Excel in new sheet 'Daily_Report'."""
    try:
        df_all = pd.read_excel(EXCEL_FILE, sheet_name=None)
        main = df_all.get('Sheet1') or list(df_all.values())[0]
        total_pl = main["P/L"].sum() if "P/L" in main else 0
        row = pd.DataFrame({"Date":[date.today().strftime("%Y-%m-%d")],
                            "Total_P&L":[round(total_pl,2)]})
        report = pd.concat([df_all.get('Daily_Report', pd.DataFrame()), row],
                           ignore_index=True)
        with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="w") as w:
            main.to_excel(w, index=False, sheet_name="Sheet1")
            report.to_excel(w, index=False, sheet_name="Daily_Report")
        print(f"[INFO] Daily report logged: ₹{round(total_pl,2)}")
    except Exception as e: print(f"[ERROR] Daily log failed: {e}")

def morning_summary():
    msg = "☀️ Good Morning! Tracking all active stocks today. Let's make profits 🚀"
    bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
    send_email("🌅 Swing Assistant – Morning Report", msg)

def evening_summary():
    try:
        df = pd.read_excel(EXCEL_FILE)
        total_pl = df["P/L"].sum() if "P/L" in df else 0
        msg = f"🌇 End of Day Summary — {date.today()}\n💰 Total P/L: ₹{round(total_pl,2)}"
        bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
        send_email("🌇 Swing Assistant – Evening Report", msg, EXCEL_FILE)
        log_daily_report()
    except Exception as e:
        bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Evening summary failed: {e}")

def weekly_summary():
    try:
        df = pd.read_excel(EXCEL_FILE)
        total = pd.to_numeric(df["P/L"], errors="coerce").fillna(0).sum()
        msg = (f"📊 Weekly Summary\n"
               f"Date: {date.today().strftime('%d %b %Y')}\n"
               f"Total Weekly P/L: ₹{round(total,2)}")
        bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
        send_email("📊 Swing Assistant – Weekly Summary", msg)
    except Exception as e:
        bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Weekly summary failed: {e}")

def nightly_backup():
    try:
        os.makedirs(BACKUP_FOLDER, exist_ok=True)
        ts = date.today().strftime("%Y-%m-%d")
        path = os.path.join(BACKUP_FOLDER, f"Backup_{ts}.xlsx")
        df = pd.read_excel(EXCEL_FILE); df.to_excel(path, index=False)
        bot.send_message(TELEGRAM_CHAT_ID, f"💾 Backup created: `{path}`",
                         parse_mode="Markdown")
        send_email("💾 Swing Assistant – Nightly Backup", "Backup attached.", path)
    except Exception as e:
        bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Backup failed: {e}")

# ---------------- TELEGRAM COMMANDS ----------------
@bot.message_handler(commands=['start','help'])
def help_cmd(m):
    msg = ("👋 *Swing Assistant Pro*\n\n"
           "💡 *Commands:*\n"
           "`/go` start tracking\n"
           "`/pause` pause tracking\n"
           "`/check` bot status\n"
           "`/track SYMBOL BUY TARGET SL QTY`\n"
           "`/update SYMBOL TARGET SL [QTY]`\n"
           "`/remove SYMBOL`\n"
           "`/info SYMBOL`\n"
           "`/list` holdings\n"
           "`/today` daily P/L\n"
           "`/statusfull` or `/sf`\n"
           "`/ping` test bot\n\n"
           "☀ 09:00 Morning Summary\n🌇 15:31 Evening Report\n"
           "🗓 Sat 16:00 Weekly\n💾 23:30 Backup + Email")
    bot.reply_to(m,msg)

@bot.message_handler(commands=['ping'])
def ping(m): bot.reply_to(m,f"✅ Bot alive — {datetime.now():%H:%M:%S}")

@bot.message_handler(commands=['go'])
def go(m): 
    global tracking_active; tracking_active=True
    bot.reply_to(m,"🚀 Tracking activated.")

@bot.message_handler(commands=['pause'])
def pause(m): 
    global tracking_active; tracking_active=False
    bot.reply_to(m,"⏸️ Tracking paused.")

@bot.message_handler(commands=['check'])
def check(m):
    s="✅ Active" if tracking_active else "⏸️ Paused"
    bot.reply_to(m,f"📊 Bot: {s}")

@bot.message_handler(commands=['track'])
def track(m):
    try:
        _,s,b,t,sl,qty = m.text.split()[:6]
        df=pd.read_excel(EXCEL_FILE)
        df.loc[len(df)] = [s.upper(),float(b),float(t),float(sl),
                           float(qty),date.today(),"🕒 Active",None,None,0]
        df.to_excel(EXCEL_FILE,index=False)
        bot.reply_to(m,f"✅ Added {s.upper()} @₹{b} Target₹{t} SL₹{sl}")
    except Exception as e: bot.reply_to(m,f"❌ {e}")

@bot.message_handler(commands=['update'])
def update(m):
    try:
        _,s,t,sl,*q=m.text.split()
        df=pd.read_excel(EXCEL_FILE)
        if s.upper() not in df["Stock"].values: return bot.reply_to(m,f"{s} not found.")
        df.loc[df["Stock"]==s.upper(),["Target","SL"]] = [float(t),float(sl)]
        if q: df.loc[df["Stock"]==s.upper(),"Qty"]=float(q[0])
        df.to_excel(EXCEL_FILE,index=False); bot.reply_to(m,"✅ Updated.")
    except Exception as e: bot.reply_to(m,f"❌ {e}")

@bot.message_handler(commands=['remove'])
def remove(m):
    try:
        _,s=m.text.split(); df=pd.read_excel(EXCEL_FILE)
        df=df[df["Stock"]!=s.upper()]; df.to_excel(EXCEL_FILE,index=False)
        bot.reply_to(m,f"🗑️ Removed {s.upper()}")
    except Exception as e: bot.reply_to(m,f"❌ {e}")

@bot.message_handler(commands=['info'])
def info(m):
    try:
        _,s=m.text.split(); df=pd.read_excel(EXCEL_FILE)
        r=df[df["Stock"]==s.upper()]
        if r.empty: return bot.reply_to(m,"⚠️ Not found.")
        x=r.iloc[0]; msg=(f"📊 *{x['Stock']}*\nBuy₹{x['Buy']} Target₹{x['Target']} "
                         f"SL₹{x['SL']} Qty{x['Qty']}\nLast₹{x['LastPrice']} P/L₹{x['P/L']}")
        bot.reply_to(m,msg)
    except Exception as e: bot.reply_to(m,f"❌ {e}")

@bot.message_handler(commands=['list'])
def lst(m):
    df=pd.read_excel(EXCEL_FILE)
    msg="📈 *Holdings:*\n"+"\n".join(
        [f"{r['Stock']} Buy₹{r['Buy']} Target₹{r['Target']} SL₹{r['SL']} Qty{r['Qty']}"
         for _,r in df.iterrows() if r["Stock"]!="TOTAL"])
    bot.reply_to(m,msg)

@bot.message_handler(commands=['today'])
def today(m):
    df=pd.read_excel(EXCEL_FILE)
    msg=f"🌅 *Daily Summary — {date.today()}*\n"
    tot=0
    for _,r in df.iterrows():
        if r["Stock"]=="TOTAL":continue
        pl=round((r["LastPrice"]-r["Buy"])*r["Qty"],2) if pd.notna(r["LastPrice"]) else 0
        msg+=f"{r['Stock']}: ₹{pl}\n"; tot+=pl
    msg+=f"\n💰 Total P/L ₹{round(tot,2)}"; bot.reply_to(m,msg)

@bot.message_handler(commands=['statusfull','sf'])
def sf(m):
    try:
        df=pd.read_excel(EXCEL_FILE)
        tot=df["P/L"].sum() if "P/L" in df else 0
        msg=(f"📊 *Health Check — {datetime.now():%H:%M:%S}*\n"
             f"💰 Total P/L ₹{round(tot,2)}")
        bot.reply_to(m,msg)
    except Exception as e: bot.reply_to(m,f"❌ {e}")

# ---------------- TRACKER ----------------
def check_prices():
    global tracking_active
    if not tracking_active: return
    now=datetime.now()
    if not (MARKET_OPEN<=now.time()<=MARKET_CLOSE): return
    print(f"[INFO] Checking at {now:%H:%M:%S}")
    try:
        df=pd.read_excel(EXCEL_FILE); model=load_ai_model()
        for i,r in df.iterrows():
            if r["Stock"]=="TOTAL": continue
            price=get_live_price(r["Stock"]); 
            if not price: continue
            df.at[i,"LastPrice"]=price
            df.at[i,"P/L"]=round((price-r["Buy"])*r["Qty"],2)
            ind=compute_indicators(r["Stock"])
            feat={"dist_target":(r["Target"]-price)/r["Buy"],
                  "dist_sl":(price-r["SL"])/r["Buy"],
                  "rsi":ind["rsi"],
                  "ema_ratio":(ind["ema20"]/ind["ema50"]) if ind["ema50"] else 1}
            df.at[i,"Prob"]=predict_prob(model,feat) or 0
        df.to_excel(EXCEL_FILE,index=False)
    except Exception as e: print(f"[ERROR]{e}")

# ---------------- SCHEDULER ----------------
def scheduler_thread():
    schedule.every(1).minutes.do(check_prices)
    schedule.every().day.at("09:00").do(morning_summary)
    schedule.every().day.at("15:31").do(evening_summary)
    schedule.every().saturday.at("16:00").do(weekly_summary)
    schedule.every().day.at("23:30").do(nightly_backup)
    while True:
        schedule.run_pending(); time.sleep(30)

# ---------------- MAIN ----------------
if __name__=="__main__":
    ensure_excel()
    threading.Thread(target=scheduler_thread, daemon=True).start()
    RENDER_URL=os.getenv("RENDER_EXTERNAL_URL","https://swing-assistant-bot.onrender.com")
    WEBHOOK_URL=f"{RENDER_URL}/webhook"
    bot.remove_webhook(); bot.set_webhook(url=WEBHOOK_URL)
    print(f"[INFO] Webhook set: {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
