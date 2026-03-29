
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
    MessageAction
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
    "port": int(os.environ.get("DB_PORT", 3306))
}

def get_db():
    return mysql.connector.connect(**db_config)

def shuffle_question(q):
    if q["type"] == "tf":
        return {
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "options": {"A": "是", "B": "否"},
            "answer": q["answer"]
        }

    options = [
        ("A", q.get("option_a")), ("B", q.get("option_b")),
        ("C", q.get("option_c")), ("D", q.get("option_d"))
    ]
    options = [(k, v) for k, v in options if v]

    new_options = {k: v for k, v in options}

    if q["type"] == "single":
        new_answer = q["answer"]
    else:
        new_answer_list = [c for c in q["answer"] if c in new_options]
        random.shuffle(new_answer_list)
        new_answer = "".join(new_answer_list)

    return {
        "id": q["id"],
        "type": q["type"],
        "question": q["question"],
        "options": new_options,
        "answer": new_answer
    }

def format_question_text(shuffled_q):
    if shuffled_q["type"] == "tf":
        return f"📚 是非題\n{shuffled_q['question']}\n\nO. 是\nX. 否"

    text = f"📚 {'多選題' if shuffled_q['type']=='multi' else '單選題'}\n{shuffled_q['question']}\n\n"
    for k, v in shuffled_q["options"].items():
        num = ord(k) - 64
        text += f"{num}. {v}\n"
    return text

def build_question_message(shuffled_q):
    if shuffled_q["type"] == "single":
        actions = []
        for k, v in shuffled_q["options"].items():
            num = ord(k) - 64
            actions.append(MessageAction(label=f"{num}. {v}", text=k))

        return TemplateSendMessage(
            alt_text="單選題",
            template=ButtonsTemplate(
                title="單選題",
                text=shuffled_q["question"][:60],
                actions=actions
            )
        )

    return TextSendMessage(text=format_question_text(shuffled_q))

