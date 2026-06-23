import json
import logging
import os
import hashlib
import hmac
from datetime import datetime, time
from typing import Optional

import pytz
import requests
from flask import Flask, request, jsonify, abort

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("BOT_CONFIG", "config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", CONFIG["facebook"]["page_access_token"])
VERIFY_TOKEN = os.environ.get("FB_VERIFY_TOKEN", CONFIG["facebook"]["verify_token"])
APP_SECRET = os.environ.get("FB_APP_SECRET", CONFIG["facebook"]["app_secret"])

GRAPH_API_URL = "https://graph.facebook.com/v18.0/me/messages"

WEEKDAY_MAP = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _tz() -> pytz.BaseTzInfo:
    return pytz.timezone(CONFIG.get("timezone", "America/Sao_Paulo"))


def _now() -> datetime:
    return datetime.now(_tz())


def is_open(at: Optional[datetime] = None) -> bool:
    at = at or _now()
    day_key = WEEKDAY_MAP[at.weekday()]
    day_cfg = CONFIG["schedule"].get(day_key, {})
    if not day_cfg.get("open"):
        return False
    start = time.fromisoformat(day_cfg["start"])
    end = time.fromisoformat(day_cfg["end"])
    return start <= at.time() <= end


def next_opening() -> str:
    """Return a human-readable string for the next opening time."""
    from datetime import timedelta
    now = _now()
    for offset in range(1, 8):
        candidate = now + timedelta(days=offset)
        day_key = WEEKDAY_MAP[candidate.weekday()]
        day_cfg = CONFIG["schedule"].get(day_key, {})
        if day_cfg.get("open"):
            day_names = {
                "monday": "Segunda-feira", "tuesday": "Terça-feira",
                "wednesday": "Quarta-feira", "thursday": "Quinta-feira",
                "friday": "Sexta-feira", "saturday": "Sábado",
                "sunday": "Domingo",
            }
            return f"{day_names[day_key]} às {day_cfg['start']}"
    return "em breve"


# ---------------------------------------------------------------------------
# FAQ matcher
# ---------------------------------------------------------------------------

def match_faq(text: str) -> Optional[str]:
    text_lower = text.lower()
    for topic, data in CONFIG["faq"].items():
        if any(kw in text_lower for kw in data["keywords"]):
            return data["answer"]
    return None


# ---------------------------------------------------------------------------
# Facebook Messenger API
# ---------------------------------------------------------------------------

def send_message(recipient_id: str, text: str) -> bool:
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        resp = requests.post(GRAPH_API_URL, json=payload, params=params, timeout=10)
        resp.raise_for_status()
        logger.info("Message sent to %s", recipient_id)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send message to %s: %s", recipient_id, exc)
        return False


def get_user_name(user_id: str) -> str:
    try:
        resp = requests.get(
            f"https://graph.facebook.com/v18.0/{user_id}",
            params={"fields": "first_name", "access_token": PAGE_ACCESS_TOKEN},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("first_name", "")
    except requests.RequestException:
        return ""


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

def handle_message(sender_id: str, message_text: str) -> None:
    name = get_user_name(sender_id)
    business = CONFIG["business"]["name"]
    phone = CONFIG["business"]["phone"]
    messages_cfg = CONFIG["messages"]

    if is_open():
        faq_answer = match_faq(message_text)
        if faq_answer:
            send_message(sender_id, faq_answer)
        else:
            # First contact greeting + fallback
            greeting = messages_cfg["greeting_open"].format(name=name, business=business)
            send_message(sender_id, greeting)
            fallback = messages_cfg["faq_not_found"].format(phone=phone)
            send_message(sender_id, fallback)
    else:
        faq_answer = match_faq(message_text)
        if faq_answer:
            # Answer the FAQ but also inform about hours
            send_message(sender_id, faq_answer)
            outside = messages_cfg["outside_hours_reply"].format(next_open=next_opening())
            send_message(sender_id, outside)
        else:
            closed = messages_cfg["greeting_closed"].format(name=name, business=business)
            send_message(sender_id, closed)


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(payload: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header[7:])


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return challenge, 200

    logger.warning("Webhook verification failed")
    abort(403)


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    signature = request.headers.get("X-Hub-Signature-256", "")
    if APP_SECRET and APP_SECRET != "SEU_APP_SECRET_AQUI":
        if not verify_signature(request.get_data(), signature):
            logger.warning("Invalid signature — request rejected")
            abort(403)

    data = request.get_json(silent=True)
    if not data or data.get("object") != "page":
        return jsonify({"status": "ignored"}), 200

    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            message = event.get("message", {})

            # Ignore echo messages sent by the page itself
            if message.get("is_echo"):
                continue

            text = message.get("text", "").strip()
            if sender_id and text:
                logger.info("Received from %s: %s", sender_id, text)
                handle_message(sender_id, text)

    return jsonify({"status": "ok"}), 200


@app.route("/status", methods=["GET"])
def status():
    now = _now()
    return jsonify({
        "business": CONFIG["business"]["name"],
        "is_open": is_open(),
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "next_opening": None if is_open() else next_opening(),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting bot on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
