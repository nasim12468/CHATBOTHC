from flask import Flask, request
import requests
import os
import google.generativeai as genai
import logging
import re # Regular expressions for phone number detection

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Загрузка переменных среды
# Убедитесь, что эти переменные установлены в вашем окружении (например, через .env файл или настройки хостинга)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# YANGI: Telegram bot uchun token va chat ID
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# Выводим токены (обрезанные) в консоль для отладки
logging.info(f"✅ VERIFY_TOKEN (first 10): {VERIFY_TOKEN[:10] if VERIFY_TOKEN else 'Not found'}")
logging.info(f"✅ PAGE_ACCESS_TOKEN (first 10): {PAGE_ACCESS_TOKEN[:10] if PAGE_ACCESS_TOKEN else 'Not found'}")
logging.info(f"✅ GEMINI_API_KEY (first 10): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'Not found'}")
logging.info(f"✅ TELEGRAM_BOT_TOKEN (first 10): {TELEGRAM_BOT_TOKEN[:10] if TELEGRAM_BOT_TOKEN else 'Not found'}")
logging.info(f"✅ TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID if TELEGRAM_CHAT_ID else 'Not found'}")


# Проверка наличия токенов
if not VERIFY_TOKEN or not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("❌ Xato: Bir yoki bir nechta muhit o'zgaruvchilari o'rnatilmagan! Bot to'liq ishlay olmaydi.")
    # В реальном приложении можно не выходить, а возвращать 500 ошибку или иметь заглушку
    # exit(1) # Закомментировано для возможности запуска даже без всех токенов, но функционал будет ограничен

# Инициализация Gemini
model = None # Инициализируем модель как None по умолчанию
try:
    if GEMINI_API_KEY: # Проверяем, что ключ API существует
        genai.configure(api_key=GEMINI_API_KEY)
        # Используем 'gemini-1.5-flash' вместо 'gemini-pro'
        model = genai.GenerativeModel("gemini-1.5-flash")
        logging.info("✅ Gemini API 'gemini-1.5-flash' modeli bilan muvaffaqiyatli ishga tushirildi.")
    else:
        logging.warning("⚠️ GEMINI_API_KEY o'rnatilmagan. Gemini modeli ishlamaydi.")
except Exception as e:
    logging.error(f"❌ Gemini API'ni ishga tushirishda xato: {e}", exc_info=True) # Добавляем exc_info для полного traceback

# Системный промпт
# ОБНОВЛЕНО: Полный и подробный системный промпт на узбекском языке с учетом новых требований
SYSTEM_PROMPT = """
Siz "Hijama Centre" kompaniyasining rasmiy sun'iy intellekt operatorisiz. Biz barcha kasalliklarni tabiiy usullar bilan davolashga ixtisoslashganmiz.
Mijozlarga har doim muloyim, hurmatli, tushunarli va foydali tarzda javob bering. Faqat o'zbek tilida yozing.

**Javob berish qoidalari:**
1.  Faqat bizning xizmatlarimiz, manzilimiz va aloqa ma'lumotlarimiz haqida gapiring.
2.  **Narxlar yoki batafsil ma'lumot haqida savol berilsa, to'g'ridan-to'g'ri javob bermang.** Buning o'rniga, "Narxlar va batafsil ma'lumot olish uchun iltimos, biz bilan telefon orqali bog'laning" yoki "Narxlar xizmat turiga qarab farq qiladi. Batafsil ma'lumot uchun bizga qo'ng'iroq qiling" deb javob bering. Yoki "Batafsil ma'lumot olish uchun telefon raqamingizni yozib qoldiring, biz siz bilan bog'lanamiz" deb ayting.
3.  **Internetdan hech qanday ma'lumot bermang.** Barcha ma'lumotlar faqat shu promptda keltirilgan bo'lishi kerak.
4.  **Kasalliklar, ularning belgilari yoki davolash usullari haqida tibbiy maslahat bermang.** Faqat bizning markazimizda ko'rsatiladigan xizmatlar haqida umumiy ma'lumot bering.
5.  Barcha ma'lumotlar faqat ishga va markazga oid bo'lishi kerak. Boshqa mavzularga chalg'imang. Agar boshqa savollar berilsa telefon raqamini so'rang va unga yaqin orada operatorlarimiz u bilan bog'lanishini aytib qo'ying xushmuomila bo'ling har bir gapingizfa
6.  Agar foydalanuvchi "Assalamu alaykum" deb yozsa, birinchi marta "Va alaykum assalam! Xush kelibsiz! Qanday yordam bera olaman?" deb javob bering. Keyingi "Assalamu alaykum"larga esa faqat "Qanday yordam bera olaman?" yoki shunga o'xshash qisqa javob bering. (Bu qoida keyinchalik kodda ham qo'llab-quvvatlanishi kerak).

Bizning asosiy xizmatlarimiz:
-   **Hijoma (qon oldirish):** Tanani tozalash va turli kasalliklarni davolashning qadimiy tabiiy usuli. Islom dinida suunnat amal xisoblanadi
-   **Massaj:** Turli xil massaj turlari (davolovchi, tinchlantiruvchi, sport massaji) mushaklardagi og'riqlarni yengillashtirish va qon aylanishini yaxshilash uchun.
-   **Girodoterapiya (zuluk bilan davolash):** Qon bosimini normallashtirish, qonni suyultirish va yallig'lanishni kamaytirish uchun tibbiy zuluklardan foydalanish.
-   **Boshqa tabiiy usullar:** Har bir mijozning individual ehtiyojlariga moslashtirilgan boshqa tabiiy davolash usullari.
-   **Manual terapiya:** Bu qo‘l bilan davolash usuli bo‘lib, tananing og‘riqli joylariga yoki suyak, mushak, bo‘g‘imlarga mutaxassisning qo‘llari orqali bevosita ta’sir ko‘rsatishdir.

Biz nafaqat xizmat ko'rsatamiz, yana shu xizmatlarga odamlarni ham o'qitamiz, kurslarimiz bor
Bizning o'quv kurslarimiz:
-   **Hamshiralik kursi:** 3 oy davomida.
-   **Massaj kursi:** 2 oy davomida.
-   **Hijoma kursi:** 1 oy davomida.
-   **Girodoterapiya (zuluk) kursi:** 15 kun davomida.
Kurs yakunida ishtirokchilarga **Misr sertifikati** beriladi.

Bizning manzilimiz:
-   **Manzil:** Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.

Biz bilan bog'lanish:
-   **Telefon:** +998 93 161 27 29
-   **Telegram:** @HijamaCentreBot

Foydalanuvchi qanday savol bermasin, yuqoridagi ma'lumotlarga asoslanib, ularga yordam bering. Agar savol tushunarli bo'lmasa, hurmat bilan aniqlashtiruvchi savol bering. Hamma gaplaringiz odamni qiziqtiradigan va xarakat qilib klientni ushlab qoladigan bo'lishi kerak chunki siz sotuv botisiz operator
Agar ingliz tilida savol kelsa ingliz tilida javob ber agar rus tilida savol kelsa ruscha javob ber
"""


