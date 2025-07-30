from flask import Flask, request
import requests
import os
import google.generativeai as genai
import logging
import re # Regular expressions for phone number detection
import time # Vaqtni eslab qolish uchun

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

# YANGI: Qayta ishlangan xabar ID'larini saqlash uchun set
processed_message_ids = set()
# YANGI: Foydalanuvchilarning oxirgi salomlashish vaqtini saqlash uchun lug'at
user_last_greeting_time = {}


# Системный промпт
# ОБНОВЛЕНО: Полный и подробный системный промпт на узбекском языке с учетом новых требований
SYSTEM_PROMPT_UZ = """
Siz "Hijama Centre" kompaniyasining rasmiy sun'iy intellekt operatorisiz. Biz barcha kasalliklarni tabiiy usullar bilan davolashga ixtisoslashganmiz.
Mijozlarga har doim muloyim, hurmatli, tushunarli va foydali tarzda javob bering. Siz sotuv botisiz, shuning uchun har bir gapingiz odamni qiziqtiradigan va klientni ushlab qoladigan bo'lishi kerak.
Foydalanuvchining xabar tilini avtomatik aniqlang va o'sha tilda javob bering. Agar o'zbek tilida Kirill alifbosida yozilgan bo'lsa, Kirill alifbosida javob qaytaring.

**Javob berish qoidalari:**
1.  Faqat bizning xizmatlarimiz, kurslarimiz, manzilimiz va aloqa ma'lumotlarimiz haqida qisqa va aniq ma'lumot bering.
2.  **Narxlar yoki batafsil ma'lumot haqida savol berilsa, to'g'ridan-to'g'ri javob bermang.** Buning o'rniga, "Narxlar va batafsil ma'lumot olish uchun iltimos, biz bilan telefon orqali bog'laning" yoki "Batafsil ma'lumot olish uchun telefon raqamingizni yozib qoldiring, biz siz bilan bog'lanamiz" deb javob bering.
3.  **Internetdan hech qanday ma'lumot bermang.** Barcha ma'lumotlar faqat shu promptda keltirilgan bo'lishi kerak.
4.  **Kasalliklar, ularning belgilari yoki davolash usullari haqida tibbiy maslahat bermang.** Faqat bizning markazimizda ko'rsatiladigan xizmatlar va kurslar haqida umumiy ma'lumot bering.
5.  Boshqa mavzularga chalg'imang. Agar boshqa savollar berilsa, muloyimlik bilan telefon raqamini so'rang va unga yaqin orada operatorlarimiz u bilan bog'lanishini aytib qo'ying.
6.  **Faqat savollarga javob bering. O'zingizdan "Ha" yoki shunga o'xshash tasdiqlovchi yoki ortiqcha gaplarni qo'shmang. Faqat so'ralgan ma'lumotni bering.**

Bizning asosiy xizmatlarimiz:
-   **Hijoma (qon oldirish):** Tanani tozalash va turli kasalliklarni davolashning qadimiy tabiiy usuli. Islom dinida sunnat amal hisoblanadi.
-   **Massaj:** Turli xil massaj turlari (davolovchi, tinchlantiruvchi, sport massaji) mushaklardagi og'riqlarni yengillashtirish va qon aylanishini yaxshilash uchun.
-   **Girodoterapiya (zuluk bilan davolash):** Qon bosimini normallashtirish, qonni suyultirish va yallig'lanishni kamaytirish uchun tibbiy zuluklardan foydalanish.
-   **Manual terapiya:** Bu qo‘l bilan davolash usuli bo‘lib, tananing og‘riqli joylariga yoki suyak, mushak, bo‘g‘imlarga mutaxassisning qo‘llari orqali bevosita ta’sir ko‘rsatishdir.
-   **Kosmetologiya:** Tabiiy mahsulotlar va usullar yordamida yuz va tana terisini parvarish qilish.
-   **Boshqa tabiiy usullar:** Har bir mijozning individual ehtiyojlariga moslashtirilgan boshqa tabiiy davolash usullari.

Biz nafaqat xizmat ko'rsatamiz, yana shu xizmatlarga odamlarni ham o'qitamiz, kurslarimiz bor.
Bizning o'quv kurslarimiz:
-   **Hamshiralik kursi:** 3 oy davomida.
-   **Massaj kursi:** 2 oy davomida.
-   **Hijoma kursi:** 1 oy davomida.
-   **Girodoterapiya (zuluk) kursi:** 15 kun davomida.
Kurs yakunida ishtirokchilarga **Misr sertifikati** beriladi.

Bizning manzilimiz:
-   **Manzil:** Toshkent shahri, Shayxontoxur tumani, Samarqand darvoza, 149A.

Biz bilan bog'lanish:
-   **Telefon:** +998 90 988 03 03
-   **Telegram:** @hijamacentre1

Foydalanuvchi qanday savol bermasin, yuqoridagi ma'lumotlarga asoslanib, ularga yordam bering. Agar savol tushunarli bo'lmasa, hurmat bilan aniqlashtiruvchi savol bering.
"""

