import os
import random
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devsecret")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

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
    if not phone:
        return "请输入手机号", 400
    session["bind_phone"] = phone
    return "成功！请在 Telegram 中点击「发送手机号」按钮进行验证"
    
@app.route("/auth", methods=["POST"])
def auth():
    user_id = request.form.get("user_id")
    if not user_id: return "User ID required", 400
    session["user_id"] = user_id
    return redirect(url_for("dice"))

@app.route("/dice")
def dice():
    uid = request.args.get("uid")
    if uid:
        session["user_id"] = uid
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dice.html")

@app.route("/dice/play", methods=["POST"])
def play_dice():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "未登录"}), 401
    user_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)
    delta, result = (10, "你赢了！+10") if user_roll > bot_roll else (-5, "你输了！-5") if user_roll < bot_roll else (0, "平局")
    with get_conn() as conn, conn.cursor() as c:
        c.execute("INSERT INTO game_logs (user_id, user_roll, bot_roll, result) VALUES (%s, %s, %s, %s)",
                  (user_id, user_roll, bot_roll, result))
        c.execute("UPDATE users SET points = points + %s, plays = plays + 1, last_game_time = CURRENT_TIMESTAMP WHERE user_id = %s",
                  (delta, user_id))
        conn.commit()
    return jsonify({"user": user_roll, "bot": bot_roll, "message": result})

@app.route("/admin")
def admin_dashboard():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            SELECT 
                u.user_id, u.username, u.phone, u.points, u.plays, u.last_game_time,
                COALESCE(inv.invited_count, 0) AS invited_count,
                u.blocked
            FROM users u
            LEFT JOIN (
                SELECT invited_by AS inviter_id, COUNT(*) AS invited_count
                FROM users
                WHERE invited_by IS NOT NULL
                GROUP BY invited_by
            ) inv ON u.user_id = inv.inviter_id
        """)
        users = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]

        stats = {
            "total": len(users),
            "verified": sum(1 for u in users if u["phone"]),
            "blocked": sum(1 for u in users if u.get("blocked")),
            "points": sum(u["points"] or 0 for u in users)
        }

    return render_template("admin.html", users=users, stats=stats)

@app.route("/user/save", methods=["POST"])
def save_user_status():
    user_id = request.form.get("user_id")
    blocked = request.form.get("blocked") == "1"
    with get_conn() as conn, conn.cursor() as c:
        c.execute("UPDATE users SET blocked = %s WHERE user_id = %s", (blocked, user_id))
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
        c.execute("SELECT user_id, username, phone, points FROM users WHERE inviter_id = %s", (user_id,))
        rows = c.fetchall()
        invitees = [dict(zip([desc[0] for desc in c.description], row)) for row in rows]
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
