"""
WhatsApp AI Bot — Green-API + Gemini Bridge
============================================
Production-ready version for Render.com FREE Web Service tier.
Uses the NEW google-genai package.

Requirements (requirements.txt):
    requests
    google-genai
    flask

Environment Variables (set in Render dashboard):
    GREEN_API_ID_INSTANCE
    GREEN_API_TOKEN_INSTANCE
    GEMINI_API_KEY
"""

import os
import requests
import time
import threading
from google import genai
from google.genai import types
from flask import Flask

# ─────────────────────────────────────────────
#  CONFIG — loaded from environment variables
# ─────────────────────────────────────────────
GREEN_API_ID_INSTANCE    = os.environ["GREEN_API_ID_INSTANCE"]
GREEN_API_TOKEN_INSTANCE = os.environ["GREEN_API_TOKEN_INSTANCE"]
GEMINI_API_KEY           = os.environ["GEMINI_API_KEY"]

# Bot personality
SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant. "
    "Keep replies concise and friendly. "
    "Use plain text — avoid markdown symbols like **, ##, or bullet dashes."
)

POLLING_INTERVAL = 3
# ─────────────────────────────────────────────


# ── Gemini setup ──────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)

# Conversation history per sender
conversations: dict[str, list] = {}


# ── Green-API helpers ─────────────────────────
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
        print(f"[send] -> {chat_id}: {text[:60]}...")
    except Exception as e:
        print(f"[send] Error: {e}")


# ── Gemini reply ──────────────────────────────
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

    # Keep last 20 messages only
    if len(history) > 20:
        conversations[sender_id] = history[-20:]

    return reply


# ── Main bot loop ─────────────────────────────
def main():
    print("WhatsApp-Gemini bot is running.")
    while True:
        notification = receive_notification()

        if notification:
            receipt_id = notification.get("receiptId")
            body = notification.get("body", {})
            type_webhook = body.get("typeWebhook")

            if type_webhook == "incomingMessageReceived":
                message_data = body.get("messageData", {})
                msg_type = message_data.get("typeMessage")

                if msg_type == "textMessage":
                    text_data = message_data.get("textMessageData", {})
                    user_text = text_data.get("textMessage", "").strip()
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


# ── Flask keeps Render free tier alive ───────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "WhatsApp-Gemini bot is running!", 200

@flask_app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = threading.Thread(target=main, daemon=True)
    bot_thread.start()

    # Use Render's PORT (default 10000)
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting Flask on port {port}")
    flask_app.run(host="0.0.0.0", port=port)
