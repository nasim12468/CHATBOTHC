from flask import Flask, request
import requests
import os
import google.generativeai as genai
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Загрузка переменных среды
# Убедитесь, что эти переменные установлены в вашем окружении (например, через .env файл или настройки хостинга)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Выводим токены (обрезанные) в консоль для отладки
logging.info(f"✅ VERIFY_TOKEN (first 10): {VERIFY_TOKEN[:10] if VERIFY_TOKEN else 'Not found'}")
logging.info(f"✅ PAGE_ACCESS_TOKEN (first 10): {PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else 'Not found'}")
logging.info(f"✅ GEMINI_API_KEY (first 10): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'Not found'}")

# Проверка наличия токенов
if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY:
    logging.error("❌ Ошибка: Одна или несколько переменных среды не установлены! Бот не сможет полноценно функционировать.")
    # В реальном приложении можно не выходить, а возвращать 500 ошибку или иметь заглушку
    # exit(1) # Закомментировано для возможности запуска даже без всех токенов, но функционал будет ограничен

# Инициализация Gemini
model = None # Инициализируем модель как None по умолчанию
try:
    if GEMINI_API_KEY: # Проверяем, что ключ API существует
        genai.configure(api_key=GEMINI_API_KEY)
        # Используем 'gemini-1.5-flash' вместо 'gemini-pro'
        model = genai.GenerativeModel("gemini-1.5-flash")
        logging.info("✅ Gemini API успешно инициализирован с моделью 'gemini-1.5-flash'.")
    else:
        logging.warning("⚠️ GEMINI_API_KEY не установлен. Gemini модель не будет работать.")
except Exception as e:
    logging.error(f"❌ Ошибка инициализации Gemini API: {e}", exc_info=True) # Добавляем exc_info для полного traceback

# Системный промпт
# ОБНОВЛЕНО: Полный и подробный системный промпт на узбекском языке
SYSTEM_PROMPT = """
Siz "Hijama Centre" kompaniyasining rasmiy sun'iy intellekt operatorisiz. Biz barcha kasalliklarni tabiiy usullar bilan davolashga ixtisoslashganmiz.
Mijozlarga har doim muloyim, hurmatli, tushunarli va foydali tarzda javob bering.
Savollarga qisqa, aniq va do'stona ohangda javob bering. Faqat o'zbek tilida yozing.

Bizning asosiy xizmatlarimiz:
-   **Hijoma (qon oldirish):** Tanani tozalash va turli kasalliklarni davolashning qadimiy usuli.
-   **Massaj:** Turli xil massaj turlari (davolovchi, tinchlantiruvchi, sport massaji) mushaklardagi og'riqlarni yengillashtirish va qon aylanishini yaxshilash uchun.
-   **Girodoterapiya (zuluk bilan davolash):** Qon bosimini normallashtirish, qonni suyultirish va yallig'lanishni kamaytirish uchun tibbiy zuluklardan foydalanish.
-   **Kosmetologiya:** Tabiiy mahsulotlar va usullar yordamida yuz va tana terisini parvarish qilish.
-   **Boshqa tabiiy usullar:** Har bir mijozning individual ehtiyojlariga moslashtirilgan boshqa tabiiy davolash usullari.

Bizning manzilimiz:
-   **Manzil:** Toshkent shahri, Yakkasaroy tumani, Ubaydullayev ko'chasi, 16-uy.

Biz bilan bog'lanish:
-   **Telefon:** +998 93 161 27 29
-   **Telegram:** @HijamaCentreBot

Foydalanuvchi qanday savol bermasin, yuqoridagi ma'lumotlarga asoslanib, ularga yordam bering. Agar savol tushunarli bo'lmasa, hurmat bilan aniqlashtiruvchi savol bering.
"""


# Верификация (GET)
@app.route("/webhook", methods=["GET"]) # ИЗМЕНЕНО: Теперь используется '/webhook' для GET запросов
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
@app.route("/webhook", methods=["POST"]) # Маршрут '/webhook' для входящих сообщений
def webhook():
    data = request.get_json()
    logging.info(f"📩 [WEBHOOK] Получены данные: {data}")

    if not data:
        logging.warning("⚠️ Получены пустые данные POST-запроса.")
        return "ok", 200

    # Проверяем, что это сообщение Instagram
    if data.get("object") == "instagram":
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
                    logging.info(f"💬 Получено postback-событие от {sender_id}: {messaging_event['postback']}")
                else:
                    logging.info(f"⚠️ Получено не текстовое сообщение или отсутствует поле 'message' от {sender_id}: {messaging_event}")
    else:
        logging.warning(f"⚠️ Получен запрос не от Instagram: {data.get('object')}")

    return "ok", 200

# Генерация ответа от Gemini
def ask_gemini(question):
    if not model:
        logging.error("❌ Gemini модель не инициализирована. Невозможно сгенерировать ответ.")
        return "Kechirasiz, AI xizmati hozirda ishlamayapti."
    try:
        # Используем SYSTEM_PROMPT как часть запроса, это более типично для Gemini API
        response = model.generate_content(SYSTEM_PROMPT + f"\nSavol: {question}\nJavob:")
        return response.text.strip()
    except Exception as e:
        logging.error(f"❌ Ошибка при генерации ответа от Gemini: {e}", exc_info=True) # Добавляем exc_info=True для полного traceback
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."

# Отправка ответа пользователю в Instagram
def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    if not PAGE_ACCESS_TOKEN:
        logging.error("❌ PAGE_ACCESS_TOKEN не установлен. Невозможно отправить сообщение.")
        return

    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status() # Вызывает исключение для HTTP ошибок (4xx или 5xx)
        logging.info(f"📤 Ответ отправлен пользователю ({recipient_id}): {message_text[:50]}...") # Обрезаем для лога
        logging.info(f"📡 Ответ сервера Meta: {r.status_code} - {r.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ошибка при отправке сообщения Meta API: {e}", exc_info=True)
        if r is not None:
            logging.error(f"❌ Ответ Meta (ошибка): {r.status_code} - {r.text}")
    except Exception as e:
        logging.error(f"❌ Неизвестная ошибка при отправке сообщения: {e}", exc_info=True)

# Запуск сервера
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Бот запущен. Ожидание запросов на порту {port}...")
    app.run(host="0.0.0.0", port=port, debug=True) # debug=True полезен для локальной отладки
