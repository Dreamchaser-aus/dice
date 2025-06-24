import os
import random
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
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

@app.route("/auth", methods=["POST"])
def auth():
    user_id = request.form.get("user_id")
    if not user_id: return "User ID required", 400
    session["user_id"] = user_id
    return redirect(url_for("dice"))

@app.route("/dice")
def dice():
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
        c.execute("SELECT user_id, username, phone, points, plays, last_game_time FROM users")
        users = [dict(zip([desc[0] for desc in c.description], row)) for row in c.fetchall()]
    return render_template("admin.html", users=users)

if __name__ == "__main__":
    app.run(debug=True)