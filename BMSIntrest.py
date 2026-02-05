
#!/usr/bin/env python3

import os
import re
import json
import time
import random
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# =================================================
# CONFIG
# =================================================
IST = timezone(timedelta(hours=5, minutes=30))

BMS_URL = "https://in.bookmyshow.com/movies/vijayawada/varanasi/ET00471138"
MOVIE_CODE = "ET00471138"

BASE_FOLDER = "data"
EVENT_FILE = os.path.join(BASE_FOLDER, f"{MOVIE_CODE}.json")

MAX_RETRIES = 5
BASE_DELAY = 2.0  # seconds

os.makedirs(BASE_FOLDER, exist_ok=True)

# =================================================
# HELPERS
# =================================================
def ist_now_iso():
    return datetime.now(IST).isoformat(timespec="minutes")


def get_random_ip():
    return ".".join(str(random.randint(1, 255)) for _ in range(4))


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_interested(text: str) -> int:
    """
    Converts:
    '64.6K+ are interested' → 64600
    """
    text = text.replace(",", "").upper()

    m = re.search(r"(\d+(\.\d+)?)\s*K\+?\s*ARE\s*INTERESTED", text)
    if not m:
        raise ValueError("Interested pattern not found")

    return int(round(float(m.group(1)) * 1000))


def get_last_interest(history: dict):
    if not history:
        return None
    return history[max(history.keys())]


# =================================================
# USER AGENTS + HEADERS
# =================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{m}_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64; rv:{r}) Gecko/20100101 Firefox/{r}",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS).format(
        v=f"{random.randint(90,120)}.0.{random.randint(1000,5000)}.{random.randint(0,150)}",
        m=random.randint(12, 15),
        r=random.randint(90,120),
    )


def get_headers():
    ip = get_random_ip()
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": "https://in.bookmyshow.com",
        "Referer": "https://in.bookmyshow.com/",
        "X-Forwarded-For": ip,
        "Client-IP": ip,
    }

# =================================================
# SCRAPER WITH RETRY
# =================================================
def scrape_bms_interest():
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = get_headers()
            sleep_time = BASE_DELAY * attempt + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

            res = scraper.get(BMS_URL, headers=headers, timeout=15)

            if res.status_code in (403, 429):
                raise RuntimeError(f"Blocked (HTTP {res.status_code})")

            res.raise_for_status()

            soup = BeautifulSoup(res.text, "html.parser")

            # 🎯 STRICT SEARCH
            for el in soup.find_all(["div", "span", "p"]):
                text = el.get_text(" ", strip=True)
                if "are interested" in text.lower():
                    return text

            raise ValueError("Interested text not found")

        except Exception as e:
            last_error = e
            print(
                f"[RETRY {attempt}/{MAX_RETRIES}] "
                f"{type(e).__name__}: {e}"
            )

    raise RuntimeError(f"All retries failed: {last_error}")

# =================================================
# MAIN
# =================================================
def run():
    timestamp = ist_now_iso()

    try:
        raw_text = scrape_bms_interest()
        interested = parse_interested(raw_text)

        data = load_json(EVENT_FILE, {
            "eventCode": MOVIE_CODE,
            "source": "BookMyShow",
            "timezone": "Asia/Kolkata",
            "last_updated": None,
            "history": {}
        })

        history = data.get("history", {})

        last_value = get_last_interest(history)

        # 🔁 ALWAYS update last_updated
        data["last_updated"] = timestamp

        # 🔒 Skip history write if unchanged
        if last_value == interested:
            save_json(EVENT_FILE, data)
            print(
                f"[SKIP] {MOVIE_CODE} | Interest unchanged ({interested}) | "
                f"last_updated set to {timestamp}"
            )
            return

        # 🔒 Prevent overwrite of same timestamp
        if timestamp in history:
            save_json(EVENT_FILE, data)
            print(
                f"[SKIP] {MOVIE_CODE} | Timestamp exists | "
                f"last_updated set to {timestamp}"
            )
            return

        # ✅ SAVE NEW VALUE
        history[timestamp] = interested
        data["history"] = history

        save_json(EVENT_FILE, data)

        print(
            f"[OK] {MOVIE_CODE} | Interested: {interested} | "
            f"IST {timestamp}"
        )

    except Exception as e:
        print("[ERROR] SCRAPE_FAILED:", e)


if __name__ == "__main__":
    run()
