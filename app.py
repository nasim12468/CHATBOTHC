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
    print(f"[WEBHOOK VERIFY] mode={mode}, token={token}, challenge={challenge}", flush=True)

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("[WEBHOOK VERIFY] OK", flush=True)
        return challenge, 200

    print("[WEBHOOK VERIFY] FAILED", flush=True)
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("[WEBHOOK PAYLOAD]", data, flush=True)

    # Обрабатываем все записи
    for entry in data.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = msg['sender']['id']
            text   = msg.get('message', {}).get('text', '')
            print(f"[INCOMING] from={sender} text={text!r}", flush=True)

            # Определяем ответ по ключевым словам
            txt = text.lower()
            reply = None
            if 'привет' in txt:
                reply = 'Привет! Чем могу помочь?'
            elif 'цены' in txt:
                reply = 'Наши цены: …'
            # elif 'другое_слово' in txt:
            #     reply = 'Ваш ответ'

            if reply:
                print(f"[REPLY] to={sender} text={reply!r}", flush=True)
                resp = send_message(sender, reply)
                print(f"[FB RESP] status={resp.status_code} body={resp.text}", flush=True)

    return 'OK', 200

def send_message(recipient_id, text):
    # Отправляем сообщение от имени страницы PAGE_ID
    url = f'https://graph.facebook.com/v23.0/{PAGE_ID}/messages'
    params = {'access_token': ACCESS_TOKEN}
    payload = {
        'recipient': {'id': recipient_id},
        'message':   {'text': text}
    }
    print("[SEND_MESSAGE] URL=", url, " TOKEN…", ACCESS_TOKEN[:10] + '…', flush=True)
    return requests.post(url, params=params, json=payload)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
