import os
import random
from functools import wraps

import bcrypt
import mysql.connector
import pandas as pd
from flask import Flask, flash, redirect, render_template, request, session, url_for
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None


def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "line_quiz_bot"),
    )


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def shuffle_question(question_row):
    options = [
        ("A", question_row["option_a"]),
        ("B", question_row["option_b"]),
        ("C", question_row["option_c"]),
        ("D", question_row["option_d"]),
    ]
    correct_text = dict(options).get(question_row["answer"])
    random.shuffle(options)

    labels = ["A", "B", "C", "D"]
    shuffled = {}
    new_answer = None

    for idx, (_, text) in enumerate(options):
        label = labels[idx]
        shuffled[label] = text
        if text == correct_text:
            new_answer = label

    return {
        "question": question_row["question"],
        "category": question_row.get("category", ""),
        "options": shuffled,
        "answer": new_answer,
        "id": question_row["id"],
    }


def format_question_text(shuffled):
    return (
        f"📚 題目：\n{shuffled['question']}\n\n"
        f"A. {shuffled['options']['A']}\n"
        f"B. {shuffled['options']['B']}\n"
        f"C. {shuffled['options']['C']}\n"
        f"D. {shuffled['options']['D']}\n\n"
        f"請直接回覆 A / B / C / D"
    )


