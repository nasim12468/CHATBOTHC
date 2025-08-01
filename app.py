from flask import Flask, request
import requests
import os
import google.generativeai as genai
import logging
import re # Regular expressions for phone number detection
import time # Vaqtni eslab qolish uchun
import json # __firebase_config ni yuklash uchun
import firebase_admin # Firestore uchun
from firebase_admin import credentials, firestore

# Log configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Load environment variables
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Print tokens (truncated) to console for debugging
logging.info(f"✅ VERIFY_TOKEN (first 10): {VERIFY_TOKEN[:10] if VERIFY_TOKEN else 'Not found'}")
logging.info(f"✅ PAGE_ACCESS_TOKEN (first 10): {PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else 'Not found'}")
logging.info(f"✅ GEMINI_API_KEY (first 10): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'Not found'}")
logging.info(f"✅ TELEGRAM_BOT_TOKEN (first 10): {TELEGRAM_BOT_TOKEN[:10] if TELEGRAM_BOT_TOKEN else 'Not found'}")
logging.info(f"✅ TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID if TELEGRAM_CHAT_ID else 'Not found'}")

# Check for missing tokens
if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("❌ Xato: Bir yoki bir nechta muhit o'zgaruvchilari o'rnatilmagan! Bot to'liq ishlay olmaydi.")

# Initialize Gemini
model = None
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        logging.info("✅ Gemini API 'gemini-1.5-flash' modeli bilan muvaffaqiyatli ishga tushirildi.")
    else:
        logging.warning("⚠️ GEMINI_API_KEY o'rnatilmagan. Gemini modeli ishlamaydi.")
except Exception as e:
    logging.error(f"❌ Gemini API'ni ishga tushirishda xato: {e}", exc_info=True)

# Initialize Firebase and Firestore
db = None
try:
    firebase_config_str = os.getenv("__firebase_config")
    if firebase_config_str:
        firebase_config = json.loads(firebase_config_str)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={'projectId': firebase_config.get('projectId')})
        db = firestore.client()
        logging.info("✅ Firestore muvaffaqiyatli ishga tushirildi.")
    else:
        logging.warning("⚠️ __firebase_config topilmadi. Firestore mavjud bo'lmaydi.")
except Exception as e:
    logging.error(f"❌ Firestore'ni ishga tushirishda xato: {e}", exc_info=True)


# NEW: Set to store processed message IDs
processed_message_ids = set()
# NEW: Dictionary to store the last greeting time for users
user_last_greeting_time = {}
# NEW: List to cache FAQs in memory
cached_faqs = []

# NEW: Function to load FAQs from Firestore
def load_faqs_from_firestore():
    global cached_faqs
    if not db:
        logging.warning("⚠️ Firestore ishga tushirilmagan, FAQ'larni yuklab bo'lmaydi.")
        return

    try:
        app_id = os.getenv("__app_id", "default-app-id")
        faqs_ref = db.collection(f"artifacts/{app_id}/public/data/faqs")
        docs = faqs_ref.stream()
        temp_faqs = []
        for doc in docs:
            faq_data = doc.to_dict()
            if "question_keywords" in faq_data and isinstance(faq_data["question_keywords"], list):
                faq_data["question_keywords"] = [k.lower() for k in faq_data["question_keywords"]]
            temp_faqs.append(faq_data)
        cached_faqs = temp_faqs
        logging.info(f"✅ Firestore'dan {len(cached_faqs)} ta FAQ yuklandi.")
    except Exception as e:
        logging.error(f"❌ FAQ'larni Firestore'dan yuklashda xato: {e}", exc_info=True)

# Load FAQs when the bot starts
if db:
    load_faqs_from_firestore()


