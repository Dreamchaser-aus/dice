from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import logging
import os
import psycopg2
import asyncio
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

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

async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_button = KeyboardButton("发送手机号", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("请点击下方按钮发送您的手机号进行绑定", reply_markup=markup)

# 用户点击按钮后自动触发此 contact handler
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.message.from_user.id
    phone = contact.phone_number

    # 存入数据库示例（注意需你已有 get_conn 方法）
    from main import get_conn  # 如果 main.py 中定义了此方法
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, username, phone)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET phone = EXCLUDED.phone
        """, (user_id, update.message.from_user.username, phone))
        conn.commit()

    await update.message.reply_text("✅ 手机号绑定成功！您可以开始游戏了。")

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
