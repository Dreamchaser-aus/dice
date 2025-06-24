import os
import random
import psycopg2
import asyncio
import logging
import nest_asyncio

nest_asyncio.apply()

from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DB Helper ---
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# --- Command: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎲 欢迎来到骰子游戏！请输入 /bind 开始绑定手机号。")

# --- Command: /bind ---
async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_button = KeyboardButton("📱 发送手机号", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("请点击下方按钮发送手机号完成绑定", reply_markup=markup)

# --- Contact Handler ---
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user

    if not contact or str(contact.user_id) != str(user.id):
        await update.message.reply_text("⚠️ 请使用您自己的 Telegram 账号发送手机号")
        return

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, username, phone)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET username = EXCLUDED.username, phone = EXCLUDED.phone
        """, (user.id, user.username or "", contact.phone_number))
        conn.commit()

    await update.message.reply_text("✅ 手机号绑定成功！您可以开始游戏了。")

# --- Command: /rank ---
async def show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT username, points FROM users WHERE points IS NOT NULL ORDER BY points DESC LIMIT 10")
        rows = c.fetchall()

    if not rows:
        await update.message.reply_text("暂无排行榜数据。")
        return

    msg = "🏆 当前积分排行榜：\n"
    for i, (name, pts) in enumerate(rows, 1):
        msg += f"{i}. {name or '匿名'} - {pts} 分\n"
    await update.message.reply_text(msg)

# --- Entry Point ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CommandHandler("rank", show_rank))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

