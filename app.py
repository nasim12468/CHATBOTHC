import os
import time
import logging
import re
import random
from instagrapi import Client
import google.generativeai as genai

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Check that all necessary tokens exist
if not all([INSTA_USERNAME, INSTA_PASSWORD, GEMINI_API_KEY]):
    logging.error("❌ Xato: Instagram login ma'lumotlari yoki Gemini API kaliti o'rnatilmagan! Bot ishga tushirilmaydi.")
    exit()

# Initialize Gemini
model = None
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    logging.info("✅ Gemini API 'gemini-1.5-flash' modeli bilan muvaffaqiyatli ishga tushirildi.")
except Exception as e:
    logging.error(f"❌ Gemini API'ni ishga tushirishda xato: {e}", exc_info=True)
    exit()

# FAQ and Answers dictionary
# You can add new questions and answers to this dictionary here
# Keywords must be words.
FAQS = {
    "uz": {
        "xizmatlar": "🌸 Hijama Centre klinikasida sog'ligingiz va go'zalligingiz uchun tabiiy muolajalarni taklif etamiz.\nMuolajalarimiz:\n- Hijoma\n- Massaj\n- Manual terapiya\n- Girodoterapiya\n- Kosmetologiya",
        "hijoma": "🩸 Hijoma (banka bilan davolash) - bu qadimiy tabiiy usul bo'lib, tanani tozalash va turli kasalliklarni davolash uchun qo'llaniladi. Islomda sunnat amali hisoblanadi.",
        "massaj": "💆‍♂️ Bizda mushaklardagi og'riqlarni yo'qotish va qon aylanishini yaxshilash uchun turli xil massaj turlari mavjud.",
        "manzil": "📍 Bizning manzilimiz: Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.",
        "kurslar": "👩‍🎓 Bizda tabiiy tibbiyot sohasida kasb egallashni istaganlar uchun maxsus kurslar mavjud.\nKursni muvaffaqiyatli yakunlaganlarga Misr sertifikati beriladi. 📜",
        "boglanish": "📞 Biz bilan bog'lanish uchun:\n- Telefon: +998 90 988 03 03\n- Telegram: @hijamacentre1",
        "narx": "📞 Batafsil ma'lumot olish uchun, iltimos, telefon raqamingizni qoldiring. Biz siz bilan tez orada bog'lanamiz! 😊",
        "ijara": "📞 Ijara bo'yicha batafsil ma'lumot olish uchun, iltimos, telefon raqamingizni qoldiring.\nBiz siz bilan tez orada bog'lanamiz!😊",
        "kosmetologiya": "💄 Kosmetologiya bo'yicha xizmatlarimiz yuz va tana terisiga g'amxo'rlik qilishga qaratilgan. Batafsil ma'lumot olish uchun biz bilan bog'laning.",
        "shifokor": "👨‍⚕️ Klinikamizda tibbiy ma'lumotga ega mutaxassislar ishlaydi. Ular sizni qabul qilish uchun doim tayyor.",
        "ish": "💼 Bo'sh ish o'rinlari haqida ma'lumot olish uchun, iltimos, telefon raqamingizni qoldiring. Biz siz bilan bog'lanamiz!",
        "qabul": "📞 Qabulga yozilish uchun, iltimos, telefon raqamingizni qoldiring. Biz siz bilan tez orada bog'lanamiz!😊",
        "qon": "🩸 Hijomada qon olish jarayoni sanitariya-gigiyena qoidalariga rioya qilingan holda amalga oshiriladi. Bu haqda toʻliq maʼlumot olish uchun klinikamizga murojaat qiling.",
        "fallback": "Kechirasiz, men bu savolga javob bera olmayman. Iltimos, biz bilan to'g'ridan-to'g'ri bog'laning yoki FAQ'lardan savol tanlang.😊"
    },
    "en": {
        "services": "🌸 At Hijama Centre, we offer natural treatments for your health and beauty.\nOur services include:\n- Hijama\n- Massage\n- Manual Therapy\n- Hirudotherapy\n- Kosmetology",
        "hijama": "🩸 Hijama (cupping therapy) is an ancient natural method used for body cleansing and treating various diseases. It is considered a Sunnah act in Islam.",
        "massage": "💆‍♂️ We offer various types of massage to relieve muscle pain and improve blood circulation.",
        "location": "📍 Our center is located at: Toshkent city, Shaykhontokhur district, Samarqand Darvoza, 149A.",
        "courses": "👩‍🎓 We have specialized courses for those who want to build a career in natural medicine.\nUpon successful completion, you will receive an Egyptian Certificate. 📜",
        "contact": "📞 You can reach us at:\n- Phone: +998 90 988 03 03\n- Telegram: @hijamacentre1",
        "price": "📞 To get detailed information about prices, please leave your phone number. We will contact you shortly! 😊",
        "rent": "📞 To get detailed information about rent, please leave your phone number.\nWe will contact you shortly! 😊",
        "cosmetology": "💄 Our cosmetology services focus on skin care for the face and body. Please contact us for more information.",
        "doctor": "👨‍⚕️ Our clinic employs medical professionals. They are always ready to assist you.",
        "job": "💼 For information on job vacancies, please leave your phone number. We will contact you shortly!",
        "appointment": "📞 To book an appointment, please leave your phone number. We will contact you shortly!😊",
        "blood": "🩸 The blood-letting procedure in Hijama is performed in compliance with sanitary and hygienic rules. For full information on this, please contact our clinic.",
        "fallback": "Sorry, I can't answer this question right now. Please contact us directly or choose a question from the FAQ.😊"
    }
}

