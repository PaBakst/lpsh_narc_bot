# bot.py
import os, logging
# from dotenv import load_dotenv 

from dotenv import load_dotenv
from pathlib import Path
from collections import defaultdict

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
from telegram.constants import ParseMode  # импортируем enum для parse_mode





from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes,
)
from openai import OpenAI   



import re

def convert_markdown_headings_to_bold(text: str) -> str:
    # Заменяем ### Заголовок → *Заголовок*
    text = re.sub(r"^###\s*(.*)", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s*(.*)", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^#\s*(.*)", r"*\1*", text, flags=re.MULTILINE)
    return text                 

# 1) загружаем переменные окружения
load_dotenv()
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# 2) настраиваем "клиента" DeepSeek
client = OpenAI(
    api_key = DEEPSEEK_API_KEY,
    base_url = "https://api.deepseek.com", 
)

logging.basicConfig(level=logging.INFO)       # чтобы видеть сообщения в терминале

# 3) /start
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Напиши мне что-нибудь 🙂")

# 4) чат-обработчик
# Истории пользователей: user_id → list of messages
chat_history = defaultdict(list)

from telegram.constants import ParseMode  # импортируем enum для parse_mode

async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    question = update.message.text

    if not chat_history[user_id]:
        chat_history[user_id].append({"role": "system", "content": "You are a helpful assistant who formats answers in Markdown for Telegram."})

    chat_history[user_id].append({"role": "user", "content": question})
    history = chat_history[user_id][-20:]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=history
    )

    assistant_reply = response.choices[0].message.content
    assistant_reply = convert_markdown_headings_to_bold(assistant_reply)
    chat_history[user_id].append({"role": "assistant", "content": assistant_reply})

    await update.message.reply_text(
        assistant_reply,
        parse_mode=ParseMode.MARKDOWN  # или ParseMode.MARKDOWN_V2, если нужно
    )

# 5) «Собираем» приложение и запускаем long-polling
def main() -> None:
    app = (ApplicationBuilder()               
           .token(TELEGRAM_TOKEN)
           .build())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.run_polling()                         # слушаем Telegram

if __name__ == "__main__":
    main()

