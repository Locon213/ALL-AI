import logging
import os
import requests
import base64
import json
import time
from datetime import datetime, timedelta
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from flask import Flask, request, jsonify
from threading import Thread
import asyncio

# Создайте объект HTTPXRequest
httpx_request = HTTPXRequest(
    read_timeout=120,
    write_timeout=120,
    connect_timeout=120
)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токены API
API_TOKEN = "7953823124:AAEvTebtGxiyQ-S1Sb6KUOVMhsX5JQPgoxo"
KANDINSKY_API_KEY = "637F66C7FEFC4490519D2AFC3BD96BBE"
KANDINSKY_SECRET_KEY = "492EA9669523F2EF2F083B6D3E532576"
KANDINSKY_API_URL = "https://api-key.fusionbrain.ai/"
FLUX_API_URL = "https://api-inference.huggingface.co/models/"
HUGGINGFACE_API_TOKEN = "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"

# Список поддерживаемых моделей
MODELS = {
    "flux_dev": "black-forest-labs/FLUX.1-dev",
    "flux_schnell": "black-forest-labs/FLUX.1-schnell",
    "stable_diffusion": "stabilityai/stable-diffusion-3.5-large",
    "kandinsky": "kandinsky",
    "hermes_llama": "NousResearch/Hermes-3-Llama-3.1-8B",
    "phi_3_5_mini": "microsoft/Phi-3.5-mini-instruct",
    "gemma_2_9b": "google/gemma-2-9b-it",
    "mistral_nemo": "mistralai/Mistral-Nemo-Instruct-2407"
}

# Категории моделей
IMAGE_MODELS = ["flux_dev", "flux_schnell", "stable_diffusion", "kandinsky"]
TEXT_MODELS = ["hermes_llama", "phi_3_5_mini", "gemma_2_9b", "mistral_nemo"]

# Хранилище данных пользователей
user_data = {}

# ID канала для пинга
PING_CHANNEL_ID = "@ALLAIPING"

# Максимальное количество токенов для текстовых моделей
MAX_TOKENS = 8192

# Проверка подписки на канал
async def is_subscribed(update: Update) -> bool:
    chat_id = "@AllAI_News_bot"
    user_id = update.effective_user.id

    try:
        member = await update.get_bot().get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки: {e}")
        return False

# Приветственное сообщение
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Пользователь начал взаимодействие с ботом.")
    await update.message.reply_text(
        "👋 Привет! Я бот ALL AI Other. 🎨💬\n"
        "Я могу создавать изображения на основе текста и общаться с текстовыми моделями.\n"
        "Попробуй команды /generate_image или /generate_text, чтобы начать! 🚀"
    )

