from flask import Flask, request
import requests
import os
import google.generativeai as genai
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Загрузка переменных среды
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Выводим токены (обрезанные) в консоль для отладки
logging.info(f"✅ VERIFY_TOKEN (first 10): {VERIFY_TOKEN[:10] if VERIFY_TOKEN else 'Not found'}")
logging.info(f"✅ PAGE_ACCESS_TOKEN (first 10): {PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else 'Not found'}")
logging.info(f"✅ GEMINI_API_KEY (first 10): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'Not found'}")

# Проверка наличия токенов
if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY:
    logging.error("❌ Ошибка: Одна или несколько переменных среды не установлены! Проверьте .env файл или настройки окружения.")
    # В реальном приложении можно не выходить, а возвращать 500 ошибку или иметь заглушку
    # exit(1) # Закомментировано для возможности запуска даже без всех токенов, но функционал будет ограничен

# Инициализация Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-pro")
    logging.info("✅ Gemini API успешно инициализирован.")
except Exception as e:
    logging.error(f"❌ Ошибка инициализации Gemini API: {e}")
    model = None # Устанавливаем None, чтобы избежать ошибок при попытке использования

# Системный промпт
SYSTEM_PROMPT = """
Siz Hijama markazining sun'iy intellekt yordamchisiz.
Siz har doim mijozlarga muloyim, hurmatli va foydali tarzda javob berishingiz kerak.
Savollarga qisqa, tushunarli va do'stona ohangda javob bering.
Faqat o'zbek tilida yozing.
"""

# Проверка Meta App (GET)
@app.route("/", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    logging.info(f"🌐 [VERIFY] Получен запрос на верификацию. mode: {mode} | token: {token[:10] if token else 'None'}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logging.info("✅ Вебхук подтверждён. Отправляем challenge.")
        return challenge, 200
    logging.warning(f"❌ Неверный verify token или режим. Ожидался '{VERIFY_TOKEN}', получен '{token}'.")
    return "Verification failed", 403

# Обработка сообщений (POST)
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"📩 [WEBHOOK] Получены данные: {data}")

    if not data:
        logging.warning("⚠️ Получены пустые данные POST-запроса.")
        return "ok", 200

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event["sender"]["id"]
            if "message" in messaging_event and "text" in messaging_event["message"]:
                user_msg = messaging_event["message"]["text"]
                logging.info(f"👤 Сообщение от пользователя ({sender_id}): {user_msg}")

                if model: # Проверяем, что модель Gemini инициализирована
                    reply = ask_gemini(user_msg)
                    logging.info(f"🤖 Ответ Gemini: {reply}")
                else:
                    reply = "Kechirasiz, AI xizmati hozircha mavjud emas. Iltimos, keyinroq urinib ko'ring."
                    logging.error("❌ Gemini модель не инициализирована. Невозможно сгенерировать ответ.")

                send_message(sender_id, reply)
            elif "postback" in messaging_event:
                # Обработка postback-событий (например, нажатия кнопок)
                logging.info(f"💬 Получено postback-событие от {sender_id}: {messaging_event['postback']}")
                # Здесь можно добавить логику для обработки postback
            else:
                logging.info(f"⚠️ Получено не текстовое сообщение или отсутствует поле 'message' от {sender_id}: {messaging_event}")
    return "ok", 200

# Генерация ответа от Gemini
def ask_gemini(question):
    if not model:
        return "Kechirasiz, AI xizmati hozirda ishlamayapti."
    try:
        # Важно: для чат-бота лучше использовать chat.send_message, чтобы сохранять контекст
        # Но для простого ответа на каждый вопрос, generate_content тоже подойдет.
        # Если вы хотите сохранять историю диалога, вам потребуется хранить ее для каждого пользователя.
        response = model.generate_content(SYSTEM_PROMPT + f"\nSavol: {question}\nJavob:")
        return response.text.strip()
    except Exception as e:
        logging.error(f"❌ Ошибка при генерации ответа от Gemini: {e}", exc_info=True) # exc_info=True для полного traceback
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."

# Отправка ответа пользователю в Instagram
def send_message(recipient_id, message_text):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    if not PAGE_ACCESS_TOKEN:
        logging.error("❌ PAGE_ACCESS_TOKEN не установлен. Невозможно отправить сообщение.")
        return

    try:
        r = requests.post("[https://graph.facebook.com/v18.0/me/messages](https://graph.facebook.com/v18.0/me/messages)", params=params, headers=headers, json=data)
        r.raise_for_status() # Вызывает исключение для HTTP ошибок (4xx или 5xx)
        logging.info(f"📤 Ответ отправлен пользователю ({recipient_id}): {message_text[:50]}...") # Обрезаем для лога
        logging.info(f"📡 Ответ сервера Meta: {r.status_code} - {r.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ошибка при отправке сообщения Meta API: {e}", exc_info=True)
        if r is not None:
            logging.error(f"❌ Ответ Meta (ошибка): {r.status_code} - {r.text}")
    except Exception as e:
        logging.error(f"❌ Неизвестная ошибка при отправке сообщения: {e}", exc_info=True)

# Запуск Flask-сервера
if __name__ == "__main__":
    logging.info("🚀 Бот запущен. Ожидание запросов...")
    # debug=True не рекомендуется для продакшена, но полезен для локальной отладки
    app.run(debug=True, host="0.0.0.0", port=5000)
