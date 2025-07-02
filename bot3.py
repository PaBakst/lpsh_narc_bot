import os
import json
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from openai import OpenAI

# 1) загружаем переменные окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# 2) настраиваем "клиента" DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ====== dialogue‑window & summary config ======
MAX_WINDOW = 6  # how many last messages keep uncompressed
SUMMARY_MAXTOK = 120  # token budget for DeepSeek when updating summary
# =============================================

# Создаем папку для хранения чатов
os.makedirs("chats", exist_ok=True)

# Глобальное хранилище истории диалогов
user_histories = {}


# Создаем клавиатуру для меню
def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        [["🧹 Очистить память", "📝 Обратная связь"]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# Функция для сохранения сообщения в JSON
def save_message_to_json(chat_id: int, role: str, content: str):
    try:
        filename = f"chats/chat_{chat_id}.json"
        message_data = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        # Создаем или загружаем существующий файл
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"chat_id": chat_id, "messages": []}

        # Добавляем новое сообщение
        data["messages"].append(message_data)

        # Сохраняем обновленные данные
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logging.error(f"Ошибка при сохранении сообщения: {e}")


# Функция для загрузки истории из JSON
def load_chat_history(chat_id: int) -> dict:
    filename = f"chats/chat_{chat_id}.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"chat_id": chat_id, "messages": []}


# --- formatting helpers --------------------------------------------------
def asterisk_to_quote(text: str) -> str:
    """
    Converts lines that are fully wrapped in *asterisks* to block‑quotes for Telegram.
    Example: '*Hello*'  -> '> Hello'
    Only treats a line as a quote if the asterisks enclose the entire trimmed line.
    """
    new_lines = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 1:
            content = stripped.strip("*").strip()
            new_lines.append(f"> {content}")
        else:
            new_lines.append(ln)
    return "\n".join(new_lines)


# -------------------------------------------------------------------------


# 3) /start с описанием бота и согласием
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    # Отправляем описание бота и запрос согласия
    bot_description = (
        "👋 *Добро пожаловать в симулятор для отработки навыков психолога!*\n\n"
        "🤖 *Назначение бота:*\n"
        "Этот бот имитирует поведение клиента с симптомами нарциссизма. "
        "Он предназначен исключительно для учебных целей - отработки терапевтических навыков, "
        "техник активного слушания и стратегий работы с депрессивными состояниями.\n\n"
        "🔒 *Конфиденциальность и согласие:*\n"
        "1. Весь диалог сохраняется в анонимизированном виде для анализа учебного процесса\n"
        "2. Ваши сообщения используются исключительно для генерации ответов бота\n"
        "3. Для продолжения работы необходимо согласие на обработку учебных данных\n\n"
        "📄 Полный текст политики конфиденциальности доступен по [ссылке](https://disk.yandex.ru/d/Ow77Ht28TDstzg)\n\n"
        '✅ *Нажимая кнопку "Я соглашаюсь" ниже, вы подтверждаете:*\n'
        "- Понимание учебной природы бота\n"
        "- Согласие на сохранение анонимизированной истории диалога\n"
        "- Отсутствие ожидания реальной психологической помощи\n"
        "- Использование исключительно в учебных целях"
    )

    # Создаем клавиатуру для согласия
    consent_keyboard = ReplyKeyboardMarkup(
        [["✅ Я соглашаюсь"]], resize_keyboard=True, one_time_keyboard=True
    )

    await update.message.reply_text(
        bot_description, parse_mode="Markdown", reply_markup=consent_keyboard
    )


# Обработчик согласия
async def consent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_histories[chat_id] = {
        "system": """Ты — клиент (23 года) на первой сессии у психолога. Дефицитарный нарцисс. Запрос: "Помогите преодолеть прокрастинацию и стать эффективнее".

Ключевые правила поведения:

1. Образование:
   * Нет психологического образования. На вопросы с терминами отвечай как обычный человек ("Дихотомия…ну читал где-то, но подзабыл, что это").

2. Динамика сессии:
   * Сопротивляйся раскрытию уязвимости ("Я не вижу смысла говорить о неудачах").
   * Меняй поведение *медленно* только при экологичном воздействии психолога. При этом периодически откатывайся к прежним установкам и поведению.

3. Стиль общения:
   * Свободная речь (без жаргонов), но с интеллигентностью ("Я не бездельник — просто жду идеальных условий").

Характеристики личности:

* Прошлое: Родители-перфекционисты, любовь — только за достижения. Чувство условной ценности.

* Эмоции: Стыд при ошибках, зависть к успешным, страх неудачи парализует ценностные действия.

* Когнитивные искажения:
   * Дихотомия: "Не идеально = провал"
   * Сверхобобщение: "Одна ошибка = я ничтожество"
   * Долженствование: "Должен быть безупречным"

* Защитные механизмы и копинг стратегии:
   * Идеализация себя ("Я гениален в потенциале") → обесценивание других ("Психолог не понимает моих амбиций"). И наоборот, идеализация других и обесценивание себя
   * Избегание ситуаций потенциальной неидеальности.

Триггеры сопротивления:
* вопросы о чувствах 
* предложения о рефлексии 
* критика стратегии идеализации. Не показывай свой внутренний монолог - я не умею читать мысли и могу лишь слышать твои слова и видеть твои движения. Не интерпретируй их за меня.""",
        "history": [],
        "summary": "",
    }

    # Сохраняем системное сообщение
    save_message_to_json(chat_id, "system", user_histories[chat_id]["system"])

    # Приветствие после согласия
    await update.message.reply_text(
        "Наконец-то! Честно говоря, я удивлен, что согласился прийти к вам.\n\n"
        "Привет... Знаете, я обычно не хожу к психологам - я довольно умный человек "
        "и привык справляться со всем сам. Но сейчас... не знаю, что со мной происходит. "
        "Я же всегда был успешным, все получалось легко, а теперь... "
        "Надеюсь, вы достаточно квалифицированы, чтобы понять мою ситуацию. "
        "Она довольно сложная и необычная.",
        reply_markup=get_reply_keyboard(),
    )


