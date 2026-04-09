import os
import requests
import time
import threading
from google import genai
from google.genai import types
from flask import Flask

GREEN_API_ID_INSTANCE    = os.environ["GREEN_API_ID_INSTANCE"]
GREEN_API_TOKEN_INSTANCE = os.environ["GREEN_API_TOKEN_INSTANCE"]
GEMINI_API_KEY           = os.environ["GEMINI_API_KEY"]

SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant. "
    "Keep replies concise and friendly. "
    "Use plain text only, no markdown."
)

POLLING_INTERVAL = 3

client = genai.Client(api_key=GEMINI_API_KEY)
conversations = {}
BASE_URL = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}"


def receive_notification():
    url = f"{BASE_URL}/receiveNotification/{GREEN_API_TOKEN_INSTANCE}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data if data else None
    except Exception as e:
        print(f"[receive] Error: {e}")
        return None


def delete_notification(receipt_id):
    url = f"{BASE_URL}/deleteNotification/{GREEN_API_TOKEN_INSTANCE}/{receipt_id}"
    try:
        requests.delete(url, timeout=10)
    except Exception as e:
        print(f"[delete] Error: {e}")


def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage/{GREEN_API_TOKEN_INSTANCE}"
    payload = {"chatId": chat_id, "message": text}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"[send] -> {chat_id}: {text[:60]}")
    except Exception as e:
        print(f"[send] Error: {e}")


def get_gemini_reply(sender_id, user_message):
    history = conversations.setdefault(sender_id, [])
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=history,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        reply = response.text.strip()
    except Exception as e:
        print(f"[gemini] Error: {e}")
        history.pop()
        return "Sorry, I could not process that. Please try again."
    history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
    if len(history) > 20:
        conversations[sender_id] = history[-20:]
    return reply


def bot_loop():
    print("Bot polling started.")
    while True:
        notification = receive_notification()
        if notification:
            receipt_id = notification.get("receiptId")
            body = notification.get("body", {})
            if body.get("typeWebhook") == "incomingMessageReceived":
                message_data = body.get("messageData", {})
                if message_data.get("typeMessage") == "textMessage":
                    user_text = message_data.get("textMessageData", {}).get("textMessage", "").strip()
                    sender_data = body.get("senderData", {})
                    chat_id = sender_data.get("chatId", "")
                    sender_name = sender_data.get("senderName", "User")
                    if user_text and chat_id:
                        print(f"[recv] {sender_name}: {user_text}")
                        reply = get_gemini_reply(chat_id, user_text)
                        send_message(chat_id, reply)
            if receipt_id:
                delete_notification(receipt_id)
        time.sleep(POLLING_INTERVAL)


# Start bot thread when module loads (works with gunicorn)
t = threading.Thread(target=bot_loop, daemon=True)
t.start()

# Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "WhatsApp Gemini Bot is running!", 200

@app.route("/health")
def health():
    return "OK", 200