# System prompt for Gemini (no longer used for replies, but kept for context)
SYSTEM_PROMPT = """
Siz "Hijama Centre"ning rasmiy sun'iy intellekt operatorisiz. Biz barcha kasalliklarni tabiiy usullar bilan davolashga ixtisoslashganmiz.
Mijozlarga har doim xushmuomala, hurmat bilan, aniq va foydali javob bering.
Siz foydalanuvchining xabar tilini (o'zbek yoki ingliz) avtomatik aniqlashingiz va xuddi shu tilda javob berishingiz SHART.
Har bir yangi jumlani yangi qatordan boshlashingiz SHART.
Javob berishda sizga berilgan FAQ'lardan foydalaning.

**Javob berish qoidalari:**
1.  Faqat bizning xizmatlarimiz, kurslarimiz, manzilimiz va aloqa ma'lumotlarimiz haqida qisqacha va aniq gapiring.
2.  **Agar narxlar yoki batafsil ma'lumot so'ralsa, to'g'ridan-to'g'ri javob bermang.** Buning o'rniga, do'stona ohangda "📞 Batafsil ma'lumot olish uchun iltimos, telefon raqamingizni yozib qoldiring. Biz siz bilan tez orada bog'lanamiz!" yoki "📞 To get detailed information, please leave your phone number. We will contact you shortly!".
3.  **Kasalliklar, ularning simptomlari yoki davolash usullari haqida tibbiy maslahatlar bermang.** Faqat markazimizda taklif qilinadigan xizmatlar va kurslar haqida umumiy ma'lumot bering.
4.  Boshqa mavzularga chalg'imang.
5.  Javoblaringizni iloji boricha qisqa va lo'nda qiling. Keraksiz jumlalardan foydalanmang.
"""

# RegEx for phone numbers
PHONE_NUMBER_REGEX = re.compile(r'\+?\d{9,15}')
# Keywords related to price
PRICE_KEYWORDS = ["narx", "qancha", "turadi", "pul", "to'lov", "ijara", "cost", "price", "how much", "rent"]
# New keywords for appointments
APPOINTMENT_KEYWORDS = ["qabul", "yozilish", "yozilmoq", "navbat", "yozilaman", "appointment", "book", "schedule", "visit"]

# Get a response from Gemini (this function is no longer called in the main loop, as per your request)
def get_gemini_response(question, system_prompt):
    if not model:
        return "Kechirasiz, AI xizmati hozircha mavjud emas. Iltimos, keyinroq urinib ko'ring. 😊"
    try:
        response = model.generate_content(
            system_prompt + f"\nUser's message: {question}\nResponse:",
            generation_config={"max_output_tokens": 150}
        )
        reply_text = response.text.strip()
        reply_text = re.sub(r'\n+', '\n', reply_text).strip()
        return reply_text
    except Exception as e:
        logging.error(f"❌ Gemini javobini yaratishda xato: {e}", exc_info=True)
        return "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 🥺"