def get_user_progress(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM user_progress WHERE user_id = %s",
        (user_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def save_user_progress(user_id, qid, correct_answer, answered_questions, score=None, total_answered=None):
    conn = get_db()
    cursor = conn.cursor()

    if score is None or total_answered is None:
        cursor.execute(
            "SELECT score, total_answered FROM user_progress WHERE user_id = %s",
            (user_id,)
        )
        existing = cursor.fetchone()
        if existing:
            if score is None:
                score = existing[0]
            if total_answered is None:
                total_answered = existing[1]
        else:
            score = 0 if score is None else score
            total_answered = 0 if total_answered is None else total_answered

    sql = """
    INSERT INTO user_progress
    (user_id, current_question_id, current_answer, answered_questions, score, total_answered)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    current_question_id = VALUES(current_question_id),
    current_answer = VALUES(current_answer),
    answered_questions = VALUES(answered_questions),
    score = VALUES(score),
    total_answered = VALUES(total_answered)
    """
    cursor.execute(sql, (user_id, qid, correct_answer, answered_questions, score, total_answered))
    conn.commit()
    cursor.close()
    conn.close()


def reset_user_progress(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_progress (user_id, current_question_id, current_answer, answered_questions, score, total_answered)
        VALUES (%s, NULL, NULL, '', 0, 0)
        ON DUPLICATE KEY UPDATE
        current_question_id = NULL,
        current_answer = NULL,
        answered_questions = '',
        score = 0,
        total_answered = 0
        """,
        (user_id,)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_random_question(user_id):
    progress = get_user_progress(user_id)
    answered_ids = []
    if progress and progress.get("answered_questions"):
        answered_ids = [x for x in progress["answered_questions"].split(",") if x.strip()]

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if answered_ids:
        placeholders = ",".join(["%s"] * len(answered_ids))
        sql = f"SELECT * FROM questions WHERE id NOT IN ({placeholders}) ORDER BY RAND() LIMIT 1"
        cursor.execute(sql, tuple(answered_ids))
    else:
        cursor.execute("SELECT * FROM questions ORDER BY RAND() LIMIT 1")

    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def append_answered_question(progress, qid):
    answered = []
    if progress and progress.get("answered_questions"):
        answered = [x for x in progress["answered_questions"].split(",") if x.strip()]
    answered.append(str(qid))
    return ",".join(answered)


def log_answer(user_id, question_id, user_answer, correct_answer, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO answer_logs (user_id, question_id, user_answer, correct_answer, is_correct)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, question_id, user_answer, correct_answer, is_correct)
    )
    conn.commit()
    cursor.close()
    conn.close()


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admin_users WHERE username = %s", (username,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin and bcrypt.checkpw(password.encode(), admin["password"].encode()):
            session["admin_logged_in"] = True
            session["admin_username"] = admin["username"]
            return redirect(url_for("dashboard"))

        flash("登入失敗，請檢查帳號密碼。", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM questions WHERE 1=1"
    params = []

    if keyword:
        sql += " AND question LIKE %s"
        params.append(f"%{keyword}%")

    if category:
        sql += " AND category = %s"
        params.append(category)

    sql += " ORDER BY id DESC"
    cursor.execute(sql, params)
    questions = cursor.fetchall()

    cursor.execute("SELECT DISTINCT category FROM questions WHERE category IS NOT NULL AND category <> '' ORDER BY category")
    categories = [row["category"] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        questions=questions,
        categories=categories,
        keyword=keyword,
        selected_category=category,
    )


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_question():
    if request.method == "POST":
        form = request.form
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO questions (category, question, option_a, option_b, option_c, option_d, answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                form["category"].strip(),
                form["question"].strip(),
                form["option_a"].strip(),
                form["option_b"].strip(),
                form["option_c"].strip(),
                form["option_d"].strip(),
                form["answer"].strip().upper(),
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("題目新增成功。", "success")
        return redirect(url_for("dashboard"))

    return render_template("question_form.html", mode="add", question=None)


@app.route("/edit/<int:question_id>", methods=["GET", "POST"])
@login_required
def edit_question(question_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        form = request.form
        cursor.execute(
            """
            UPDATE questions
            SET category = %s,
                question = %s,
                option_a = %s,
                option_b = %s,
                option_c = %s,
                option_d = %s,
                answer = %s
            WHERE id = %s
            """,
            (
                form["category"].strip(),
                form["question"].strip(),
                form["option_a"].strip(),
                form["option_b"].strip(),
                form["option_c"].strip(),
                form["option_d"].strip(),
                form["answer"].strip().upper(),
                question_id,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("題目更新成功。", "success")
        return redirect(url_for("dashboard"))

    cursor.execute("SELECT * FROM questions WHERE id = %s", (question_id,))
    question = cursor.fetchone()
    cursor.close()
    conn.close()

    if not question:
        flash("找不到題目。", "danger")
        return redirect(url_for("dashboard"))

    return render_template("question_form.html", mode="edit", question=question)


@app.route("/delete/<int:question_id>", methods=["POST"])
@login_required
def delete_question(question_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE id = %s", (question_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("題目已刪除。", "warning")
    return redirect(url_for("dashboard"))


@app.route("/upload", methods=["POST"])
@login_required
def upload_excel():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("請選擇 Excel 檔案。", "danger")
        return redirect(url_for("dashboard"))

    df = pd.read_excel(file)
    expected = ["category", "question", "A", "B", "C", "D", "answer"]
    if list(df.columns) != expected:
        flash("Excel 欄位格式錯誤，請使用範例檔格式。", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cursor = conn.cursor()
    count = 0

    for _, row in df.iterrows():
        cursor.execute(
            """
            INSERT INTO questions (category, question, option_a, option_b, option_c, option_d, answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(row["category"]).strip(),
                str(row["question"]).strip(),
                str(row["A"]).strip(),
                str(row["B"]).strip(),
                str(row["C"]).strip(),
                str(row["D"]).strip(),
                str(row["answer"]).strip().upper(),
            ),
        )
        count += 1

    conn.commit()
    cursor.close()
    conn.close()

    flash(f"Excel 匯入成功，共新增 {count} 題。", "success")
    return redirect(url_for("dashboard"))


@app.route("/callback", methods=["POST"])
def callback():
    if not line_bot_api or not handler:
        return "LINE credentials not configured", 500

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400

    return "OK"


@handler.add(MessageEvent, message=TextMessage) if handler else (lambda func: func)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip().upper()

    if msg in ["開始", "START", "重新開始", "RESET"]:
        if msg in ["重新開始", "RESET"]:
            reset_user_progress(user_id)

        question_row = get_random_question(user_id)
        if not question_row:
            reset_user_progress(user_id)
            question_row = get_random_question(user_id)

        if not question_row:
            reply = "目前題庫沒有任何題目。"
        else:
            progress = get_user_progress(user_id)
            shuffled = shuffle_question(question_row)
            answered_questions = append_answered_question(progress, question_row["id"])
            score = progress["score"] if progress else 0
            total_answered = progress["total_answered"] if progress else 0
            save_user_progress(user_id, question_row["id"], shuffled["answer"], answered_questions, score, total_answered)
            reply = format_question_text(shuffled)

    elif msg in ["A", "B", "C", "D"]:
        progress = get_user_progress(user_id)
        if not progress or not progress.get("current_question_id") or not progress.get("current_answer"):
            reply = "請先輸入「開始」開始測驗。"
        else:
            is_correct = msg == progress["current_answer"]
            score = int(progress["score"] or 0) + (1 if is_correct else 0)
            total_answered = int(progress["total_answered"] or 0) + 1
            log_answer(
                user_id=user_id,
                question_id=progress["current_question_id"],
                user_answer=msg,
                correct_answer=progress["current_answer"],
                is_correct=is_correct,
            )

            result_line = "✅ 答對了！" if is_correct else f"❌ 答錯了！正確答案是 {progress['current_answer']}"

            next_question = get_random_question(user_id)
            if next_question:
                shuffled = shuffle_question(next_question)
                answered_questions = append_answered_question(progress, next_question["id"])
                save_user_progress(user_id, next_question["id"], shuffled["answer"], answered_questions, score, total_answered)
                accuracy = round(score / total_answered * 100, 1)
                reply = (
                    f"{result_line}\n"
                    f"目前成績：{score}/{total_answered}（{accuracy}%）\n\n"
                    f"{format_question_text(shuffled)}"
                )
            else:
                accuracy = round(score / total_answered * 100, 1) if total_answered else 0
                save_user_progress(user_id, None, None, progress.get("answered_questions", ""), score, total_answered)
                reply = (
                    f"{result_line}\n\n"
                    f"🎉 題庫已完成！\n"
                    f"總成績：{score}/{total_answered}\n"
                    f"正確率：{accuracy}%\n"
                    f"輸入「重新開始」可再測一次。"
                )
    else:
        reply = "可輸入「開始」開始測驗，或輸入「重新開始」重置進度。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