# Генерация изображения
async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if not await is_subscribed(update):
        await update.message.reply_text(
            "❌ Вы должны подписаться на канал [All AI News](https://t.me/AllAI_News_bot), чтобы использовать бота.",
            parse_mode="Markdown"
        )
        return

    last_request = user_data.get(user_id, {}).get("last_request")
    if last_request and datetime.now() - last_request < timedelta(minutes=1):
        remaining_time = timedelta(minutes=1) - (datetime.now() - last_request)
        seconds = remaining_time.total_seconds()
        await update.message.reply_text(f"⏳ Пожалуйста, подождите {int(seconds)} секунд перед новой генерацией.")
        return

    keyboard = [
        [InlineKeyboardButton("Flux.1 Schnell 🚀", callback_data="flux_schnell")],
        [InlineKeyboardButton("Flux.1 Dev ⚙️", callback_data="flux_dev")],
        [InlineKeyboardButton("Stable Diffusion 🖌️", callback_data="stable_diffusion")],
        [InlineKeyboardButton("Kandinsky 🎨", callback_data="kandinsky")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите модель для генерации изображения:",
        reply_markup=reply_markup
    )

# Генерация текста
async def generate_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if not await is_subscribed(update):
        await update.message.reply_text(
            "❌ Вы должны подписаться на канал [All AI News](https://t.me/AllAI_News_bot), чтобы использовать бота.",
            parse_mode="Markdown"
        )
        return

    last_request = user_data.get(user_id, {}).get("last_request")
    if last_request and datetime.now() - last_request < timedelta(minutes=1):
        remaining_time = timedelta(minutes=1) - (datetime.now() - last_request)
        seconds = remaining_time.total_seconds()
        await update.message.reply_text(f"⏳ Пожалуйста, подождите {int(seconds)} секунд перед новой генерацией.")
        return

    keyboard = [
        [InlineKeyboardButton("Hermes LLaMA 🦙", callback_data="hermes_llama")],
        [InlineKeyboardButton("Phi-3.5 Mini 🤖", callback_data="phi_3_5_mini")],
        [InlineKeyboardButton("Gemma 2.9B 🌐", callback_data="gemma_2_9b")],
        [InlineKeyboardButton("Mistral Nemo 🌟", callback_data="mistral_nemo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите модель для генерации текста:",
        reply_markup=reply_markup
    )

# Обработка выбора модели
async def select_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data[user_id] = user_data.get(user_id, {})
    user_data[user_id]["model"] = query.data

    if query.data in IMAGE_MODELS:
        if query.message:
            await query.edit_message_text("Модель выбрана. ✍️ Напишите описание изображения.")
        else:
            logger.warning("Не удалось отредактировать сообщение: сообщение отсутствует.")
    elif query.data in TEXT_MODELS:
        if query.message:
            await query.edit_message_text("Модель выбрана. ✍️ Напишите ваш запрос.")
        else:
            logger.warning("Не удалось отредактировать сообщение: сообщение отсутствует.")

# Обработка описания
async def process_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user = user_data.get(user_id, {})
    if not user.get("model"):
        await update.message.reply_text("⚠️ Сначала выберите модель с помощью команды /generate_image или /generate_text.")
        return

    prompt = update.message.text
    logger.info(f"Пользователь выбрал модель: {user['model']}, описание: {prompt}")

    last_request = user.get("last_request")
    if last_request and datetime.now() - last_request < timedelta(minutes=1):
        remaining_time = timedelta(minutes=1) - (datetime.now() - last_request)
        seconds = remaining_time.total_seconds()
        await update.message.reply_text(f"⏳ Пожалуйста, подождите {int(seconds)} секунд перед новой генерацией.")
        return

    await update.message.reply_text("⏳ Генерация... Это может занять немного времени.")
    user_data[user_id]["last_request"] = datetime.now()

    try:
        if user["model"] in IMAGE_MODELS:
            content = generate_image(user["model"], prompt)
            if content:
                await send_image(update, content, prompt)
            else:
                await update.message.reply_text("❌ Ошибка при генерации изображения. Попробуйте ещё раз!")
        elif user["model"] in TEXT_MODELS:
            content = generate_text(user["model"], prompt)
            if content:
                await send_text(update, content, prompt)
            else:
                await update.message.reply_text("❌ Ошибка при генерации текста. Попробуйте ещё раз!")
    except Exception as e:
        logger.error(f"Ошибка при генерации: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

# Генерация изображения через API
def generate_image(model: str, prompt: str) -> bytes:
    if model == "kandinsky":
        return generate_image_kandinsky(prompt)
    else:
        url = f"{FLUX_API_URL}{MODELS[model]}"
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}
        response = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=120)
        response.raise_for_status()
        return response.content

# Генерация изображения через Kandinsky
def generate_image_kandinsky(prompt: str) -> bytes:
    try:
        headers = {
            "X-Key": f"Key {KANDINSKY_API_KEY}",
            "X-Secret": f"Secret {KANDINSKY_SECRET_KEY}"
        }
        response = requests.get(f"{KANDINSKY_API_URL}key/api/v1/models", headers=headers, timeout=120)
        response.raise_for_status()
        model_id = response.json()[0]["id"]

        params = {
            "type": "GENERATE",
            "numImages": 1,
            "width": 1024,
            "height": 1024,
            "generateParams": {"query": prompt}
        }
        data = {
            "model_id": (None, model_id),
            "params": (None, json.dumps(params), "application/json")
        }
        response = requests.post(
            f"{KANDINSKY_API_URL}key/api/v1/text2image/run", headers=headers, files=data, timeout=120
        )
        response.raise_for_status()
        task_id = response.json()["uuid"]

        for _ in range(10):
            status_response = requests.get(
                f"{KANDINSKY_API_URL}key/api/v1/text2image/status/{task_id}",
                headers=headers, timeout=120
            )
            status_response.raise_for_status()
            status_data = status_response.json()

            if status_data["status"] == "DONE":
                return base64.b64decode(status_data["images"][0])
            elif status_data["status"] == "FAIL":
                return None
            time.sleep(5)
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка генерации через Kandinsky: {e}")
        return None

# Генерация текста через Hugging Face API
def generate_text(model: str, prompt: str) -> str:
    url = f"{FLUX_API_URL}{MODELS[model]}"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_length": MAX_TOKENS
        }
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()[0]["generated_text"]

# Отправка изображения
async def send_image(update: Update, image_data: bytes, prompt: str) -> None:
    try:
        user_id = update.message.from_user.id

        duration = datetime.now() - user_data.get(user_id, {}).get("last_request", datetime.now())
        minutes, seconds = divmod(duration.total_seconds(), 60)

        # Сохраняем изображение
        file_path = f"generated_image_{user_id}.png"
        with open(file_path, "wb") as f:
            f.write(image_data)

        with open(file_path, "rb") as f:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Переделать", callback_data="redo")]])

            await update.message.reply_photo(
                photo=InputFile(f),
                caption=(
                    f"🎉 Вот ваше изображение!\n"
                    f"🖌️ Модель: {user_data[user_id]['model']}\n"
                    f"⏱ Время генерации: {int(minutes)} мин. {int(seconds)} сек.\n"
                    f"📜 Описание: {prompt}"
                ),
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        await update.message.reply_text("⚠️ Ошибка при отправке изображения.")


# Отправка текста
async def send_text(update: Update, text: str, prompt: str) -> None:
    try:
        user_id = update.message.from_user.id

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Переделать", callback_data="redo")]])

        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке текста: {e}")
        await update.message.reply_text("⚠️ Ошибка при отправке текста.")


# Redo generation
async def redo_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()
    if user_id not in user_data or "model" not in user_data[user_id] or "prompt" not in user_data[user_id]:
        await query.edit_message_text("⚠️ Нет данных для повторной генерации. Попробуйте сначала.")
        return

    prompt = user_data[user_id]["prompt"]
    model = user_data[user_id]["model"]

    await query.edit_message_text("⏳ Повторная генерация. Подождите немного...")
    try:
        if model in IMAGE_MODELS:
            content = generate_image(model, prompt)
            if content:
                await send_image(query, content, prompt)
            else:
                await query.edit_message_text("❌ Ошибка при повторной генерации изображения.")
        elif model in TEXT_MODELS:
            content = generate_text(model, prompt)
            if content:
                await send_text(query, content, prompt)
            else:
                await query.edit_message_text("❌ Ошибка при повторной генерации текста.")
    except Exception as e:
        logger.error(f"Ошибка при повторной генерации: {e}")
        await query.edit_message_text("⚠️ Ошибка при повторной генерации. Попробуйте позже.")


# Пинг-запросы для предотвращения отключения бота
async def send_ping(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Используем имя канала для пинга
        await context.bot.send_chat_action(chat_id=PING_CHANNEL_ID, action="typing")
        logger.info("Пинг отправлен.")
    except Exception as e:
        logger.error(f"Ошибка при отправке пинга: {e}")


# Обработчик запросов для вебхука
async def handle_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await app.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")

# Настройка вебхука
async def setup_webhook(app: Application, webhook_url: str) -> None:
    try:
        await app.bot.set_webhook(url=webhook_url)
        logger.info(f"Вебхук установлен на {webhook_url}")
    except Exception as e:
        logger.error(f"Ошибка при установке вебхука: {e}")


# Main bot function
if __name__ == "__main__":
    # Создание Flask приложения с новым именем
    flask_app = Flask(__name__)

    @flask_app.route("/", methods=["POST", "HEAD", "GET"])  # Добавляем поддержку методов HEAD и GET
    def index():
        if request.method == "POST":
            json_data = request.get_json(force=True)
            update = Update.de_json(json_data, app.bot)  # Используйте app.bot для обработки обновлений
            asyncio.run(handle_webhook(update, app))  # Передайте app в качестве контекста
            return jsonify({"status": "ok"})
        elif request.method == "HEAD":
            # Ответ на метод HEAD
            return "", 200  # Возвращаем пустой ответ с кодом 200
        elif request.method == "GET":
            # Ответ на метод GET
            return jsonify({"status": "Service is running"}), 200  # Возвращаем JSON с сообщением

    # Создание Telegram Bot приложения
    app = Application.builder().token(API_TOKEN).request(httpx_request).build()

    # Инициализация приложения
    asyncio.create_task(app.initialize())

    # Добавление обработчиков команд и колбэков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("generate_image", generate_image_command))
    app.add_handler(CommandHandler("generate_text", generate_text_command))
    app.add_handler(CallbackQueryHandler(select_model))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_description))
    app.add_handler(CallbackQueryHandler(redo_generation, pattern="^redo$"))

    # Настройка вебхука
    WEBHOOK_URL = "https://all-ai-mdjo.onrender.com"  # Замените на ваш реальный URL Render

    # Запуск Flask в отдельном потоке
    def run_flask():
        flask_app.run(host="0.0.0.0", port=5000)  # Используйте flask_app для запуска Flask

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Настройка вебхука асинхронно
    asyncio.create_task(setup_webhook(app, WEBHOOK_URL))

    logger.info("Бот запущен с вебхуком...")
