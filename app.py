from flask import Flask, request
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

app = Flask(__name__)
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.mode') == 'subscribe' and        request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    for entry in data.get('entry', []):
        for msg in entry.get('messaging', []):
            text = msg.get('message', {}).get('text', '').lower()
            sender = msg.get('sender', {}).get('id')
            if not sender or not text:
                continue
            if 'привет' in text:
                reply = 'Привет! Чем могу помочь?'
            elif 'цены' in text:
                reply = 'Наши цены: ...'
            else:
                reply = 'Не понял ваш запрос.'
            send_message(sender, reply)
    return 'OK', 200

def send_message(recipient_id, text):
    url = f'https://graph.facebook.com/v17.0/me/messages'
    params = {'access_token': ACCESS_TOKEN}
    payload = {
        'recipient': {'id': recipient_id},
        'message': {'text': text}
    }
    requests.post(url, params=params, json=payload)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
