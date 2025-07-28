from flask import Flask, request
import os
import requests

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "your_verify_token")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "your_page_access_token")

@app.route("/webhook", methods=["GET"])
def verify():
    # Проверка для Meta (Instagram/Facebook)
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print("Received POST:", data)  # для отладки

    if data.get("object") == "instagram":
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging["sender"]["id"]
                if "message" in messaging:
                    text = messaging["message"].get("text", "")
                    reply_text = handle_message(text)
                    send_reply(sender_id, reply_text)
    return "OK", 200

def handle_message(text):
    # Здесь можешь использовать Gemini или ChatGPT
    return "Salom! Sizning savolingiz: " + text

def send_reply(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
