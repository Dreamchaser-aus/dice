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
    user_id = update.message.from_user.id
    phone = contact.phone_number

    # 存入数据库
    from main import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, username, phone)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET phone = EXCLUDED.phone
        """, (user_id, update.message.from_user.username, phone))
        conn.commit()

    # 给出自动登录链接
    game_url = f"https://dice-production-1f4e.up.railway.app/dice?uid={user_id}"
    await update.message.reply_text(
        f"✅ 手机号绑定成功！\n点击开始游戏：{game_url}",
        disable_web_page_preview=True
    )

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
    
async def share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    invite_link = f"https://dice-production-1f4e.up.railway.app/bind?inviter={user_id}"
    await update.message.reply_text(f"📨 分享你的邀请链接给好友：\n{invite_link}")   
    
# --- Command: /invitees ---
async def invitees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            SELECT username, phone, points
            FROM users
            WHERE invited_by = %s
        """, (user_id,))
        rows = c.fetchall()

    if not rows:
        await update.message.reply_text("你还没有邀请任何好友。")
        return

    msg = f"📋 你已邀请 {len(rows)} 位好友：\n"
    for i, (username, phone, points) in enumerate(rows, 1):
        name = username or phone or "匿名"
        msg += f"{i}. {name} - {points or 0} 分\n"

    await update.message.reply_text(msg)
    
# --- Command: /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Bot 支持的指令如下：\n\n"
        "/start - 开始游戏介绍\n"
        "/bind - 绑定手机号以参与游戏\n"
        "/share - 获取你的专属邀请链接\n"
        "/rank - 查看排行榜\n"
        "/help - 显示帮助信息\n"
    )
    await update.message.reply_text(help_text)
    
    
# --- Entry Point ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(CommandHandler("share", share))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    application.add_handler(CommandHandler("rank", show_rank))
    application.add_handler(CommandHandler("help", help_command))  # ✅ 注册 /help
    application.add_handler(CommandHandler("invitees", invitees))    

    await application.run_polling()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
