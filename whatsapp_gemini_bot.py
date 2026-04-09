"""
WhatsApp AI Bot — Green-API + Gemini Bridge
============================================
Production-ready version for deployment on Render.com

Requirements (requirements.txt):
    requests
    google-generativeai

Environment Variables (set in Render dashboard):
    GREEN_API_ID_INSTANCE
    GREEN_API_TOKEN_INSTANCE
    GEMINI_API_KEY
"""

import os
import requests
import time
import google.generativeai as genai

# ─────────────────────────────────────────────
#  CONFIG — loaded from environment variables
# ─────────────────────────────────────────────
GREEN_API_ID_INSTANCE    = os.environ["GREEN_API_ID_INSTANCE"]
GREEN_API_TOKEN_INSTANCE = os.environ["GREEN_API_TOKEN_INSTANCE"]
GEMINI_API_KEY           = os.environ["GEMINI_API_KEY"]

# Optional: Give your bot a personality
SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant. "
    "Keep replies concise and friendly. "
    "Use plain text — avoid markdown symbols like **, ##, or bullet dashes."
)

# How long to wait between polling for new messages (seconds)
POLLING_INTERVAL = 3
# ─────────────────────────────────────────────


# ── Gemini setup ──────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_PROMPT,
)

# In-memory conversation history per sender
# Format: { "2348012345678@c.us": [{"role": ..., "parts": [...]}] }
conversations: dict[str, list] = {}


# ── Green-API helpers ─────────────────────────
BASE_URL = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}"


def receive_notification() -> dict | None:
    """Pull one notification from the Green-API queue."""
    url = f"{BASE_URL}/receiveNotification/{GREEN_API_TOKEN_INSTANCE}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data if data else None
    except Exception as e:
        print(f"[receive] Error: {e}")
        return None


def delete_notification(receipt_id: int) -> None:
    """Acknowledge (delete) a processed notification so it won't repeat."""
    url = f"{BASE_URL}/deleteNotification/{GREEN_API_TOKEN_INSTANCE}/{receipt_id}"
    try:
        requests.delete(url, timeout=10)
    except Exception as e:
        print(f"[delete] Error: {e}")


def send_message(chat_id: str, text: str) -> None:
    """Send a text message to a WhatsApp chat."""
    url = f"{BASE_URL}/sendMessage/{GREEN_API_TOKEN_INSTANCE}"
    payload = {"chatId": chat_id, "message": text}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"[send] → {chat_id}: {text[:60]}...")
    except Exception as e:
        print(f"[send] Error: {e}")


# ── Gemini reply ──────────────────────────────
def get_gemini_reply(sender_id: str, user_message: str) -> str:
    """Send message to Gemini, keeping per-sender conversation history."""
    history = conversations.setdefault(sender_id, [])

    # Add the user's new message to history
    history.append({"role": "user", "parts": [user_message]})

    try:
        chat = model.start_chat(history=history[:-1])  # history before this turn
        response = chat.send_message(user_message)
        reply = response.text.strip()
    except Exception as e:
        print(f"[gemini] Error: {e}")
        reply = "Sorry, I ran into a problem. Please try again."

    # Save the assistant reply to history
    history.append({"role": "model", "parts": [reply]})

    # Keep history from growing too large (last 20 turns = 10 exchanges)
    if len(history) > 20:
        conversations[sender_id] = history[-20:]

    return reply


# ── Main loop ─────────────────────────────────
def main():
    print("✅ WhatsApp-Gemini bot is running. Press Ctrl+C to stop.\n")
    while True:
        notification = receive_notification()

        if notification:
            receipt_id = notification.get("receiptId")
            body = notification.get("body", {})
            type_webhook = body.get("typeWebhook")

            # We only care about incoming text messages
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
                        print(f"[recv] {sender_name} ({chat_id}): {user_text}")
                        reply = get_gemini_reply(chat_id, user_text)
                        send_message(chat_id, reply)

            # Always delete the notification after processing
            if receipt_id:
                delete_notification(receipt_id)

        time.sleep(POLLING_INTERVAL)


if __name__ == "__main__":
    main()
