import json
import logging
import os
import time
import random
from datetime import datetime
from typing import Optional

import pytz
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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

FB_EMAIL    = os.environ.get("FB_EMAIL",    CONFIG["facebook"]["email"])
FB_PASSWORD = os.environ.get("FB_PASSWORD", CONFIG["facebook"]["password"])

WEEKDAY_MAP = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Tracks which conversations already received a reply in this session
replied_ids: set[str] = set()


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _tz() -> pytz.BaseTzInfo:
    return pytz.timezone(CONFIG.get("timezone", "America/Sao_Paulo"))


def _now() -> datetime:
    return datetime.now(_tz())


def is_open(at: Optional[datetime] = None) -> bool:
    from datetime import time as dtime
    at = at or _now()
    day_key = WEEKDAY_MAP[at.weekday()]
    day_cfg = CONFIG["schedule"].get(day_key, {})
    if not day_cfg.get("open"):
        return False
    start = dtime.fromisoformat(day_cfg["start"])
    end   = dtime.fromisoformat(day_cfg["end"])
    return start <= at.time() <= end


def next_opening() -> str:
    from datetime import timedelta
    now = _now()
    day_names = {
        "monday": "Segunda-feira", "tuesday": "Terça-feira",
        "wednesday": "Quarta-feira", "thursday": "Quinta-feira",
        "friday": "Sexta-feira", "saturday": "Sábado", "sunday": "Domingo",
    }
    for offset in range(1, 8):
        candidate = now + timedelta(days=offset)
        day_key = WEEKDAY_MAP[candidate.weekday()]
        day_cfg = CONFIG["schedule"].get(day_key, {})
        if day_cfg.get("open"):
            return f"{day_names[day_key]} às {day_cfg['start']}"
    return "em breve"


# ---------------------------------------------------------------------------
# FAQ matcher
# ---------------------------------------------------------------------------

def match_faq(text: str) -> Optional[str]:
    text_lower = text.lower()
    for _topic, data in CONFIG["faq"].items():
        if any(kw in text_lower for kw in data["keywords"]):
            return data["answer"]
    return None


def build_reply(last_message: str, sender_name: str) -> str:
    business = CONFIG["business"]["name"]
    phone    = CONFIG["business"]["phone"]
    msgs     = CONFIG["messages"]

    faq_answer = match_faq(last_message)

    if is_open():
        if faq_answer:
            return faq_answer
        greeting = msgs["greeting_open"].format(name=sender_name, business=business)
        fallback  = msgs["faq_not_found"].format(phone=phone)
        return f"{greeting}\n\n{fallback}"
    else:
        if faq_answer:
            outside = msgs["outside_hours_reply"].format(next_open=next_opening())
            return f"{faq_answer}\n\n{outside}"
        return msgs["greeting_closed"].format(name=sender_name, business=business)


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def _human_delay(min_s: float = 0.8, max_s: float = 2.2) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _type_humanlike(element, text: str) -> None:
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.12))


def create_driver() -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if CONFIG.get("headless"):
        options.add_argument("--headless=new")
    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 900)
    return driver


def login(driver: uc.Chrome) -> None:
    logger.info("Logging in to Facebook...")
    driver.get("https://www.facebook.com/login")
    wait = WebDriverWait(driver, 20)

    email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
    _human_delay()
    _type_humanlike(email_field, FB_EMAIL)

    pass_field = driver.find_element(By.ID, "pass")
    _human_delay(0.5, 1.0)
    _type_humanlike(pass_field, FB_PASSWORD)

    _human_delay()
    pass_field.send_keys(Keys.RETURN)

    # Wait for home feed to confirm login
    wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='feed'] | //div[@data-pagelet='LeftRail']")))
    logger.info("Login successful")
    _human_delay(2, 4)


def open_marketplace_inbox(driver: uc.Chrome) -> None:
    driver.get("https://www.facebook.com/marketplace/inbox")
    _human_delay(3, 5)


# ---------------------------------------------------------------------------
# Conversation processing
# ---------------------------------------------------------------------------

def get_conversations(driver: uc.Chrome) -> list:
    """Return list of conversation elements in the inbox sidebar."""
    try:
        return driver.find_elements(
            By.XPATH,
            "//div[@role='row'] | //a[contains(@href,'/marketplace/t/')]"
        )
    except Exception:
        return []