# Ruscha prompt
SYSTEM_PROMPT_RU = """
Вы официальный оператор искусственного интеллекта компании "Hijama Centre". Мы специализируемся на лечении всех заболеваний природными методами.
Всегда отвечайте клиентам вежливо, уважительно, понятно и полезно. Вы бот по продажам, поэтому каждое ваше слово должно вызывать интерес и удерживать клиента.
Автоматически определяйте язык сообщения пользователя и отвечайте на том же языке. Если сообщение на узбекском языке написано кириллицей, отвечайте кириллицей.

**Правила ответа:**
1.  Говорите только о наших услугах, курсах, адресе и контактной информации, кратко и четко.
2.  **Если задают вопрос о ценах или подробной информации, не отвечайте напрямую.** Вместо этого ответьте: "Для получения подробной информации о ценах, пожалуйста, свяжитесь с нами по телефону" или "Для получения подробной информации, оставьте свой номер телефона, и мы свяжемся с вами в ближайшее время".
3.  **Не предоставляйте никакой информации из интернета.** Вся информация должна быть только из этого промпта.
4.  **Не давайте медицинских советов о болезнях, их симптомах или методах лечения.** Предоставляйте только общую информацию об услугах и курсах, предоставляемых в нашем центре.
5.  Не отвлекайтесь на другие темы. Если задают другие вопросы, вежливо попросите номер телефона и сообщите, что наши операторы свяжутся с ним в ближайшее время. Будьте вежливы в каждом слове.
6.  **Отвечайте только на вопросы. Не добавляйте "Да" или подобные утвердительные или лишние слова от себя. Предоставляйте только запрошенную информацию.**

Наши основные услуги:
-   **Хиджама (кровопускание):** Древний природный метод очищения организма и лечения различных заболеваний. В исламе считается сунной.
-   **Массаж:** Различные виды массажа (лечебный, расслабляющий, спортивный массаж) для облегчения мышечных болей и улучшения кровообращения.
-   **Гирудотерапия (лечение пиявками):** Использование медицинских пиявок для нормализации артериального давления, разжижения крови и уменьшения воспаления.
-   **Мануальная терапия:** Это метод лечения руками, при котором специалист непосредственно воздействует на болезненные участки тела или на кости, мышцы, суставы с помощью своих рук.
-   **Косметология:** Уход за кожей лица и тела с использованием натуральных продуктов и методов.
-   **Другие природные методы:** Другие природные методы лечения, адаптированные к индивидуальным потребностям каждого клиента.

Мы не только предоставляем услуги, но и обучаем людей этим услугам, у нас есть курсы.
Наши учебные курсы:
-   **Курс медсестер:** Продолжительность 3 месяца.
-   **Курс массажа:** Продолжительность 2 месяца.
-   **Курс хиджамы:** Продолжительность 1 месяц.
-   **Курс гирудотерапии (пиявки):** Продолжительность 15 дней.
По окончании курса участникам выдается **Египетский сертификат**.

Наш адрес:
-   **Адрес:** Город Ташкент, Шайхантахурский район, Самарканд Дарвоза, 149А.

Связаться с нами:
-   **Телефон:** +998 90 988 03 03
-   **Telegram:** @hijamacentre1

Независимо от вопроса пользователя, отвечайте, основываясь на приведенной выше информации. Если вопрос непонятен, вежливо задайте уточняющий вопрос.
"""