# NEW: Function to add initial FAQs to Firestore (for one-time use)
def add_initial_faqs():
    if not db:
        logging.error("❌ Firestore ishga tushirilmagan, FAQ'larni qo'shib bo'lmaydi.")
        return

    app_id = os.getenv("__app_id", "default-app-id")
    faqs_ref = db.collection(f"artifacts/{app_id}/public/data/faqs")

    initial_faqs_data = [
        {
            "question_keywords": ["xizmatlar", "qanday xizmatlar", "nima qilasiz", "xizmat turlari", "services", "what services", "what do you do"],
            "answer_text_uz": "Bizning asosiy xizmatlarimiz: Hijoma, Massaj, Girodoterapiya (zuluk bilan davolash), Manual terapiya va Kosmetologiya. Batafsil ma'lumot uchun biz bilan bog'laning.",
            "answer_text_en": "Our main services include: Hijama, Massage, Hirudotherapy (leech therapy), Manual Therapy, and Cosmetology. Please contact us for more details."
        },
        {
            "question_keywords": ["kurslar", "o'qimoqchiman", "o'qish", "o'rgatish", "o'rgating", "kurs", "courses", "study", "learn", "teach"],
            "answer_text_uz": "Bizda Hamshiralik (3 oy), Massaj (2 oy), Hijoma (1 oy), Girodoterapiya (15 kun) kurslari mavjud. Kurs yakunida Misr sertifikati beriladi. Narxlar va batafsil ma'lumot uchun telefon raqamingizni qoldiring, biz siz bilan bog'lanamiz.",
            "answer_text_en": "We offer Nursing (3 months), Massage (2 months), Hijama (1 month), and Hirudotherapy (15 days) courses. An Egyptian Certificate is provided upon completion. For prices and details, please leave your phone number, and we will contact you."
        },
        {
            "question_keywords": ["manzil", "adres", "qayerdasiz", "joylashuv", "address", "location", "where are you"],
            "answer_text_uz": "Bizning manzilimiz: Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.",
            "answer_text_en": "Our address is: Tashkent city, Shaykhontokhur district, Samarqand Darvoza, 149A."
        },
        {
            "question_keywords": ["telefon", "raqam", "aloqa", "bog'lanish", "phone", "number", "contact"],
            "answer_text_uz": "Biz bilan bog'lanish uchun telefon raqami: +998 90 988 03 03. Telegram orqali ham @hijamacentre1 manziliga yozishingiz mumkin.",
            "answer_text_en": "Our contact phone number is: +998 90 988 03 03. You can also reach us on Telegram at @hijamacentre1."
        },
        {
            "question_keywords": ["narx", "qancha turadi", "pul", "to'lov", "batafsil ma'lumot", "price", "cost", "how much", "payment", "detailed information"],
            "answer_text_uz": "Narxlar xizmat turiga qarab farq qiladi. Batafsil ma'lumot olish uchun iltimos, biz bilan telefon orqali bog'laning yoki telefon raqamingizni yozib qoldiring, biz siz bilan bog'lanamiz.",
            "answer_text_en": "Prices vary depending on the service. For detailed information, please contact us by phone or leave your phone number, and we will contact you."
        }
    ]

    try:
        for faq in initial_faqs_data:
            doc_id = faq["question_keywords"][0]
            faqs_ref.document(doc_id).set(faq)
            logging.info(f"✅ FAQ qo'shildi/yangilandi: {doc_id}")
        logging.info("✅ Barcha dastlabki FAQ'lar muvaffaqiyatli qo'shildi/yangilandi.")
    except Exception as e:
        logging.error(f"❌ Dastlabki FAQ'larni qo'shishda xato: {e}", exc_info=True)