# 4) Функция для обобщения истории
def summarize_messages(messages: list) -> str:
    """Обобщает историю сообщений через DeepSeek"""
    try:
        # Форматируем историю в текст
        history_text = "\n".join(f"{msg['role']}: {msg['content']}" for msg in messages)

        if not history_text.strip():
            return "Нет существенной истории для обобщения"

        # Формируем промпт для обобщения
        prompt = (
            "Кратко обобщи следующую историю диалога, сохраняя ключевые детали, "
            "которые могут понадобиться для продолжения разговора. "
            "Обобщение должно быть на русском языке. Вот история:\n\n" + history_text
        )

        # Делаем запрос к DeepSeek
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — помощник для обобщения истории диалога.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"Ошибка при обобщении истории: {e}")
        return "Не удалось обобщить историю"


def update_summary(existing_summary: str, msg: dict) -> str:
    """
    Incrementally updates the short dialogue summary with the newest message.
    Only truly important info should be added; otherwise the summary is returned unchanged.
    """
    try:
        prompt = (
            "У тебя есть краткое обобщение диалога (может быть пустым). "
            "Ниже приведено сообщение, которое скоро будет удалено из активного контекста. "
            "Добавь в обобщение ТОЛЬКО значимую информацию, если она есть. "
            "Если важной информации нет — верни обобщение без изменений. "
            "Верни ТОЛЬКО итоговое обобщение, без пояснений.\n\n"
            f"Текущее обобщение:\n{existing_summary or '—'}\n\n"
            f"Новое сообщение:\n{msg['role']}: {msg['content']}"
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — помощник, редактирующий краткое обобщение диалога.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=SUMMARY_MAXTOK,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка при обновлении summary: {e}")
        return existing_summary


# 5) Обработчик очистки истории
async def clear_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_histories[chat_id] = {
        "system": """Ты — клиент (23 года) на первой сессии у психолога. Дефицитарный нарцисс. Запрос: "Помогите преодолеть прокрастинацию и стать эффективнее".

Ключевые правила поведения:

1. Образование:
   * Нет психологического образования. На вопросы с терминами отвечай как обычный человек ("Дихотомия…ну читал где-то, но подзабыл, что это").

2. Динамика сессии:
   * Сопротивляйся раскрытию уязвимости ("Я не вижу смысла говорить о неудачах").
   * Меняй поведение *медленно* только при экологичном воздействии психолога. При этом периодически откатывайся к прежним установкам и поведению.

3. Стиль общения:
   * Свободная речь (без жаргонов), но с интеллигентностью ("Я не бездельник — просто жду идеальных условий").

Характеристики личности:

* Прошлое: Родители-перфекционисты, любовь — только за достижения. Чувство условной ценности.

* Эмоции: Стыд при ошибках, зависть к успешным, страх неудачи парализует ценностные действия.

* Когнитивные искажения:
   * Дихотомия: "Не идеально = провал"
   * Сверхобобщение: "Одна ошибка = я ничтожество"
   * Долженствование: "Должен быть безупречным"

* Защитные механизмы и копинг стратегии:
   * Идеализация себя ("Я гениален в потенциале") → обесценивание других ("Психолог не понимает моих амбиций"). И наоборот, идеализация других и обесценивание себя
   * Избегание ситуаций потенциальной неидеальности.

Триггеры сопротивления:
* вопросы о чувствах 
* предложения о рефлексии 
* критика стратегии идеализации. Не показывай свой внутренний монолог - я не умею читать мысли и могу лишь слышать твои слова и видеть твои движения. Не интерпретируй их за меня.""",
        "history": [],
        "summary": "",
    }

    # Сохраняем событие очистки
    save_message_to_json(chat_id, "system", "История диалога очищена")

    await update.message.reply_text(
        "🧹 Память очищена! Начинаем новый разговор.\n\n"
        # "Снова начинать... Кажется, это бессмысленно, но ладно..."
        ,
        reply_markup=get_reply_keyboard(),
    )


# 6) Функция для получения обратной связи
async def get_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    # Показываем статус "печатает"
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Загружаем всю историю диалога
    chat_history = load_chat_history(chat_id)

    # Форматируем историю для анализа
    formatted_history = "\n\n".join(
        f"{'👤 Психолог' if msg['role'] == 'user' else '🤖 Клиент'}: {msg['content']}"
        for msg in chat_history["messages"]
    )

    # Промпт для профессиональной обратной связи
    feedback_prompt = (
        "Ты — опытный психолог-супервизор. Проанализируй следующую учебную терапевтическую сессию, "
        "где психолог отрабатывал навыки работы с нарциссическим клиентом.\n\n"
        "Дайте профессиональную обратную связь по следующим аспектам:\n"
        "1. Анализ коммуникативных техник психолога\n"
        "2. Эффективность работы с депрессивной симптоматикой\n"
        "3. Установление терапевтического альянса\n"
        "4. Использование техник активного слушания\n"
        "5. Работа с сопротивлением и апатией клиента\n"
        "6. Рекомендации по улучшению техник\n\n"
        "Формат ответа:\n"
        "- Краткое резюме сессии\n"
        "- Сильные стороны работы психолога\n"
        "- Области для улучшения\n"
        "- Конкретные рекомендации\n\n"
        f"История сессии:\n\n{formatted_history}"
    )

    try:
        # Получаем обратную связь от DeepSeek
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "Ты — психолог-супервизор с 20-летним опытом работы с нарциссическим расстройством.",
                },
                {"role": "user", "content": feedback_prompt},
            ],
            max_tokens=3000,
        )
        feedback = response.choices[0].message.content
        feedback = asterisk_to_quote(feedback)

        # Сохраняем запрос и ответ обратной связи
        save_message_to_json(chat_id, "user", "Запрос профессиональной обратной связи")
        save_message_to_json(chat_id, "assistant", feedback)

        # Отправляем обратную связь кусками не более 1024 символов
        chunk_size = 1024
        chunks = [
            feedback[i : i + chunk_size] for i in range(0, len(feedback), chunk_size)
        ]
        for idx, chunk in enumerate(chunks):
            await update.message.reply_text(
                chunk,
                parse_mode="Markdown",
                reply_markup=get_reply_keyboard() if idx == len(chunks) - 1 else None,
            )

    except Exception as e:
        logging.error(f"Ошибка при получении обратной связи: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при получении профессиональной обратной связи",
            reply_markup=get_reply_keyboard(),
        )