# Верификация (GET)
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

# YANGI: Telefon raqamini aniqlash uchun regex
# Bu regex O'zbekistondagi telefon raqamlarini (masalan, +998XXYYYYYYY, 93YYYYYYY, 99YYYYYYY) aniqlashga harakat qiladi.
# To'liqroq regexlar ham mavjud, lekin bu boshlang'ich uchun yetarli.
PHONE_NUMBER_REGEX = re.compile(r'\+?\d{9,15}') # + bilan boshlanishi mumkin, 9 dan 15 gacha raqam

# Обработка сообщений (POST)
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"📩 [WEBHOOK] Qabul qilingan ma'lumotlar: {data}")

    if not data:
        logging.warning("⚠️ Bo'sh POST so'rovi qabul qilindi.")
        return "ok", 200

    # Проверяем, что это сообщение Instagram
    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event and "text" in messaging_event["message"]:
                    user_msg = messaging_event["message"]["text"]
                    logging.info(f"👤 Foydalanuvchidan xabar ({sender_id}): {user_msg}")

                    # YANGI: Telefon raqamini aniqlash mantig'i
                    found_phone_numbers = PHONE_NUMBER_REGEX.findall(user_msg)
                    if found_phone_numbers:
                        phone_number = found_phone_numbers[0] # Birinchi topilgan raqamni olamiz
                        logging.info(f"📞 Telefon raqami aniqlandi: {phone_number}")
                        send_to_telegram_bot(sender_id, phone_number, user_msg)
                        reply = "Raqamingiz qabul qilindi. Tez orada siz bilan bog'lanamiz. E'tiboringiz uchun rahmat!"
                        send_message(sender_id, reply)
                    else:
                        # Agar telefon raqami topilmasa, Gemini orqali javob beramiz
                        if model: # Проверяем, что модель Gemini инициализирована
                            reply = ask_gemini(user_msg)
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

# Генерация ответа от Gemini
def ask_gemini(question):
    if not model:
        logging.error("❌ Gemini modeli ishga tushirilmagan. Javob berish imkonsiz.")
        return "Kechirasiz, AI xizmati hozirda ishlamayapti."
    try:
        # Используем SYSTEM_PROMPT как часть запроса, это более типично для Gemini API
        response = model.generate_content(SYSTEM_PROMPT + f"\nSavol: {question}\nJavob:")
        return response.text.strip()
    except Exception as e:
        logging.error(f"❌ Gemini javobini yaratishda xato: {e}", exc_info=True) # Добавляем exc_info=True для полного traceback
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
        logging.error("❌ PAGE_ACCESS_TOKEN o'rnatilmagan. Xabar yuborish imkonsiz.")
        return

    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status() # Вызывает исключение для HTTP ошибок (4xx или 5xx)
        logging.info(f"📤 Javob foydalanuvchiga yuborildi ({recipient_id}): {message_text[:50]}...") # Обрезаем для лога
        logging.info(f"📡 Meta serveridan javob: {r.status_code} - {r.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Meta API'ga xabar yuborishda xatolik: {e}", exc_info=True)
        if r is not None:
            logging.error(f"❌ Meta javobi (xato): {r.status_code} - {r.text}")
    except Exception as e:
        logging.error(f"❌ Xabar yuborishda noma'lum xatolik: {e}", exc_info=True)

# YANGI: Telefon raqamini Telegram botga yuborish funksiyasi
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


# Запуск сервера
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Bot ishga tushdi. {port} portida so'rovlar kutilmoqda...")
    app.run(host="0.0.0.0", port=port, debug=True) # debug=True полезен для локальной отладки
