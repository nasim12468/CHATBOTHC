from flask import Flask, request
import requests
import os
import google.generativeai as genai

app = Flask(__name__)

# Загрузка переменных среды
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Выводим токены (обрезанные) в консоль
print("✅ VERIFY_TOKEN (first 10):", VERIFY_TOKEN[:10] if VERIFY_TOKEN else "Not found")
print("✅ PAGE_ACCESS_TOKEN (first 10):", PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else "Not found")
print("✅ GEMINI_API_KEY (first 10):", GEMINI_API_KEY[:10] if GEMINI_API_KEY else "Not found")

# Проверка наличия токенов
if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY:
    print("❌ Ошибка: Одна или несколько переменных среды не установлены!")
    exit(1)

# Инициализация Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

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
    print("🌐 [VERIFY] mode:", mode, "| token:", token)

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Вебхук подтверждён")
        return challenge, 200
    print("❌ Неверный verify token")
    return "Verification failed", 403

# Обработка сообщений (POST)
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 [WEBHOOK] Получены данные:", data)

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event["sender"]["id"]
            if "message" in messaging_event and "text" in messaging_event["message"]:
                user_msg = messaging_event["message"]["text"]
                print(f"👤 Сообщение от пользователя ({sender_id}): {user_msg}")

                reply = ask_gemini(user_msg)
                print("🤖 Ответ Gemini:", reply)

                send_message(sender_id, reply)
            else:
                print("⚠️ Не текстовое сообщение или отсутствует поле message")
    return "ok", 200

# Генерация ответа от Gemini
def ask_gemini(question):
    try:
        response = model.generate_content(SYSTEM_PROMPT + f"\nSavol: {question}\nJavob:")
        return response.text.strip()
    except Exception as e:
        print("❌ Ошибка при генерации ответа от Gemini:", e)
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."

# Отправка ответа пользователю в Instagram
def send_message(recipient_id, message_text):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    try:
        r = requests.post("https://graph.facebook.com/v18.0/me/messages", params=params, headers=headers, json=data)
        print(f"📤 Ответ отправлен пользователю ({recipient_id}): {message_text}")
        print("📡 Ответ сервера Meta:", r.status_code, r.text)
    except Exception as e:
        print("❌ Ошибка при отправке сообщения:", e)

# Запуск Flask-сервера
if __name__ == "__main__":
    print("🚀 Бот запущен. Ожидание запросов...")
    app.run(debug=True, host="0.0.0.0", port=5000)