# System prompt (combined for Uzbek and English)
SYSTEM_PROMPT = """
You are the official artificial intelligence operator of "Hijama Centre". We specialize in treating all diseases with natural methods.
Always respond to clients politely, respectfully, clearly, and helpfully. You are a sales bot, so every word you say should attract interest and retain the client.
You MUST automatically detect the language of the user's message (Uzbek or English) and respond in that same language. Do not mix languages.

**Response Rules:**
1.  Only talk about our services, courses, address, and contact information, briefly and clearly.
2.  **If asked about prices or detailed information, do not answer directly.** Instead, reply: "To get detailed information about prices, please contact us by phone" or "To get detailed information, leave your phone number, and we will contact you shortly."
3.  **Do not provide any information from the internet.** All information must be only from this prompt.
4.  **Do not give medical advice about diseases, their symptoms, or treatment methods.** Provide only general information about the services and courses offered at our center.
5.  Do not get distracted by other topics. If other questions are asked, politely ask for a phone number and inform them that our operators will contact them shortly. Be polite in every word.
6.  **Only answer questions. Do not add "Yes" or similar affirmative or redundant words from yourself. Provide only the requested information.**
7.  **If the user refers with words like "want to study", "courses", "study", "teach", "course" (in Uzbek or English), first provide full information about our training courses, then suggest contacting for prices.**
8.  **Make your responses as short and concise as possible. Do not use unnecessary sentences. Try to respond within 100-150 tokens.**

Our main services:
-   **Hijama (cupping therapy):** An ancient natural method of body cleansing and treating various diseases. It is considered a Sunnah act in Islam.
-   **Massage:** Various types of massage (therapeutic, relaxing, sports massage) to relieve muscle pain and improve blood circulation.
-   **Hirudotherapy (leech therapy):** The use of medicinal leeches to normalize blood pressure, thin blood, and reduce inflammation.
-   **Manual therapy:** This is a hands-on treatment method where a specialist directly affects painful areas of the body or bones, muscles, joints with their hands.
-   **Kosmetologiya / Cosmetology:** Face and body skin care using natural products and methods.
-   **Boshqa tabiiy usullar / Other natural methods:** Other natural treatment methods tailored to the individual needs of each client.

We not only provide services, but also train people in these services; we have courses.
Our training courses:
-   **Hamshiralik kursi / Nursing Course:** Duration 3 months.
-   **Massaj kursi / Massage Course:** Duration 2 months.
-   **Hijoma kursi / Hijama Course:** Duration 1 month.
-   **Girodoterapiya (zuluk) kursi / Hirudotherapy (Leech) Course:** Duration 15 days.
Upon completion of the course, participants receive an **Egyptian Certificate**.

Our address:
-   **Manzil / Address:** Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.

Contact us:
-   **Telefon / Phone:** +998 90 988 03 03
-   **Telegram:** @hijamacentre1
"""

# Webhook verification (GET)
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    logging.info(f"🌐 [VERIFY] So'rov qabul qilindi. Rejim: {mode} | Token: {token[:10] if token else 'None'}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logging.info("✅ Webhook tasdiqlandi. Challenge yuborilmoqda.")
        return challenge, 200
    logging.warning(f"❌ Verify token yoki rejim noto'g'ri. '{VERIFY_TOKEN}' kutilgan edi, '{token}' qabul qilindi.")
    return "Verification failed", 403

# Phone number detection regex
PHONE_NUMBER_REGEX = re.compile(r'\+?\d{9,15}')

# Message processing (POST)
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"📩 [WEBHOOK] Qabul qilingan ma'lumotlar: {data}")

    if not data:
        logging.warning("⚠️ Bo'sh POST so'rovi qabul qilindi.")
        return "ok", 200

    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                message_id = messaging_event.get("message", {}).get("mid")
                if message_id and message_id in processed_message_ids:
                    logging.info(f"♻️ Xabar {message_id} allaqachon qayta ishlangan. O'tkazib yuborilmoqda.")
                    return "ok", 200

                if message_id:
                    processed_message_ids.add(message_id)

                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event and "text" in messaging_event["message"]:
                    user_msg = messaging_event["message"]["text"]
                    logging.info(f"👤 Foydalanuvchidan xabar ({sender_id}): {user_msg}")
                    user_msg_lower = user_msg.lower()

                    found_phone_numbers = PHONE_NUMBER_REGEX.findall(user_msg)
                    if found_phone_numbers:
                        phone_number = found_phone_numbers[0]
                        logging.info(f"📞 Telefon raqami aniqlandi: {phone_number}")
                        send_to_telegram_bot(sender_id, phone_number, user_msg)
                        reply = "Raqamingiz qabul qilindi. Tez orada siz bilan bog'lanamiz. E'tiboringiz uchun rahmat!"
                        send_message(sender_id, reply)
                    else:
                        current_time = time.time()
                        if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower or "hello" in user_msg_lower:
                            if sender_id not in user_last_greeting_time or \
                               (current_time - user_last_greeting_time[sender_id]) > 24 * 3600:
                                reply = "Va alaykum assalam! Xush kelibsiz! Qanday yordam bera olaman?" if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower else "Hello! Welcome! How can I help you?"
                                user_last_greeting_time[sender_id] = current_time
                                send_message(sender_id, reply)
                                return "ok", 200
                            else:
                                reply = "Qanday yordam bera olaman?" if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower else "How can I help you?"
                                send_message(sender_id, reply)
                                return "ok", 200
                        
                        # NEW: Check FAQ cache first for keywords
                        matched_faq_answer = None
                        detected_lang = 'uz' # Default language is Uzbek
                        
                        # Simple language detection for FAQ matching
                        if any(keyword in user_msg_lower for keyword in ["address", "location", "services", "contact", "phone", "price", "course"]):
                            detected_lang = 'en'

                        for faq in cached_faqs:
                            for keyword in faq.get("question_keywords", []):
                                if keyword in user_msg_lower:
                                    if detected_lang == 'en':
                                        matched_faq_answer = faq.get("answer_text_en")
                                    else:
                                        matched_faq_answer = faq.get("answer_text_uz")
                                    break
                            if matched_faq_answer:
                                break
                        
                        if matched_faq_answer:
                            logging.info(f"📚 FAQ'dan javob topildi: {matched_faq_answer[:50]}...")
                            send_message(sender_id, matched_faq_answer)
                            return "ok", 200
                        
                        # Main Gemini response (only if no FAQ match)
                        if model:
                            reply = ask_gemini(user_msg, SYSTEM_PROMPT)
                            logging.info(f"🤖 Gemini javobi: {reply}")
                        else:
                            reply = "Kechirasiz, AI xizmati hozircha mavjud emas. Iltimos, keyinroq urinib ko'ring."
                            logging.error("❌ Gemini modeli ishga tushirilmagan. Javob berish imkonsiz.")

                        send_message(sender_id, reply)
                elif "postback" in messaging_event:
                    logging.info(f"💬 Postback hodisasi qabul qilindi {sender_id}: {messaging_event['postback']}")
                else:
                    logging.info(f"⚠️ Matnli xabar emas yoki 'message' maydoni mavjud emas {sender_id}: {messaging_event}")
    else:
        logging.warning(f"⚠️ Instagramdan tashqari so'rov qabul qilindi: {data.get('object')}")

    return "ok", 200

