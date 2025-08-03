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
import hashlib # Kesh kalitini yaratish uchun

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


# Set to store processed message IDs
processed_message_ids = set()
# Dictionary to store the last greeting time for users
user_last_greeting_time = {}
# List to cache FAQs in memory
cached_faqs = []

# Function to load FAQs from Firestore
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

# Function to get a response from the Firestore cache
def get_from_cache(question):
    if not db:
        return None
    try:
        app_id = os.getenv("__app_id", "default-app-id")
        cache_ref = db.collection(f"artifacts/{app_id}/public/data/gemini_cache")
        # Savolning hash'ini yaratamiz
        question_hash = hashlib.sha256(question.encode('utf-8')).hexdigest()
        doc_ref = cache_ref.document(question_hash)
        doc = doc_ref.get()
        if doc.exists:
            logging.info("💾 Savol bazadan kesh orqali topildi.")
            return doc.to_dict().get("answer")
        return None
    except Exception as e:
        logging.error(f"❌ Keshdan ma'lumot olishda xato: {e}", exc_info=True)
        return None

# Function to save a response to the Firestore cache
def save_to_cache(question, answer):
    if not db:
        return
    try:
        app_id = os.getenv("__app_id", "default-app-id")
        cache_ref = db.collection(f"artifacts/{app_id}/public/data/gemini_cache")
        # Savolning hash'ini yaratamiz
        question_hash = hashlib.sha256(question.encode('utf-8')).hexdigest()
        doc_ref = cache_ref.document(question_hash)
        doc_ref.set({
            "question": question,
            "answer": answer,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        logging.info("💾 Yangi javob bazaga kesh sifatida saqlandi.")
    except Exception as e:
        logging.error(f"❌ Keshga ma'lumot saqlashda xato: {e}", exc_info=True)


# Function to add initial FAQs to Firestore (for one-time use)
def add_initial_faqs():
    if not db:
        logging.error("❌ Firestore ishga tushirilmagan, FAQ'larni qo'shib bo'lmaydi.")
        return

    app_id = os.getenv("__app_id", "default-app-id")
    faqs_ref = db.collection(f"artifacts/{app_id}/public/data/faqs")

    initial_faqs_data = [
        {
            "question_keywords": ["xizmatlar", "qanday", "nima", "qilasiz", "xizmat", "turlari", "services", "what", "do"],
            "answer_text_uz": "Biz Hijama Centre klinikasida sog'ligingiz va go'zalligingiz uchun tabiiy muolajalarni taklif etamiz. 🌸 Muolajalarimiz: Hijoma, Massaj, Manual terapiya, Girodoterapiya va Kosmetologiya. 😊 Batafsil ma'lumot uchun operatorlarimiz bilan bog'laning.",
            "answer_text_en": "At Hijama Centre, we offer natural treatments for your health and beauty. 🌸 Our services include: Hijama, Massage, Manual Therapy, Hirudotherapy, and Kosmetology. 😊 For more information, please contact our operators."
        },
        {
            "question_keywords": ["kurslar", "o'qimoqchiman", "o'qish", "o'rgatish", "o'rgating", "kurs", "courses", "study", "learn", "teach"],
            "answer_text_uz": "Bizda tabiiy tibbiyot sohasida kasb egallashni istaganlar uchun maxsus kurslar mavjud.👩‍🎓 Hamshiralik: 3 oy. Massaj: 2 oy. Hijoma: 1 oy. Girodoterapiya: 15 kun. Kursni muvaffaqiyatli yakunlaganlarga Misr sertifikati beriladi. 📜 Narxlar va boshqa tafsilotlar haqida ma'lumot olish uchun telefon raqamingizni qoldiring, biz siz bilan bog'lanamiz! 📞",
            "answer_text_en": "We have specialized courses for those who want to build a career in natural medicine. 👩‍🎓 Nursing: 3 months. Massage: 2 months. Hijama: 1 month. Hirudotherapy: 15 days. Upon successful completion, you will receive an Egyptian Certificate. 📜 For prices and other details, please leave your phone number, and we will contact you shortly! 📞"
        },
        {
            "question_keywords": ["manzil", "adres", "qayerdasiz", "joylashuv", "address", "location", "where", "ofis"],
            "answer_text_uz": "📍 Bizning manzilimiz: Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.",
            "answer_text_en": "📍 Our center is located at: Toshkent city, Shaykhontokhur district, Samarqand Darvoza, 149A."
        },
        {
            "question_keywords": ["telefon", "raqam", "aloqa", "bog'lanish", "phone", "number", "contact"],
            "answer_text_uz": "Biz bilan bog'lanish uchun: 📞 Telefon: +998 90 988 03 03. 💬 Telegram: @hijamacentre1",
            "answer_text_en": "You can reach us at: 📞 Phone: +998 90 988 03 03. 💬 Telegram: @hijamacentre1"
        },
        {
            "question_keywords": ["narx", "qancha", "turadi", "pul", "to'lov", "batafsil", "ma'lumot", "price", "cost", "how much", "payment", "detailed", "information"],
            "answer_text_uz": "Har bir xizmatimizning narxi individualdir. Narxlar haqida aniq ma'lumot olish uchun iltimos, telefon raqamingizni qoldiring. 📞",
            "answer_text_en": "The price for each of our services is individual. To get accurate information about prices, please leave your phone number. 📞"
        },
        {
            "question_keywords": ["bog'lanmadilar", "qo'ng'iroq", "qilmadingiz", "bog'lanmadingiz", "no one called", "didn't call", "you didn't contact"],
            "answer_text_uz": "Uzr, biz siz bilan tez orada bog'lanamiz. 🥺 Noqulayliklar uchun uzr so'raymiz.",
            "answer_text_en": "We apologize for the inconvenience. 🥺 We will contact you shortly to assist you."
        },
        {
            "question_keywords": ["qabul", "vaqtlari", "qaysi", "vaqtda", "soat", "qachon"],
            "answer_text_uz": "Bizning qabul vaqtlarimiz ertalab 7:00 dan kechasi 19:00 gacha. ⏰ Oldindan ro'yxatdan o'tishni unutmang!✍️",
            "answer_text_en": "Our reception hours are from 7:00 AM to 7:00 PM. ⏰ Don't forget to book in advance!✍️"
        },
        {
            "question_keywords": ["biz haqimizda", "markaz haqida", "biz kim", "about us", "about center", "who are we"],
            "answer_text_uz": "Biz Hijama Centre klinikasi. 😊 Sog'ligingiz va go'zalligingiz uchun tabiiy muolajalarni taklif etamiz. Muolajalarimiz: Hijoma, Massaj, Manual terapiya, Girodoterapiya va Kosmetologiya. 🌸",
            "answer_text_en": "We are Hijama Centre. 😊 We offer a wide range of natural treatments for your health and beauty. Our services include: Hijama, Massage, Manual Therapy, Hirudotherapy, and Kosmetology. 🌸"
        }
    ]

    try:
        for faq in initial_faqs_data:
            doc_id = faq["question_keywords"][0]
            faqs_ref.document(doc_id).set(faq, merge=True)
            logging.info(f"✅ FAQ qo'shildi/yangilandi: {doc_id}")
        logging.info("✅ Barcha dastlabki FAQ'lar muvaffaqiyatli qo'shildi/yangilandi.")
    except Exception as e:
        logging.error(f"❌ Dastlabki FAQ'larni qo'shishda xato: {e}", exc_info=True)

# Dastlabki FAQ'larni bot ishga tushganda bazaga qo'shish (bir martalik)
if db and not cached_faqs:
    add_initial_faqs()
    load_faqs_from_firestore()


# System prompt (combined for Uzbek and English)
SYSTEM_PROMPT = """
You are the official artificial intelligence operator of "Hijama Centre". We specialize in treating all diseases with natural methods.
Always respond to clients politely, respectfully, clearly, and helpfully. You are a sales bot, so every word you say should attract interest and retain the client.
You MUST automatically detect the language of the user's message (Uzbek or English) and respond in that same language. Do not mix languages.
You must use emojis where appropriate to make the conversation friendly and engaging.

**Response Rules:**
1.  Only talk about our services, courses, address, and contact information, briefly and clearly.
2.  **If asked about prices or detailed information, do not answer directly.** Instead, reply in a friendly tone: "Batafsil ma'lumot olish uchun iltimos, telefon raqamingizni yozib qoldiring. Biz siz bilan tez orada bog'lanamiz! 📞😊" or "To get detailed information, please leave your phone number. We will contact you shortly! 📞😊".
3.  **Do not provide any information from the internet.** All information must be only from this prompt.
4.  **Do not give medical advice about diseases, their symptoms, or treatment methods.** Provide only general information about the services and courses offered at our center.
5.  Do not get distracted by other topics. If other questions are asked, politely ask for a phone number and inform them that our operators will contact them shortly. Be polite in every word.
6.  **Only answer questions. Do not add "Yes" or similar affirmative or redundant words from yourself. Provide only the requested information, concisely.**
7.  **Make your responses as short and concise as possible. Do not use unnecessary sentences. Try to respond within 100-150 tokens.**
8.  **Always use emojis.**
8.  **Write from the paragraph messages divide them with paragrahp when neccecary information not at all where important**

Our main services:
-   **Hijama (cupping therapy):** An ancient natural method of body cleansing and treating various diseases. It is considered a Sunnah act in Islam.
-   **Massaj:** Various types of massage (therapeutic, relaxing, sports massage) to relieve muscle pain and improve blood circulation.
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
Times of work:
-   **Ish vaqti / Time:** 9:00-21:00
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
                
                # Botning o'zi yuborgan xabarlarni o'tkazib yuborish
                if messaging_event.get("message", {}).get("is_echo"):
                    logging.info("♻️ Echo xabari qabul qilindi. E'tiborsiz qoldirilmoqda.")
                    continue

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

                    # Agar xabarda telefon raqami bo'lsa
                    found_phone_numbers = PHONE_NUMBER_REGEX.findall(user_msg)
                    if found_phone_numbers:
                        phone_number = found_phone_numbers[0]
                        logging.info(f"📞 Telefon raqami aniqlandi: {phone_number}")
                        send_to_telegram_bot(sender_id, phone_number, user_msg)
                        reply = "Ajoyib! Telefon raqamingizni qabul qildik. ✅ Tez orada operatorlarimiz siz bilan bog'lanishadi. E'tiboringiz uchun rahmat! 😊"
                        send_message(sender_id, reply)
                        return "ok", 200
                    
                    current_time = time.time()
                    
                    # Salomlashish uchun javob
                    if "yaxshimisiz" in user_msg_lower or "qaleysiz" in user_msg_lower:
                        reply = "Rahmat, yaxshi! 😊 Sizga qanday yordam bera olaman?"
                        send_message(sender_id, reply)
                        return "ok", 200
                    
                    if "rahmat" in user_msg_lower or "raxmat" in user_msg_lower or "tashakkur" in user_msg_lower:
                        send_message(sender_id, "Sog' bo'ling! 👋")
                        return "ok", 200
                    elif "thank you" in user_msg_lower or "thanks" in user_msg_lower:
                        send_message(sender_id, "You're welcome! 😊")
                        return "ok", 200
                    
                    if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower or "hello" in user_msg_lower:
                        if sender_id not in user_last_greeting_time or \
                           (current_time - user_last_greeting_time[sender_id]) > 24 * 3600:
                            reply = "Va alaykum assalam! 😊 Xush kelibsiz! Qanday yordam bera olaman?" if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower else "Hello! 😊 Welcome! How can I help you?"
                            user_last_greeting_time[sender_id] = current_time
                            send_message(sender_id, reply)
                            return "ok", 200
                        else:
                            reply = "Qanday yordam bera olaman? 😊" if "assalamu alaykum" in user_msg_lower or "salom" in user_msg_lower else "How can I help you? 😊"
                            send_message(sender_id, reply)
                            return "ok", 200

                    # FAQ'lardan mos javobni qidirish
                    matched_faq_answer = None
                    detected_lang = 'uz'
                    
                    if any(keyword in user_msg_lower for keyword in ["address", "location", "services", "contact", "phone", "price", "course", "thank you", "thanks", "called", "contacted", "about"]):
                        detected_lang = 'en'
                    
                    user_msg_words = set(user_msg_lower.split())

                    for faq in cached_faqs:
                        faq_keywords_set = set(faq.get("question_keywords", []))
                        if not user_msg_words.isdisjoint(faq_keywords_set):
                            if detected_lang == 'en':
                                matched_faq_answer = faq.get("answer_text_en")
                            else:
                                matched_faq_answer = faq.get("answer_text_uz")
                            break
                    
                    if matched_faq_answer:
                        send_message(sender_id, matched_faq_answer)
                        return "ok", 200
                    
                    # Agar FAQ'da mos javob topilmasa, Gemini'dan so'rash
                    cached_answer = get_from_cache(user_msg)
                    if cached_answer:
                        reply = cached_answer
                        logging.info(f"💾 Javob keshdan olindi: {reply[:50]}...")
                    else:
                        if model:
                            reply = ask_gemini(user_msg, SYSTEM_PROMPT)
                            logging.info(f"🤖 Gemini javobi: {reply}")
                            save_to_cache(user_msg, reply)
                        else:
                            reply = "Kechirasiz, AI xizmati hozircha mavjud emas. Iltimos, keyinroq urinib ko'ring. 😊"
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
        return "Kechirasiz, AI xizmati hozirda ishlamayapti. 🥺"
    try:
        response = model.generate_content(
            system_prompt + f"\nUser's message: {question}\nResponse:",
            generation_config={"max_output_tokens": 150}
        )
        reply_text = response.text.strip()
        # Ensure emojis are added if not already present
        if '😊' not in reply_text and '📞' not in reply_text and '👍' not in reply_text:
            reply_text += " 😊"
        return reply_text
    except Exception as e:
        logging.error(f"❌ Gemini javobini yaratishda xato: {e}", exc_info=True)
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 🥺"

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
    except requests.exceptions.HTTPError as http_err:
        try:
            error_details = r.json()
            error_message = error_details.get("error", {}).get("message", "Noma'lum xato")
            error_code = error_details.get("error", {}).get("code", "N/A")
            logging.error(f"❌ Meta API'ga xabar yuborishda HTTP xato: {http_err}. Xato kodi: {error_code}, Xato xabari: '{error_message}'")
        except json.JSONDecodeError:
            logging.error(f"❌ Meta API'ga xabar yuborishda HTTP xato: {http_err}. Javob JSON formatida emas. To'liq javob: {r.text}")
    except requests.exceptions.RequestException as req_err:
        logging.error(f"❌ Meta API'ga xabar yuborishda xato: {req_err}", exc_info=True)
    except Exception as e:
        logging.error(f"❌ Xabar yuborishda noma'lum xato: {e}", exc_info=True)

# Send phone number to Telegram bot
def send_to_telegram_bot(instagram_sender_id, phone_number, original_message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("❌ TELEGRAM_BOT_TOKEN yoki TELEGRAM_CHAT_ID o'rnatilmagan. Telefon raqamini Telegramga yuborish imkonsiz.")
        return

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text_message = (
        f"Yangi telefon raqami qabul qilindi!🎉\n"
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
