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

logging.info(f"✅ VERIFY_TOKEN (first 10): {VERIFY_TOKEN[:10] if VERIFY_TOKEN else 'Not found'}")
logging.info(f"✅ PAGE_ACCESS_TOKEN (first 10): {PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else 'Not found'}")
logging.info(f"✅ GEMINI_API_KEY (first 10): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'Not found'}")

if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY:
    logging.error("❌ VERIFY_TOKEN, PAGE_ACCESS_TOKEN yoki GEMINI_API_KEY yo‘q! Barcha xizmatlar to‘liq ishlamaydi.")

# Инициализация Gemini (v1)
model = None
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name="models/gemini-pro")  # ОБНОВЛЕНИЕ ЗДЕСЬ
        logging.info("✅ Gemini model muvaffaqiyatli yuklandi.")
except Exception as e:
    logging.error(f"❌ Gemini modelni yuklashda xatolik: {e}", exc_info=True)

# Prompt - sistemani tanituvchi
SYSTEM_PROMPT = """
Siz Hijama Centre markazining sun'iy intellekt yordamchisiz.
Siz har doim mijozlarga muloyim, hurmatli va foydali tarzda javob berishingiz kerak.
Faqat o'zbek tilida yozing.
Siz Hijama Centre markazining rasmiy operatori bo‘lib, mijozlar savollariga yordam berasiz.
Quyidagilarni har doim hisobga oling:
Xizmatlar: hijama, bankalar qo‘yish, massaj, qon yuritish va boshqa tabiiy usullar.
Manzil: Toshkent, Yakkasaroy tumani, Ubaydullaev ko‘chasi 16-uy.
Telefon: +998 93 161 27 29
Telegram: @HijamaCentreBot
"""

# Верификация Meta webhook
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logging.info("✅ Webhook tasdiqlandi.")
        return challenge, 200
    else:
        logging.warning("❌ Noto‘g‘ri VERIFY_TOKEN.")
        return "Verification failed", 403

# Обработка сообщений
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"📩 [WEBHOOK] Kiruvchi so‘rov: {data}")

    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event and "text" in messaging_event["message"]:
                    user_msg = messaging_event["message"]["text"]
                    logging.info(f"👤 Foydalanuvchi ({sender_id}): {user_msg}")

                    if model:
                        reply = ask_gemini(user_msg)
                    else:
                        reply = "Kechirasiz, sun’iy intellekt hozirda ishlamayapti."

                    send_message(sender_id, reply)
    return "ok", 200

# Chat yordamchining javobi
def ask_gemini(question):
    try:
        full_prompt = f"{SYSTEM_PROMPT}\nSavol: {question}\nJavob:"
        response = model.generate_content(full_prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"❌ Gemini javobida xatolik: {e}", exc_info=True)
        return "Kechirasiz, AI javob bera olmadi. Iltimos, keyinroq urinib ko‘ring."

# Instagram'ga javob yuborish
def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        logging.info(f"📤 Javob yuborildi ({recipient_id}): {message_text[:50]}")
    except Exception as e:
        logging.error(f"❌ Instagram API xatosi: {e}", exc_info=True)

# Run server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Bot ishga tushdi. Port: {port}")
    app.run(host="0.0.0.0", port=port)
