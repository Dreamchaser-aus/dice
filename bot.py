from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import logging
import os
import psycopg2
import asyncio
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DB Helper ---
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# --- Command: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001F3B2 欢迎来到骰子游戏！输入 /bind 开始绑定手机号。")

# --- Command: /bind ---
async def start_bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("\U0001F4F1 发送手机号", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text("请点击下方按钮授权你的手机号", reply_markup=keyboard)

# --- Handle Contact ---
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    phone = contact.phone_number
    tg_id = update.effective_user.id

    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            UPDATE users SET user_id = %s WHERE phone = %s
        """, (tg_id, phone))
        conn.commit()

    await update.message.reply_text(f"✅ 成功绑定 Telegram ID：{tg_id} 与手机号：{phone}")

# --- Command: /rank 排行榜 ---
async def show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            SELECT username, points FROM users 
            WHERE points IS NOT NULL ORDER BY points DESC LIMIT 10
        """)
        rows = c.fetchall()

    if not rows:
        await update.message.reply_text("暂无排行榜数据。")
        return

    msg = "\U0001F3C6 积分排行榜：\n"
    for i, (name, pts) in enumerate(rows, 1):
        msg += f"{i}. {name or '匿名'} - {pts} 分\n"
    await update.message.reply_text(msg)

# --- Bot Entry Point ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 添加所有 handler，例如
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CommandHandler("rank", show_rank))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
