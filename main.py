import os
import random
import psycopg2
from flask import  Flask
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from dotenv import load_dotenv
from datetime import datetime
from datetime import date

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devsecret")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

from datetime import date

def auto_reset_daily_plays():
    today = date.today()
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            UPDATE users
            SET plays = 10,
                daily_reset = %s
            WHERE daily_reset IS NULL OR daily_reset < %s
        """, (today, today))
        conn.commit()

# 请求结束自动关闭连接
@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()
        
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/bind")
def bind_page():
    return render_template("bind.html")

@app.route("/bind/submit", methods=["POST"])
def bind_submit():
    phone = request.form.get("phone")
    inviter = request.args.get("inviter")  # 通过 URL 获取邀请人 ID

    if not phone:
        return "请输入手机号", 400

    session["bind_phone"] = phone
    session["invited_by"] = inviter  # 保存到 session 中供后续使用

    return "成功！请在 Telegram 中点击「发送手机号」按钮进行验证"
    
@app.route("/auth", methods=["POST"])
def auth():
    user_id = request.form.get("user_id")
    if not user_id:
        return "User ID required", 400

    invited_by = session.get("invited_by")

    with get_conn() as conn, conn.cursor() as c:
        # 若用户尚未存在则插入
        c.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (user_id, phone, invited_by) VALUES (%s, %s, %s)", (
                user_id, session.get("bind_phone"), invited_by
            ))
            conn.commit()

    session["user_id"] = user_id
    return redirect(url_for("dice"))

@app.route("/dice")
def dice():
    uid = request.args.get("uid")
    if uid:
        session["user_id"] = uid
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT plays, daily_reset FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
        plays_today = row[0] or 0
        daily_reset = row[1]
        today = date.today()
        if daily_reset != today:
            plays_today = 0
    remaining = max(0, 10 - plays_today)
    return render_template("dice.html", remaining=remaining)

@app.route("/dice/play", methods=["POST"])
def play_dice():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "未登录"}), 401

    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT plays, daily_reset FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 404

        plays_today, daily_reset = row
        today = date.today()

        if daily_reset != today:
            plays_today = 0
            c.execute("UPDATE users SET plays = 0, daily_reset = %s WHERE user_id = %s", (today, user_id))
            conn.commit()

        if plays_today >= 10:
            return jsonify({"error": "你今天已达游戏上限（10次），请明天再来"}), 403

        user_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)
        delta, result = (10, "你赢了！+10") if user_roll > bot_roll else (-5, "你输了！-5") if user_roll < bot_roll else (0, "平局")

        c.execute("INSERT INTO game_logs (user_id, user_roll, bot_roll, result) VALUES (%s, %s, %s, %s)",
                  (user_id, user_roll, bot_roll, result))
        c.execute("""
            UPDATE users
            SET points = points + %s,
                plays = plays + 1,
                last_game_time = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (delta, user_id))
        conn.commit()

        remaining = 9 - plays_today

    return jsonify({
        "user": user_roll,
        "bot": bot_roll,
        "message": result,
        "remaining": remaining
    })
    
from flask import request

@app.route("/admin")
def admin_dashboard():
    auto_reset_daily_plays()
    keyword = request.args.get("q", "").strip()
    blocked_filter = request.args.get("filter", "").strip()

    query = """
    SELECT 
        u.user_id, u.username, u.phone, u.points, u.plays, u.last_game_time,
        u.created_at, u.invited_by, u.blocked,
        inviter.username AS inviter,
        COALESCE(inv.invited_count, 0) AS invited_count
    FROM users u
    LEFT JOIN users inviter ON u.invited_by = inviter.user_id
    LEFT JOIN (
        SELECT invited_by, COUNT(*) AS invited_count
        FROM users
        WHERE invited_by IS NOT NULL
        GROUP BY invited_by
    ) inv ON u.user_id = inv.invited_by
    WHERE 1=1
    """
    params = []

    if keyword:
        query += " AND (u.username ILIKE %s OR u.phone ILIKE %s)"
        params += [f"%{keyword}%", f"%{keyword}%"]

    if blocked_filter == "1":
        query += " AND u.blocked = TRUE"
    elif blocked_filter == "0":
        query += " AND (u.blocked = FALSE OR u.blocked IS NULL)"

    with get_conn() as conn, conn.cursor() as c:
        c.execute(query, params)
        users = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]

        stats = {
            "total": len(users),
            "verified": sum(1 for u in users if u["phone"]),
            "blocked": sum(1 for u in users if u.get("blocked")),
            "points": sum(u["points"] or 0 for u in users)
        }

    def format_time(value):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value or ''

    for u in users:
        u["created_at"] = format_time(u.get("created_at"))
        u["last_game_time"] = format_time(u.get("last_game_time"))

    return render_template("admin.html", users=users, stats=stats, request=request, keyword=keyword, page=1, total_pages=1)

@app.route("/user/save", methods=["POST"])
def save_user():
    data = request.get_json()
    user_id = data.get("user_id")
    blocked = data.get("blocked")
    points = data.get("points")
    plays = data.get("plays")
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            UPDATE users
            SET blocked = %s,
                points = %s,
                plays = %s
            WHERE user_id = %s
        """, (blocked, points, plays, user_id))
        conn.commit()
    return jsonify({"status": "ok"})

@app.route("/user/delete", methods=["POST"])
def delete_user():
    user_id = request.form.get("user_id")
    with get_conn() as conn, conn.cursor() as c:
        c.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
    return jsonify({"status": "deleted"})

@app.route("/admin/rank/today")
def today_rank():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            SELECT u.user_id, u.username, u.points, COUNT(g.id) AS plays_today
            FROM users u
            JOIN game_logs g ON u.user_id = g.user_id
            WHERE g.timestamp::date = CURRENT_DATE
            GROUP BY u.user_id, u.username, u.points
            ORDER BY u.points DESC
            LIMIT 10;
        """)
        users = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("rank_today.html", users=users)
    
@app.route("/user/logs")
def user_logs():
    user_id = request.args.get("user_id")
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            SELECT user_roll, bot_roll, result, timestamp
            FROM game_logs
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT 100
        """, (user_id,))
        logs = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("user_logs.html", logs=logs)

@app.route("/invitees")
def view_invitees():
    user_id = request.args.get("user_id")
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT user_id, username, phone, points FROM users WHERE invited_by = %s", (user_id,))
        invitees = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("invitees.html", invitees=invitees)
    
@app.route("/init")
def init_tables():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY
            );
        """)
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plays INTEGER DEFAULT 0;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_game_time TIMESTAMP;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by BIGINT;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN DEFAULT FALSE;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_reset DATE;")

        c.execute("""
            CREATE TABLE IF NOT EXISTS game_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                user_roll INTEGER,
                bot_roll INTEGER,
                result TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    return "✅ 数据表初始化完成（包含字段补全）"

if __name__ == "__main__":
    app.run(debug=True)
