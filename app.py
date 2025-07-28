from flask import Flask, request
import os
import requests
from google.generativeai import GenerativeModel, configure
import logging

# === Настройки ===
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# === Настройка логгера ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Настройка Flask ===
app = Flask(__name__)

# === Настройка Gemini ===
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY не найден!")
else:
    configure(api_key=GEMINI_API_KEY)
    gemini_model = GenerativeModel("gemini-pro")
    logger.info("✅ Модель Gemini инициализирована.")

# === Webhook GET (подтверждение) ===
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Вебхук подтверждён. Отправляем challenge.")
        return challenge, 200
    else:
        logger.warning("❌ Неверный токен подтверждения!")
        return "Verification failed", 403

# === Webhook POST (получение сообщений) ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logger.info(f"📥 Получены данные: {data}")
    
    if "entry" in data:
        for entry in data["entry"]:
            messaging = entry.get("messaging")
            if messaging:
                for message_event in messaging:
                    sender_id = message_event["sender"]["id"]
                    if "message" in message_event and "text" in message_event["message"]:
                        user_message = message_event["message"]["text"]
                        logger.info(f"👤 Сообщение от пользователя ({sender_id}): {user_message}")
                        
                        # Генерация ответа через Gemini
                        if GEMINI_API_KEY:
                            try:
                                response = gemini_model.generate_content(user_message)
                                reply = response.text
                                logger.info(f"🤖 Ответ Gemini: {reply}")
                            except Exception as e:
                                reply = "Ошибка генерации ответа."
                                logger.error(f"⚠️ Ошибка Gemini: {e}")
                        else:
                            reply = "Gemini API Key не настроен."
                        
                        send_message(sender_id, reply)
    
    return "EVENT_RECEIVED", 200

# === Функция отправки ответа пользователю ===
def send_message(recipient_id, message_text):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    
    r = requests.post("https://graph.facebook.com/v18.0/me/messages",
                      params=params, headers=headers, json=data)
    logger.info(f"📡 Ответ сервера Meta: {r.status_code} - {r.text}")

# === Запуск локально (если нужно) ===
if __name__ == "__main__":
    app.run(debug=True)
