import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 开始游戏", web_app=WebAppInfo(url="https://your-app.up.railway.app/dice"))
    ]])
    await update.message.reply_text("欢迎！点击下方按钮开始游戏：", reply_markup=keyboard)

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton("📱 发送手机号", request_contact=True)]]
    await update.message.reply_text("请发送您的手机号：", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))

async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact:
        with get_conn() as conn, conn.cursor() as c:
            c.execute("UPDATE users SET phone = %s WHERE user_id = %s", (contact.phone_number, contact.user_id))
            conn.commit()
        await update.message.reply_text("✅ 手机号绑定成功！")

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
        rows = c.fetchall()
    text = "🏆 当前排行榜：\n"
    for i, (username, points) in enumerate(rows, 1):
        text += f"{i}. @{username or '未知'} - {points}分\n"
    await update.message.reply_text(text.strip())

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("phone", phone))
    app.add_handler(MessageHandler(filters.CONTACT, save_phone))
    app.run_polling()

if __name__ == "__main__":
    main()