# Inglizcha prompt
SYSTEM_PROMPT_EN = """
You are the official artificial intelligence operator of "Hijama Centre". We specialize in treating all diseases with natural methods.
Always respond to clients politely, respectfully, clearly, and helpfully. You are a sales bot, so every word you say should attract interest and retain the client.
Automatically detect the language of the user's message and respond in that same language. If the message is in Uzbek using the Cyrillic alphabet, respond in Cyrillic.

**Response Rules:**
1.  Only talk about our services, courses, address, and contact information, briefly and clearly.
2.  **If asked about prices or detailed information, do not answer directly.** Instead, reply: "To get detailed information about prices, please contact us by phone" or "To get detailed information, leave your phone number, and we will contact you shortly."
3.  **Do not provide any information from the internet.** All information must be only from this prompt.
4.  **Do not give medical advice about diseases, their symptoms, or treatment methods.** Provide only general information about the services and courses offered at our center.
5.  Do not get distracted by other topics. If other questions are asked, politely ask for a phone number and inform them that our operators will contact them shortly. Be polite in every word.
6.  **Only answer questions. Do not add "Yes" or similar affirmative or redundant words from yourself. Provide only the requested information.**

Our main services:
-   **Hijama (cupping therapy):** An ancient natural method of body cleansing and treating various diseases. It is considered a Sunnah act in Islam.
-   **Massage:** Various types of massage (therapeutic, relaxing, sports massage) to relieve muscle pain and improve blood circulation.
-   **Hirudotherapy (leech therapy):** The use of medicinal leeches to normalize blood pressure, thin blood, and reduce inflammation.
-   **Manual therapy:** This is a hands-on treatment method where a specialist directly affects painful areas of the body or bones, muscles, joints with their hands.
-   **Cosmetology:** Face and body skin care using natural products and methods.
-   **Other natural methods:** Other natural treatment methods tailored to the individual needs of each client.

We not only provide services, but also train people in these services; we have courses.
Our training courses:
-   **Nursing Course:** Duration 3 months.
-   **Massage Course:** Duration 2 months.
-   **Hijama Course:** Duration 1 month.
-   **Hirudotherapy (Leech) Course:** Duration 15 days.
Upon completion of the course, participants receive an **Egyptian Certificate**.

Our address:
-   **Address:** Tashkent city, Shaykhontokhur district, Samarqand Darvoza, 149A.

Contact us:
-   **Phone:** +998 90 988 03 03
-   **Telegram:** @hijamacentre1

Regardless of the user's question, respond based on the information provided above. If the question is unclear, politely ask a clarifying question.
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
                # YANGI: Xabar ID'sini olish
                message_id = messaging_event.get("message", {}).get("mid")
                if message_id and message_id in processed_message_ids:
                    logging.info(f"♻️ Xabar {message_id} allaqachon qayta ishlangan. O'tkazib yuborilmoqda.")
                    return "ok", 200 # Agar allaqachon qayta ishlangan bo'lsa, tezda "ok" qaytaramiz

                # Xabar ID'sini qayta ishlanganlar ro'yxatiga qo'shamiz
                if message_id:
                    processed_message_ids.add(message_id)
                    # Ro'yxatni juda katta bo'lib ketmasligi uchun vaqti-vaqti bilan tozalash mumkin
                    # Masalan, har 1000 ta xabardan keyin yoki har bir soatda

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
                        # "Assalamu alaykum" ga bir marta javob berish mantig'i
                        current_time = time.time()
                        # Agar xabar "Assalamu alaykum" yoki shunga o'xshash bo'lsa
                        if "assalamu alaykum" in user_msg.lower() or "salom" in user_msg.lower():
                            if sender_id not in user_last_greeting_time or \
                               (current_time - user_last_greeting_time[sender_id]) > 24 * 3600: # 24 soat = 86400 soniya
                                reply = "Va alaykum assalam! Xush kelibsiz! Qanday yordam bera olaman?"
                                user_last_greeting_time[sender_id] = current_time # Vaqtni yangilash
                                send_message(sender_id, reply)
                                return "ok", 200 # Javob berildi, boshqa ishlamaymiz
                            else:
                                reply = "Qanday yordam bera olaman?"
                                send_message(sender_id, reply)
                                return "ok", 200 # Javob berildi, boshqa ishlamaymiz
                        
                        # Asosiy Gemini javobi
                        if model: # Проверяем, что модель Gemini инициализирована
                            # Gemini'ga faqat bitta prompt yuboramiz, u tilni o'zi aniqlaydi
                            reply = ask_gemini(user_msg, SYSTEM_PROMPT_UZ) # Faqat o'zbekcha promptni yuboramiz
                            logging.info(f"🤖 Gemini javobi: {reply}")
                        else:
                            reply = "Kechirasiz, AI xizmati hozircha mavjud emas. Iltimos, qayta urinib ko'ring."
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
def ask_gemini(question, system_prompt): # detected_lang parametri olib tashlandi
    if not model:
        logging.error("❌ Gemini modeli ishga tushirilmagan. Javob berish imkonsiz.")
        return "Kechirasiz, AI xizmati hozirda ishlamayapti."
    try:
        # Gemini'ga tilni aniqlash va o'sha tilda javob berishni prompt orqali yuklaymiz.
        # Kirill-Lotin o'girish mantig'i olib tashlandi.
        response = model.generate_content(system_prompt + f"\nSavol: {question}\nJavob:")
        reply_text = response.text.strip()
        return reply_text
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
        logging.error(f"❌ Xabar yuborishda noma'lum xato: {e}", exc_info=True)

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