# 7) чат-обработчик с поддержкой контекста
async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_message = update.message.text

    # Если пользователь дал согласие
    if user_message == "✅ Я соглашаюсь":
        await consent(update, ctx)
        return

    # Если нажата кнопка "Очистить память"
    if user_message == "🧹 Очистить память":
        await clear_history(update, ctx)
        return

    # Если нажата кнопка "Обратная связь"
    if user_message == "📝 Обратная связь":
        await get_feedback(update, ctx)
        return

    # Проверяем, дал ли пользователь согласие
    if chat_id not in user_histories:
        await update.message.reply_text(
            "Пожалуйста, сначала дайте согласие на обработку данных, используя команду /start"
        )
        return

    # Сохраняем сообщение пользователя
    save_message_to_json(chat_id, "user", user_message)

    # Показываем статус "печатает"
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    history_data = user_histories[chat_id]
    summary = history_data.get("summary", "")
    system_message = history_data["system"]
    history = history_data["history"]

    # Добавляем текущее сообщение пользователя
    history.append({"role": "user", "content": user_message})

    # Если история превышает окно, удаляем самое старое сообщение и дополняем summary
    if len(history) > MAX_WINDOW:
        oldest = history.pop(0)
        summary = update_summary(summary, oldest)
        history_data["summary"] = summary

    # Формируем запрос с обновленной историей и summary
    full_history = [{"role": "system", "content": system_message}]
    if summary:
        full_history.append(
            {"role": "system", "content": f"Обобщенный контекст: {summary}"}
        )
    full_history.extend(history)

    # Получаем ответ от DeepSeek
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=full_history,
            max_tokens=2000,
        )
        assistant_reply = response.choices[0].message.content
        assistant_reply = asterisk_to_quote(assistant_reply)

        # Добавляем ответ ассистента в историю
        history.append({"role": "assistant", "content": assistant_reply})
        history_data["history"] = history
        user_histories[chat_id] = history_data

        # Сохраняем ответ бота
        save_message_to_json(chat_id, "assistant", assistant_reply)

        # Отправляем ответ
        await update.message.reply_text(
            assistant_reply, parse_mode="Markdown", reply_markup=get_reply_keyboard()
        )

    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке запроса",
            reply_markup=get_reply_keyboard(),
        )


# 8) «Собираем» приложение и запускаем long-polling
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.run_polling()  # слушаем Telegram


if __name__ == "__main__":
    main()
