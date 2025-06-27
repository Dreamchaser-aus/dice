import os
import random
import psycopg2
import asyncio
import logging
import nest_asyncio

nest_asyncio.apply()

from dotenv import load_dotenv
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DB Helper ---
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# --- Utilities ---
def get_user_id(update: Update):
    if update.message:
        return update.message.from_user.id
    if update.callback_query:
        return update.callback_query.from_user.id
    return None

def get_chat_id(update: Update):
    if update.message:
        return update.message.chat_id
    if update.callback_query:
        return update.callback_query.message.chat_id
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 处理 inviter 参数（来自 t.me/bot?start=inviter_123456）
    if context.args and context.args[0].startswith("inviter_"):
        inviter_id = context.args[0].split("_")[1]
        user_id = update.effective_user.id

        # 存储 inviter_id -> 可保存到数据库或 session 映射（例如 Redis/session/临时表）
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE users SET invited_by = %s WHERE user_id = %s AND invited_by IS NULL", (inviter_id, user_id))
            conn.commit()

    keyboard = [
        [InlineKeyboardButton("📱 绑定手机号", callback_data="bind")],
        [InlineKeyboardButton("🏆 查看排行榜", callback_data="rank")],
        [InlineKeyboardButton("📨 我的邀请", callback_data="invitees")],
        [InlineKeyboardButton("🔗 获取邀请链接", callback_data="share")],
        [InlineKeyboardButton("❓ 帮助", callback_data="help")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎲 欢迎使用骰子游戏 Bot！请选择一个操作：", reply_markup=markup)

# --- Command: bind ---
async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id(update)
    contact_button = KeyboardButton("📱 发送手机号", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=chat_id, text="请点击下方按钮发送手机号完成绑定", reply_markup=markup)

# --- Contact Handler ---
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.message.from_user.id
    phone = contact.phone_number

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, phone)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET phone = EXCLUDED.phone
            """, (user_id, update.message.from_user.username, phone))
            conn.commit()
    except Exception as e:
        logging.exception("数据库保存手机号失败")
        await update.message.reply_text("❌ 绑定失败，请稍后重试。")
        return

    game_url = f"https://dice-production-1f4e.up.railway.app/dice?uid={user_id}"
    await update.message.reply_text(
        f"✅ 手机号绑定成功！\n点击开始游戏：{game_url}",
        disable_web_page_preview=True
    )

# --- Command: /rank ---
async def show_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id(update)
    try:
        with get_conn() as conn, conn.cursor() as c:
            c.execute("SELECT username, points FROM users WHERE points IS NOT NULL ORDER BY points DESC LIMIT 10")
            rows = c.fetchall()
    except Exception as e:
        logging.exception("查询排行榜失败")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 查询失败，请稍后重试。")
        return

    if not rows:
        await context.bot.send_message(chat_id=chat_id, text="暂无排行榜数据。")
        return

    msg = "🏆 当前积分排行榜：\n"
    for i, (name, pts) in enumerate(rows, 1):
        msg += f"{i}. {name or '匿名'} - {pts} 分\n"
    await context.bot.send_message(chat_id=chat_id, text=msg)

# --- Command: share ---
async def share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)
    invite_link = f"https://t.me/{context.bot.username}?start=inviter_{user_id}"
    await context.bot.send_message(chat_id=chat_id, text=f"📨 分享你的邀请链接给好友：\n{invite_link}")

# --- Command: invitees ---
async def invitees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)

    try:
        with get_conn() as conn, conn.cursor() as c:
            c.execute("""
                SELECT username, phone, points
                FROM users
                WHERE invited_by = %s
            """, (user_id,))
            rows = c.fetchall()
    except Exception as e:
        logging.exception("查询邀请失败")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 查询失败，请稍后重试。")
        return

    if not rows:
        await context.bot.send_message(chat_id=chat_id, text="你还没有邀请任何好友。")
        return

    msg = f"📋 你已邀请 {len(rows)} 位好友：\n"
    for i, (username, phone, points) in enumerate(rows, 1):
        name = username or phone or "匿名"
        msg += f"{i}. {name} - {points or 0} 分\n"

    await context.bot.send_message(chat_id=chat_id, text=msg)

# --- Command: help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Bot 支持的指令如下：\n\n"
        "/start - 开始游戏介绍\n"
        "/bind - 绑定手机号以参与游戏\n"
        "/share - 获取你的专属邀请链接\n"
        "/rank - 查看排行榜\n"
        "/help - 显示帮助信息\n"
    )
    chat_id = get_chat_id(update)
    await context.bot.send_message(chat_id=chat_id, text=help_text)

# --- Inline Menu ---
async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    command = query.data
    if command == "bind":
        await bind(update, context)
    elif command == "rank":
        await show_rank(update, context)
    elif command == "invitees":
        await invitees(update, context)
    elif command == "share":
        await share(update, context)
    elif command == "help":
        await help_command(update, context)

# --- Entry Point ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    await application.bot.delete_webhook(drop_pending_updates=True)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(CommandHandler("share", share))
    application.add_handler(CommandHandler("rank", show_rank))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("invitees", invitees))

    application.add_handler(CallbackQueryHandler(handle_menu_button))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