# Generate response from Gemini
def ask_gemini(question, system_prompt):
    if not model:
        logging.error("❌ Gemini modeli ishga tushirilmagan. Javob berish imkonsiz.")
        return "Kechirasiz, AI xizmati hozirda ishlamayapti."
    try:
        response = model.generate_content(
            system_prompt + f"\nUser's message: {question}\nResponse:",
            generation_config={"max_output_tokens": 150}
        )
        reply_text = response.text.strip()
        return reply_text
    except Exception as e:
        logging.error(f"❌ Gemini javobini yaratishda xato: {e}", exc_info=True)
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."

# Send response to the user on Instagram
def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    if not PAGE_ACCESS_TOKEN:
        logging.error("❌ PAGE_ACCESS_TOKEN o'rnatilmagan. Xabar yuborish imkonsiz.")
        return

    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        logging.info(f"📤 Javob foydalanuvchiga yuborildi ({recipient_id}): {message_text[:50]}...")
        logging.info(f"📡 Meta serveridan javob: {r.status_code} - {r.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Meta API'ga xabar yuborishda xatolik: {e}", exc_info=True)
        if r is not None:
            logging.error(f"❌ Meta javobi (xato): {r.status_code} - {r.text}")
    except Exception as e:
        logging.error(f"❌ Xabar yuborishda noma'lum xato: {e}", exc_info=True)

# Send phone number to Telegram bot
def send_to_telegram_bot(instagram_sender_id, phone_number, original_message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ TELEGRAM_BOT_TOKEN yoki TELEGRAM_CHAT_ID o'rnatilmagan. Telefon raqamini Telegramga yuborish imkonsiz.")
        return

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text_message = (
        f"Yangi telefon raqami qabul qilindi!\n"
        f"Instagram foydalanuvchisi ID: {instagram_sender_id}\n"
        f"Telefon raqami: {phone_number}\n"
        f"Asl xabar: {original_message}"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text_message
    }
    headers = {"Content-Type": "application/json"}

    try:
        r = requests.post(telegram_url, headers=headers, json=payload)
        r.raise_for_status()
        logging.info(f"✅ Telefon raqami Telegramga yuborildi: {phone_number}")
        logging.info(f"📡 Telegram serveridan javob: {r.status_code} - {r.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Telefon raqamini Telegramga yuborishda xato: {e}", exc_info=True)
        if r is not None:
            logging.error(f"❌ Telegram javobi (xato): {r.status_code} - {r.text}")
    except Exception as e:
        logging.error(f"❌ Telefon raqamini Telegramga yuborishda noma'lum xato: {e}", exc_info=True)

# Start the server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Bot ishga tushdi. {port} portida so'rovlar kutilmoqda...")
    app.run(host="0.0.0.0", port=port, debug=True)
