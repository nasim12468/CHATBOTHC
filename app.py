from flask import Flask, request
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Токены из переменных окружения Render
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

# Явно указываем Page ID Hijama School
PAGE_ID = '100346212770134'

@app.route('/webhook', methods=['GET'])
def verify():
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    for entry in data.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = msg['sender']['id']
            text   = msg.get('message', {}).get('text', '')

            # Определяем ответ по ключевым словам
            txt = text.lower()

            if 'привет' in txt:
                # Обычный текстовый ответ
                send_message(sender, 'Привет! Чем могу помочь?')

            elif 'цены' in txt:
                # Отправляем шаблон с кнопками для раздела "Цены"
                buttons = [
                    { 'type': 'postback', 'title': 'Стандартный', 'payload': 'PRICE_STANDARD' },
                    { 'type': 'postback', 'title': 'Премиум',      'payload': 'PRICE_PREMIUM' }
                ]
                send_button_template(sender, 'Выберите тариф:', buttons)

            elif 'контакты' in txt:
                # Ещё один пример кнопки, ведущей на внешнюю ссылку
                buttons = [
                    { 'type': 'web_url', 'title': 'Открыть сайт', 'url': 'https://hijamaschool.example.com' }
                ]
                send_button_template(sender, 'Наш сайт с контактами:', buttons)

            # можно добавить другие варианты

    return 'OK', 200


def send_message(recipient_id, text):
    url = f'https://graph.facebook.com/v23.0/{PAGE_ID}/messages'
    params = {'access_token': ACCESS_TOKEN}
    payload = {
        'recipient': {'id': recipient_id},
        'message':   {'text': text}
    }
    return requests.post(url, params=params, json=payload)


def send_button_template(recipient_id, text, buttons):
    url = f'https://graph.facebook.com/v23.0/{PAGE_ID}/messages'
    params = {'access_token': ACCESS_TOKEN}
    payload = {
        'recipient': {'id': recipient_id},
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'button',
                    'text': text,
                    'buttons': buttons
                }
            }
        }
    }
    return requests.post(url, params=params, json=payload)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
