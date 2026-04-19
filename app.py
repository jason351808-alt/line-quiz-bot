import os
import random
import mysql.connector
import pandas as pd

from flask import Flask, request, abort, render_template, redirect, session, flash, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    MessageAction,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-secret")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

db_config = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "line_quiz_bot"),
    "port": int(os.environ.get("DB_PORT", 3306)),
}


def get_db():
    return mysql.connector.connect(**db_config)


def normalize_text_command(text):
    return str(text).strip().replace("　", " ").strip()


def normalize_stored_answer(answer, q_type):
    text = str(answer).strip().upper()
    replacements = {
        "，": ",", "、": ",", "；": ",", ";": ",", "。": "", ".": "",
        " ": "",
        "甲": "1", "乙": "2", "丙": "3", "丁": "4", "戊": "5", "己": "6", "庚": "7", "辛": "8",
        "A": "1", "B": "2", "C": "3", "D": "4", "E": "5", "F": "6", "G": "7", "H": "8",
        "○": "O", "✗": "X", "×": "X",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    if q_type == "tf":
        true_set = {"O", "1", "是", "對", "正確", "對的", "TRUE", "T", "YES", "Y"}
        false_set = {"X", "2", "否", "錯", "不對", "錯誤", "FALSE", "F", "NO", "N"}
        if text in true_set:
            return "1"
        if text in false_set:
            return "2"
        return text

    filtered = "".join([c for c in text if c in "12345678"])
    if q_type == "multi":
        return "".join(sorted(set(filtered), key=lambda x: int(x)))
    if q_type == "single":
        return filtered[:1]
    return filtered or text


def init_app_tables():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key VARCHAR(100) PRIMARY KEY,
                setting_value TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_groups (
                id INT AUTO_INCREMENT PRIMARY KEY,
                group_name VARCHAR(100) NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_group_categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                quiz_group_id INT NOT NULL,
                category_name VARCHAR(100) NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_group_selection (
                user_id VARCHAR(100) PRIMARY KEY,
                quiz_group_id INT NULL,
                is_selecting_group TINYINT(1) NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_all_groups():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM quiz_groups ORDER BY id ASC")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def create_quiz_group(group_name):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO quiz_groups (group_name) VALUES (%s)", (group_name,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_quiz_group(group_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM quiz_group_categories WHERE quiz_group_id=%s", (group_id,))
        cursor.execute("DELETE FROM user_group_selection WHERE quiz_group_id=%s", (group_id,))
        cursor.execute("DELETE FROM quiz_groups WHERE id=%s", (group_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_group_categories(group_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT category_name FROM quiz_group_categories WHERE quiz_group_id=%s ORDER BY id ASC",
            (group_id,),
        )
        rows = cursor.fetchall()
        return [r["category_name"] for r in rows]
    finally:
        cursor.close()
        conn.close()


def get_group_categories_map():
    groups = get_all_groups()
    return {g["id"]: get_group_categories(g["id"]) for g in groups}


def set_group_categories(group_id, categories):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM quiz_group_categories WHERE quiz_group_id=%s", (group_id,))
        for category_name in categories:
            cursor.execute(
                "INSERT INTO quiz_group_categories (quiz_group_id, category_name) VALUES (%s, %s)",
                (group_id, category_name),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_user_group_selection(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM user_group_selection WHERE user_id=%s", (user_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def set_user_group_selection(user_id, quiz_group_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_group_selection (user_id, quiz_group_id, is_selecting_group)
            VALUES (%s, %s, 0)
            ON DUPLICATE KEY UPDATE quiz_group_id=%s, is_selecting_group=0
        """, (user_id, quiz_group_id, quiz_group_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def set_user_selecting_group(user_id, is_selecting):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_group_selection (user_id, quiz_group_id, is_selecting_group)
            VALUES (%s, NULL, %s)
            ON DUPLICATE KEY UPDATE is_selecting_group=%s
        """, (user_id, is_selecting, is_selecting))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_user_selected_group(user_id):
    selection = get_user_group_selection(user_id)
    if not selection or not selection.get("quiz_group_id"):
        return None
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM quiz_groups WHERE id=%s", (selection["quiz_group_id"],))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM admin_users WHERE username=%s AND password=%s",
            (username, password),
        )
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin:
            session["login"] = True
            return redirect("/dashboard")

        return render_template("login.html", error="帳號或密碼錯誤")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if not session.get("login"):
        return redirect("/")

    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()
    qtype = request.args.get("type", "").strip()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM questions WHERE 1=1"
    params = []

    if keyword:
        sql += " AND question LIKE %s"
        params.append(f"%{keyword}%")

    if category:
        sql += " AND category=%s"
        params.append(category)

    if qtype:
        sql += " AND type=%s"
        params.append(qtype)

    sql += " ORDER BY id DESC"
    cursor.execute(sql, params)
    questions = cursor.fetchall()

    cursor.execute(
        "SELECT DISTINCT category FROM questions "
        "WHERE category IS NOT NULL AND category != '' ORDER BY category"
    )
    categories = cursor.fetchall()

    cursor.close()
    conn.close()

    groups = get_all_groups()
    group_categories_map = get_group_categories_map()

    return render_template(
        "dashboard.html",
        data=questions,
        categories=categories,
        keyword=keyword,
        category=category,
        qtype=qtype,
        groups=groups,
        group_categories_map=group_categories_map,
    )


@app.route("/groups/add", methods=["POST"])
def add_group():
    if not session.get("login"):
        return redirect("/")

    group_name = request.form.get("group_name", "").strip()
    if not group_name:
        flash("請輸入組別名稱", "danger")
        return redirect("/dashboard")

    create_quiz_group(group_name)
    flash(f"已新增組別：{group_name}", "success")
    return redirect("/dashboard")


@app.route("/groups/delete/<int:group_id>", methods=["POST"])
def remove_group(group_id):
    if not session.get("login"):
        return redirect("/")

    delete_quiz_group(group_id)
    flash("組別已刪除", "success")
    return redirect("/dashboard")


@app.route("/groups/set-categories/<int:group_id>", methods=["POST"])
def update_group_categories(group_id):
    if not session.get("login"):
        return redirect("/")

    selected_categories = request.form.getlist(f"group_categories_{group_id}")
    set_group_categories(group_id, selected_categories)

    if selected_categories:
        flash("已設定組別題庫範圍：" + "、".join(selected_categories), "success")
    else:
        flash("此組別未勾選科目，將視為全部科目", "warning")

    return redirect("/dashboard")


@app.route("/add", methods=["GET", "POST"])
def add_question():
    if not session.get("login"):
        return redirect("/")

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        question = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        option_e = request.form.get("option_e", "").strip()
        option_f = request.form.get("option_f", "").strip()
        option_g = request.form.get("option_g", "").strip()
        option_h = request.form.get("option_h", "").strip()
        answer = request.form.get("answer", "")
        qtype = request.form.get("type", "single").strip()
        answer = normalize_stored_answer(answer, qtype)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO questions
            (category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, qtype),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/dashboard")

    return render_template("question_form.html", mode="add", q=None)


@app.route("/edit/<int:qid>", methods=["GET", "POST"])
def edit_question(qid):
    if not session.get("login"):
        return redirect("/")

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        question = request.form.get("question", "").strip()
        option_a = request.form.get("option_a", "").strip()
        option_b = request.form.get("option_b", "").strip()
        option_c = request.form.get("option_c", "").strip()
        option_d = request.form.get("option_d", "").strip()
        option_e = request.form.get("option_e", "").strip()
        option_f = request.form.get("option_f", "").strip()
        option_g = request.form.get("option_g", "").strip()
        option_h = request.form.get("option_h", "").strip()
        answer = request.form.get("answer", "")
        qtype = request.form.get("type", "single").strip()
        answer = normalize_stored_answer(answer, qtype)

        cursor.execute(
            """
            UPDATE questions
            SET category=%s, question=%s, option_a=%s, option_b=%s,
                option_c=%s, option_d=%s, option_e=%s, option_f=%s,
                option_g=%s, option_h=%s, answer=%s, type=%s
            WHERE id=%s
            """,
            (category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, qtype, qid),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/dashboard")

    cursor.execute("SELECT * FROM questions WHERE id=%s", (qid,))
    q = cursor.fetchone()
    cursor.close()
    conn.close()

    if not q:
        return "找不到題目", 404

    return render_template("question_form.html", mode="edit", q=q)


@app.route("/delete/<int:qid>")
def delete_question(qid):
    if not session.get("login"):
        return redirect("/")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE id=%s", (qid,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/dashboard")


@app.route("/bulk-delete", methods=["POST"])
def bulk_delete_questions():
    if not session.get("login"):
        return redirect("/")

    ids = request.form.getlist("question_ids")
    if not ids:
        ids_csv = request.form.get("selected_ids", "").strip()
        if ids_csv:
            ids = [x.strip() for x in ids_csv.split(",") if x.strip()]

    ids = [x for x in ids if str(x).isdigit()]
    if not ids:
        flash("請先勾選要刪除的題目", "warning")
        return redirect("/dashboard")

    conn = get_db()
    cursor = conn.cursor()
    try:
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute(f"DELETE FROM questions WHERE id IN ({placeholders})", tuple(ids))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    flash(f"已刪除 {len(ids)} 筆題目", "success")
    return redirect("/dashboard")


@app.route("/import", methods=["GET", "POST"])
def import_excel():
    if not session.get("login"):
        return redirect("/")

    if request.method == "POST":
        file = request.files.get("file")
        mode = request.form.get("mode", "upsert")

        if not file or file.filename == "":
            flash("請先選擇 Excel 檔案", "danger")
            return redirect("/import")

        try:
            df = pd.read_excel(file)

            required_columns = [
                "category", "question",
                "option_a", "option_b", "option_c", "option_d",
                "option_e", "option_f", "option_g", "option_h",
                "answer", "type",
            ]
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                flash(f"缺少欄位：{', '.join(missing)}", "danger")
                return redirect("/import")

            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            inserted_count = 0
            updated_count = 0
            failed_count = 0
            error_rows = []

            if mode == "replace_all":
                cursor.execute("DELETE FROM questions")

            for index, row in df.iterrows():
                try:
                    category = "" if pd.isna(row["category"]) else str(row["category"]).strip()
                    question = "" if pd.isna(row["question"]) else str(row["question"]).strip()
                    option_a = "" if pd.isna(row["option_a"]) else str(row["option_a"]).strip()
                    option_b = "" if pd.isna(row["option_b"]) else str(row["option_b"]).strip()
                    option_c = "" if pd.isna(row["option_c"]) else str(row["option_c"]).strip()
                    option_d = "" if pd.isna(row["option_d"]) else str(row["option_d"]).strip()
                    option_e = "" if pd.isna(row["option_e"]) else str(row["option_e"]).strip()
                    option_f = "" if pd.isna(row["option_f"]) else str(row["option_f"]).strip()
                    option_g = "" if pd.isna(row["option_g"]) else str(row["option_g"]).strip()
                    option_h = "" if pd.isna(row["option_h"]) else str(row["option_h"]).strip()
                    answer = "" if pd.isna(row["answer"]) else str(row["answer"])
                    qtype = "single" if pd.isna(row["type"]) else str(row["type"]).strip().lower()
                    answer = normalize_stored_answer(answer, qtype)

                    if not question:
                        raise ValueError("題目不可為空")
                    if qtype not in ["single", "multi", "tf"]:
                        raise ValueError("type 只能是 single / multi / tf")
                    if not answer:
                        raise ValueError("answer 不可為空")

                    cursor.execute("SELECT id FROM questions WHERE question=%s LIMIT 1", (question,))
                    existing = cursor.fetchone()

                    if existing and mode == "upsert":
                        cursor.execute(
                            """
                            UPDATE questions
                            SET category=%s, option_a=%s, option_b=%s, option_c=%s, option_d=%s,
                                option_e=%s, option_f=%s, option_g=%s, option_h=%s, answer=%s, type=%s
                            WHERE id=%s
                            """,
                            (category, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, qtype, existing["id"]),
                        )
                        updated_count += 1
                    else:
                        cursor.execute(
                            """
                            INSERT INTO questions
                            (category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (category, question, option_a, option_b, option_c, option_d, option_e, option_f, option_g, option_h, answer, qtype),
                        )
                        inserted_count += 1

                except Exception as row_error:
                    failed_count += 1
                    error_rows.append(f"第 {index + 2} 列：{row_error}")

            conn.commit()
            cursor.close()
            conn.close()

            flash(
                f"匯入完成：新增 {inserted_count} 筆、更新 {updated_count} 筆、失敗 {failed_count} 筆",
                "success" if failed_count == 0 else "warning",
            )
            for err in error_rows[:10]:
                flash(err, "danger")

            return redirect("/import")

        except Exception as e:
            flash(f"匯入失敗：{e}", "danger")
            return redirect("/import")

    return render_template("import.html")


@app.route("/download-template")
def download_template():
    if not session.get("login"):
        return redirect("/")
    return send_from_directory("static", "question_template.xlsx", as_attachment=True)


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        import traceback
        print("Webhook error:", e)
        traceback.print_exc()
        abort(500)

    return "OK"


def normalize_answer(user_input, q_type):
    return normalize_stored_answer(user_input, q_type)


def check_answer(user_input, correct_answer, q_type):
    return normalize_answer(user_input, q_type) == normalize_answer(correct_answer, q_type)


def format_question_text(shuffled_q):
    if shuffled_q["type"] == "tf":
        return f"📚 是非題\n{shuffled_q['question']}\n\n1. 是\n2. 否\n\n請輸入 1 / 2，或 是 / 否"

    text = f"📚 {'多選題' if shuffled_q['type'] == 'multi' else '單選題'}\n{shuffled_q['question']}\n\n"

    for k, v in shuffled_q["options"].items():
        text += f"{k}. {v}\n"

    if shuffled_q["type"] == "multi":
        text += "\n請輸入答案，例如：13、1,3、24"
    else:
        text += "\n請輸入答案，例如：1"

    return text


def shuffle_question(q):
    if q["type"] == "tf":
        return {
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "options": {"1": "是", "2": "否"},
            "answer": normalize_stored_answer(q["answer"], q["type"]),
        }

    options = [
        ("1", q.get("option_a")), ("2", q.get("option_b")),
        ("3", q.get("option_c")), ("4", q.get("option_d")),
        ("5", q.get("option_e")), ("6", q.get("option_f")),
        ("7", q.get("option_g")), ("8", q.get("option_h")),
    ]
    options = [(k, v) for k, v in options if v]

    new_options = {k: v for k, v in options}
    answer = normalize_stored_answer(q["answer"], q["type"])

    if q["type"] == "single":
        new_answer = answer
    else:
        new_answer_list = [c for c in answer if c in new_options]
        random.shuffle(new_answer_list)
        new_answer = "".join(new_answer_list)

    return {
        "id": q["id"],
        "type": q["type"],
        "question": q["question"],
        "options": new_options,
        "answer": new_answer,
    }


def build_question_message(shuffled_q):
    if shuffled_q["type"] == "tf":
        return TemplateSendMessage(
            alt_text="是非題",
            template=ButtonsTemplate(
                title="是非題",
                text=shuffled_q["question"][:60],
                actions=[
                    MessageAction(label="1. 是", text="1"),
                    MessageAction(label="2. 否", text="2"),
                ],
            ),
        )

    if shuffled_q["type"] == "single" and len(shuffled_q["options"]) <= 4:
        actions = []
        for k, v in shuffled_q["options"].items():
            actions.append(MessageAction(label=f"{k}. {str(v)[:14]}", text=str(k)))

        return TemplateSendMessage(
            alt_text="單選題",
            template=ButtonsTemplate(
                title="單選題",
                text=shuffled_q["question"][:60],
                actions=actions,
            ),
        )

    return TextSendMessage(text=format_question_text(shuffled_q))


def get_user_progress(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_progress WHERE user_id=%s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def save_user_progress(user_id, current_question_id, current_answer, question_type,
                       answered_questions=None, score=0, total_answered=0):
    conn = get_db()
    cursor = conn.cursor()
    sql = """
    INSERT INTO user_progress
    (user_id, current_question_id, current_answer, question_type, answered_questions, score, total_answered)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        current_question_id=%s, current_answer=%s, question_type=%s,
        answered_questions=%s, score=%s, total_answered=%s
    """
    cursor.execute(sql, (
        user_id, current_question_id, current_answer, question_type, answered_questions, score, total_answered,
        current_question_id, current_answer, question_type, answered_questions, score, total_answered,
    ))
    conn.commit()
    cursor.close()
    conn.close()


def append_answered_question(progress, question_id):
    old = progress.get("answered_questions") if progress else None
    if not old:
        return str(question_id)
    items = [x for x in old.split(",") if x]
    if str(question_id) not in items:
        items.append(str(question_id))
    return ",".join(items)


def get_random_question(user_id):
    progress = get_user_progress(user_id)
    excluded = []

    if progress and progress.get("answered_questions"):
        excluded = [x for x in progress["answered_questions"].split(",") if x]

    selected_group = get_user_selected_group(user_id)
    group_categories = get_group_categories(selected_group["id"]) if selected_group else []

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM questions WHERE 1=1"
    params = []

    if group_categories:
        placeholders = ",".join(["%s"] * len(group_categories))
        sql += f" AND category IN ({placeholders})"
        params.extend(group_categories)

    if excluded:
        placeholders = ",".join(["%s"] * len(excluded))
        sql += f" AND id NOT IN ({placeholders})"
        params.extend(excluded)

    sql += " ORDER BY RAND() LIMIT 1"

    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def log_answer(user_id, question_id, user_answer, correct_answer, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO answer_logs (user_id, question_id, user_answer, correct_answer, is_correct)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, question_id, user_answer, correct_answer, is_correct),
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_wrong_questions(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT DISTINCT q.*
            FROM answer_logs a
            JOIN questions q ON a.question_id = q.id
            WHERE a.user_id=%s AND a.is_correct=0
            ORDER BY q.id DESC
            """,
            (user_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def clear_wrong_questions(user_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM answer_logs WHERE user_id=%s AND is_correct=0", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def build_wrong_book_text(user_id):
    wrong_questions = get_wrong_questions(user_id)
    if not wrong_questions:
        return "你的錯題本目前是空的。"

    lines = ["📘 錯題本（最多顯示10題）"]
    for idx, q in enumerate(wrong_questions[:10], start=1):
        answer_display = format_answer_display(q.get("answer", ""), q.get("type", "single"))
        lines.append(f"\n{idx}. {q.get('question', '')}")
        lines.append(f"正確答案：{answer_display}")

    if len(wrong_questions) > 10:
        lines.append(f"\n...還有 {len(wrong_questions) - 10} 題未顯示")

    return "\n".join(lines)


def reset_user_progress(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_progress
        (user_id, current_question_id, current_answer, question_type, answered_questions, score, total_answered)
        VALUES (%s, NULL, NULL, NULL, NULL, 0, 0)
        ON DUPLICATE KEY UPDATE
            current_question_id=NULL, current_answer=NULL, question_type=NULL,
            answered_questions=NULL, score=0, total_answered=0
        """,
        (user_id,),
    )
    conn.commit()
    cursor.close()
    conn.close()


def format_answer_display(answer, qtype):
    answer = normalize_stored_answer(answer, qtype)

    if qtype == "tf":
        if answer == "1":
            return "1"
        if answer == "2":
            return "2"
        return answer

    return "".join([c for c in str(answer) if c in "12345678"])


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = normalize_text_command(event.message.text)

    if "錯題本" in msg and not any(x in msg for x in ["清空", "重設", "刪除"]):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=build_wrong_book_text(user_id)),
        )
        return

    if any(x in msg for x in ["清空錯題本", "重設錯題本", "刪除錯題本"]):
        clear_wrong_questions(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🧹 已清空錯題本"),
        )
        return

    if msg == "選組":
        groups = get_all_groups()
        if not groups:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="目前尚未建立任何組別，請先請管理員到後台新增組別。"),
            )
            return

        set_user_selecting_group(user_id, 1)
        lines = ["請選擇組別："]
        for idx, g in enumerate(groups, start=1):
            lines.append(f"{idx}. {g['group_name']}")
        lines.append("")
        lines.append("請直接輸入數字，例如：1")

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="\n".join(lines)),
        )
        return

    if msg == "目前組別":
        selected_group = get_user_selected_group(user_id)
        if not selected_group:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="你目前尚未選擇組別，請先輸入「選組」。"),
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"你目前的組別是：{selected_group['group_name']}"),
            )
        return

    selection = get_user_group_selection(user_id)
    if selection and int(selection.get("is_selecting_group") or 0) == 1 and msg.isdigit():
        groups = get_all_groups()
        idx = int(msg) - 1

        if 0 <= idx < len(groups):
            chosen_group = groups[idx]
            set_user_group_selection(user_id, chosen_group["id"])
            reset_user_progress(user_id)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"你已選擇組別：{chosen_group['group_name']}\n輸入「開始」即可作答。"),
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="組別編號不存在，請重新輸入。"),
            )
        return

    if msg.upper() in ["開始", "START", "開始測驗", "RESET", "重設", "重新開始"]:
        selected_group = get_user_selected_group(user_id)
        if not selected_group:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請先輸入「選組」選擇你的組別。"),
            )
            return

        if msg.upper() in ["RESET", "重設", "重新開始"]:
            reset_user_progress(user_id)

        question_row = get_random_question(user_id)
        if not question_row:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="目前這個組別沒有可出的題目。"),
            )
            return

        progress = get_user_progress(user_id)
        shuffled = shuffle_question(question_row)
        answered_questions = append_answered_question(progress, question_row["id"])

        save_user_progress(
            user_id=user_id,
            current_question_id=question_row["id"],
            current_answer=shuffled["answer"],
            question_type=question_row["type"],
            answered_questions=answered_questions,
            score=progress["score"] if progress else 0,
            total_answered=progress["total_answered"] if progress else 0,
        )

        line_bot_api.reply_message(event.reply_token, build_question_message(shuffled))
        return

    if msg.upper() in ["停止", "STOP", "結束", "退出"]:
        reset_user_progress(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🛑 已停止測驗\n輸入「開始」可以重新開始"),
        )
        return

    progress = get_user_progress(user_id)
    if not progress or not progress.get("current_question_id"):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請先輸入「選組」，再輸入「開始」進行測驗。"),
        )
        return

    is_correct = check_answer(msg, progress["current_answer"], progress["question_type"])
    score = int(progress.get("score") or 0)
    total_answered = int(progress.get("total_answered") or 0) + 1

    if is_correct:
        score += 1

    log_answer(
        user_id=user_id,
        question_id=progress["current_question_id"],
        user_answer=normalize_answer(msg, progress["question_type"]),
        correct_answer=progress["current_answer"],
        is_correct=is_correct,
    )

    next_question = get_random_question(user_id)
    display_answer = format_answer_display(progress["current_answer"], progress["question_type"])
    result_text = "✅ 答對了！" if is_correct else f"❌ 答錯了！正確答案是：{display_answer}"

    if next_question:
        shuffled = shuffle_question(next_question)
        answered_questions = append_answered_question(progress, next_question["id"])

        save_user_progress(
            user_id=user_id,
            current_question_id=next_question["id"],
            current_answer=shuffled["answer"],
            question_type=next_question["type"],
            answered_questions=answered_questions,
            score=score,
            total_answered=total_answered,
        )

        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=result_text), build_question_message(shuffled)],
        )
    else:
        save_user_progress(
            user_id=user_id,
            current_question_id=None,
            current_answer=None,
            question_type=None,
            answered_questions=progress.get("answered_questions"),
            score=score,
            total_answered=total_answered,
        )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"{result_text}\n\n🎉 題庫完成！\n\n輸入「重新開始」可再次測驗。"),
        )


init_app_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
