from flask import Flask, request
import os
import requests
import google.generativeai as genai

# Настройка Flask
app = Flask(__name__)

# Переменные из окружения
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_verify_token")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "your_page_access_token")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key")

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# Системный промпт (узбекский)
SYSTEM_PROMPT = """
Сиз Hijama Centre марказининг расмий оператори бўлиб, мижозлар саволларига ёрдам берасиз.
Қуйидагиларни ҳар доим ҳисобга олинг:
- Хизматлар: ҳижама, банкалар қўйиш, массаж, қон юритиш ва бошқа табиий усуллар.
- Манзил: Тошкент, Яккасарой тумани, Убайдуллаев кўчаси 16-уй.
- Телефон: +998 93 161 27 29
- Telegram: @HijamaCentreBot

Фойдаланувчи қандай савол бермасин, хушмуомала ва ёрдамчӣ бўлиб жавоб беринг. Агар савол тушунарсиз бўлса, хушмуомала ҳолда қайта сўранг.
"""

# Верификация (GET)
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Token noto‘g‘ri", 403

# Обработка сообщений (POST)
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for change in entry.get("messaging", []):
                sender_id = change["sender"]["id"]
                if "message" in change and "text" in change["message"]:
                    user_message = change["message"]["text"]
                    reply_text = ask_gemini(user_message)
                    send_message(sender_id, reply_text)
    return "OK", 200

# Отправка запроса к Gemini
def ask_gemini(user_input):
    try:
        response = model.generate_content([
            {"role": "system", "parts": [SYSTEM_PROMPT]},
            {"role": "user", "parts": [user_input]}
        ])
        return response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        return "Кечирасиз, ҳозирча жавоб бера олмадим."

# Отправка ответа обратно в Instagram
def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    response = requests.post(url, headers=headers, json=payload)
    print("Meta response:", response.text)

# Запуск сервера
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