def get_last_message_and_sender(driver: uc.Chrome) -> tuple[str, str]:
    """
    After clicking a conversation, extract the last received message text
    and the sender's name from the chat thread.
    Returns (message_text, sender_name).
    """
    wait = WebDriverWait(driver, 10)
    try:
        # Wait for message bubbles to load
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[@data-scope='messages_table']//div[@dir='auto']")
        ))
    except TimeoutException:
        return "", ""

    # Grab all message rows
    rows = driver.find_elements(
        By.XPATH,
        "//div[@data-scope='messages_table']//div[@dir='auto']"
    )
    if not rows:
        return "", ""

    last_text = rows[-1].text.strip()

    # Try to get sender name from the conversation header
    sender_name = ""
    try:
        header = driver.find_element(
            By.XPATH,
            "//h2 | //span[@dir='auto'][contains(@class,'x1lliihq')]"
        )
        sender_name = header.text.strip().split("\n")[0]
    except NoSuchElementException:
        pass

    return last_text, sender_name


def is_last_message_mine(driver: uc.Chrome) -> bool:
    """
    Returns True if the last bubble in the conversation was sent by us
    (i.e., it appears on the right side / has outgoing class).
    """
    try:
        outgoing = driver.find_elements(
            By.XPATH,
            "//div[@data-scope='messages_table']//*[contains(@class,'x1n2onr6')]//div[@dir='auto']"
        )
        all_msgs = driver.find_elements(
            By.XPATH,
            "//div[@data-scope='messages_table']//div[@dir='auto']"
        )
        if not all_msgs or not outgoing:
            return False
        return all_msgs[-1].text.strip() == outgoing[-1].text.strip()
    except Exception:
        return False


def send_reply(driver: uc.Chrome, text: str) -> bool:
    wait = WebDriverWait(driver, 10)
    try:
        box = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='textbox'][@contenteditable='true']")
        ))
        box.click()
        _human_delay(0.5, 1.0)

        # Send line by line (SHIFT+ENTER for newlines)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            _type_humanlike(box, line)
            if i < len(lines) - 1:
                box.send_keys(Keys.SHIFT, Keys.RETURN)

        _human_delay(0.8, 1.5)
        box.send_keys(Keys.RETURN)
        logger.info("Reply sent")
        return True
    except (TimeoutException, Exception) as exc:
        logger.error("Failed to send reply: %s", exc)
        return False


def get_conversation_id(driver: uc.Chrome) -> str:
    """Use current URL as a stable conversation identifier."""
    return driver.current_url


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def process_inbox(driver: uc.Chrome) -> None:
    open_marketplace_inbox(driver)
    conversations = get_conversations(driver)
    logger.info("Found %d conversation(s)", len(conversations))

    for i in range(len(conversations)):
        try:
            # Re-fetch list (DOM may have changed)
            conversations = get_conversations(driver)
            if i >= len(conversations):
                break

            conv = conversations[i]
            conv.click()
            _human_delay(2, 4)

            conv_id = get_conversation_id(driver)
            if conv_id in replied_ids:
                logger.info("Already replied to %s — skipping", conv_id)
                continue

            if is_last_message_mine(driver):
                logger.info("Last message is mine in %s — skipping", conv_id)
                replied_ids.add(conv_id)
                continue

            last_msg, sender = get_last_message_and_sender(driver)
            if not last_msg:
                logger.info("No message text found — skipping")
                continue

            logger.info("Conversation %s | Sender: %s | Message: %s", conv_id, sender, last_msg)

            reply = build_reply(last_msg, sender)
            if send_reply(driver, reply):
                replied_ids.add(conv_id)

            _human_delay(3, 6)

        except Exception as exc:
            logger.error("Error processing conversation %d: %s", i, exc)
            continue


def run() -> None:
    check_interval = CONFIG.get("check_interval_seconds", 60)
    driver = create_driver()
    try:
        login(driver)
        while True:
            logger.info("Checking inbox...")
            try:
                process_inbox(driver)
            except Exception as exc:
                logger.error("Inbox check error: %s", exc)
                # Attempt to recover by reloading
                try:
                    driver.get("https://www.facebook.com/marketplace/inbox")
                    _human_delay(5, 8)
                except Exception:
                    pass

            logger.info("Sleeping %ds before next check...", check_interval)
            time.sleep(check_interval)
    finally:
        driver.quit()


if __name__ == "__main__":
    run()
