from flask import Flask, request
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

@app.route('/webhook', methods=['GET'])
def verify():
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    print(f"[WEBHOOK VERIFY] mode={mode}, token={token}, challenge={challenge}")
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("[WEBHOOK VERIFY] OK", data, flush=True)
        return challenge, 200

    print("[WEBHOOK VERIFY] FAILED", data, flush=True)
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("[WEBHOOK PAYLOAD]", data, flush=True)

    for entry in data.get('entry', []):
        for msg in entry.get('messaging', []):
            sender = msg.get('sender', {}).get('id')
            text   = msg.get('message', {}).get('text', '')

            print(f"[INCOMING] from={sender} text={text!r}")

            reply = None
            txt = text.lower()
            if 'привет' in txt:
                reply = 'Привет! Чем могу помочь?'
            elif 'цены' in txt:
                reply = 'Наши цены: …'
            # elif ... добавьте свои ключевые слова

            if reply:
                print(f"[REPLY] to={sender} text={reply!r}")
                resp = send_message(sender, reply)
                print(f"[FB RESP] status={resp.status_code} body={resp.text}")

    return 'OK', 200

def send_message(recipient_id, text):
    url = 'https://graph.facebook.com/v17.0/me/messages'
    params = {'access_token': ACCESS_TOKEN}
    payload = {
        'recipient': {'id': recipient_id},
        'message': {'text': text}
    }
    return requests.post(url, params=params, json=payload)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