# Detect language
def detect_language(text):
    uzbek_keywords = ["salom", "qanday", "nima", "qayerda", "narx", "rahmat", "hijoma", "xizmat", "kurs"]
    english_keywords = ["hello", "how", "what", "where", "price", "thank you", "hijama", "service", "course"]
    text_lower = text.lower()
    if any(word in text_lower for word in english_keywords):
        return 'en'
    return 'uz'

# Run the Instagram bot
def run_insta_bot():
    cl = Client()
    try:
        logging.info("⏳ Instagram'ga kirish...")
        cl.login(INSTA_USERNAME, INSTA_PASSWORD)
        logging.info("✅ Instagram'ga muvaffaqiyatli kirildi.")
    except Exception as e:
        logging.error(f"❌ Instagram'ga kirishda xato: {e}")
        return

    # To avoid blocking, we will use a random polling interval
    # The interval will be between 2 and 3 minutes (120-180 seconds)
    POLLING_INTERVAL = random.randint(120, 180)
    processed_thread_ids = set()

    while True:
        try:
            inbox_threads = cl.direct_inbox(amount=20)
            
            for thread in inbox_threads.threads:
                thread_id = thread.id
                
                if thread_id in processed_thread_ids:
                    continue

                if not thread.messages:
                    continue
                
                last_message = thread.messages[0]
                
                if last_message.user_id == cl.user_id or last_message.item_type != 'text':
                    processed_thread_ids.add(thread_id)
                    continue
                
                user_msg = last_message.text.strip()
                user_msg_lower = user_msg.lower()
                sender_id = last_message.user_id
                
                logging.info(f"👤 Foydalanuvchidan yangi xabar ({sender_id}): {user_msg}")
                
                # Detect language
                detected_lang = detect_language(user_msg)
                
                # Check for phone number first
                found_phone_numbers = PHONE_NUMBER_REGEX.findall(user_msg)
                if found_phone_numbers:
                    phone_number = found_phone_numbers[0]
                    # Since we removed Telegram functionality, we just log and respond.
                    logging.info(f"📞 Telefon raqami topildi: {phone_number}")
                    reply = "📞 Ajoyib! Telefon raqamingizni qabul qildik. Tez orada operatorlarimiz siz bilan bog'lanishadi. E'tiboringiz uchun rahmat! 😊"
                    cl.direct_send(reply, [sender_id])
                    processed_thread_ids.add(thread_id)
                    continue

                # Check for appointment keywords
                if any(kw in user_msg_lower for kw in APPOINTMENT_KEYWORDS):
                    reply = FAQS[detected_lang]["qabul"] if detected_lang == 'uz' else FAQS[detected_lang]["appointment"]
                    cl.direct_send(reply, [sender_id])
                    processed_thread_ids.add(thread_id)
                    continue

                # Check for price keywords
                if any(pk in user_msg_lower for pk in PRICE_KEYWORDS):
                    reply = FAQS[detected_lang]["narx"] if detected_lang == 'uz' else FAQS[detected_lang]["price"]
                    cl.direct_send(reply, [sender_id])
                    processed_thread_ids.add(thread_id)
                    continue

                # Search for answer in static FAQs
                matched_faq_answer = None
                user_msg_words = set(user_msg_lower.split())
                for keyword, answer in FAQS[detected_lang].items():
                    if any(word in user_msg_words for word in keyword.split()):
                        matched_faq_answer = answer
                        break
                
                if matched_faq_answer:
                    cl.direct_send(matched_faq_answer, [sender_id])
                    processed_thread_ids.add(thread_id)
                    continue
                
                # If no FAQ match, send a fallback message instead of calling Gemini
                reply = FAQS[detected_lang]["fallback"]
                cl.direct_send(reply, [sender_id])
                processed_thread_ids.add(thread_id)

        except Exception as e:
            logging.error(f"❌ Xatolik yuz berdi: {e}")
            
        time.sleep(POLLING_INTERVAL)

if __name__ == "__main__":
    run_insta_bot()
