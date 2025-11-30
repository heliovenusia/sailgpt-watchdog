import os
import time
from datetime import datetime, timedelta

import requests

URL = "https://sailgpt.tekdinext.com"
IST_OFFSET = timedelta(hours=5, minutes=30)
BASELINE_SIZE = 1145          # bytes
BASELINE_TIME = 0.21          # seconds
SIZE_LOW = 900                # GOOD if size in [SIZE_LOW, SIZE_HIGH]
SIZE_HIGH = 1400
SLOW_FACTOR = 2.0             # ABNORMAL if time > BASELINE_TIME * SLOW_FACTOR
SLOW_THRESHOLD = BASELINE_TIME * SLOW_FACTOR  # ~0.42s
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_IDS = [cid.strip() for cid in os.getenv("TG_CHAT_IDS", "").split(",") if cid.strip()]

def now_str():
    ist_time = datetime.utcnow() + IST_OFFSET
    return ist_time.strftime("%d %b %Y, %H:%M IST")

def classify(status_code, size_bytes, time_sec, error=None):
    """
    Returns (state, reason_tag) where state in {GOOD, ABNORMAL, DOWN}
    reason_tag: 'CONTENT', 'SLOW', 'ERROR'
    """
    if error is not None or status_code is None or status_code != 200:
        return "DOWN", "ERROR"

    # Status 200 = check size and time
    if size_bytes < SIZE_LOW or size_bytes > SIZE_HIGH:
        return "ABNORMAL", "CONTENT"

    if time_sec > SLOW_THRESHOLD:
        return "ABNORMAL", "SLOW"

    return "GOOD", None

def build_message(state, reason_tag, status_code, size_bytes, time_sec, error):
    ts = now_str()

    # Guard against None
    size_txt = f"{size_bytes} bytes" if size_bytes is not None else "N/A"
    time_txt = f"{time_sec:.3f} s" if time_sec is not None else "N/A"

    header = f"SAILGPT WatchDog: {state}"

    if state == "GOOD":
        lines = [
            header,
            "SailGPT is behaving normally.",
            f"Last check: {ts}",
            f"Response time: {time_txt} (normal ~{BASELINE_TIME:.2f} s)",
            f"Page size: {size_txt} (normal ~{BASELINE_SIZE} bytes)",
        ]
        return "  ".join(lines)

    if state == "ABNORMAL":
        if reason_tag == "CONTENT":
            if size_bytes and BASELINE_SIZE:
                pct = (size_bytes / BASELINE_SIZE) * 100
                pct_txt = f"{pct:.0f}% of normal"
            else:
                pct_txt = "unknown vs normal"

            lines = [
                "SAILGPT WatchDog: ABNORMAL (CONTENT)",
                "SailGPT is reachable, but the page content is unusual compared to normal.",
                f"Last check: {ts}",
                f"Page size: {size_txt} (normal ~{BASELINE_SIZE} bytes) = {pct_txt}.",
                "This may indicate an error page or backend issue. Please verify manually by logging in and sending a test prompt."
            ]
            return "  ".join(lines)

        if reason_tag == "SLOW":
            if time_sec and BASELINE_TIME:
                factor = time_sec / BASELINE_TIME
                factor_txt = f"{factor:.1f}X slower than normal"
            else:
                factor_txt = "slower than normal"

            lines = [
                "SAILGPT WatchDog: ABNORMAL (SLOW)",
                "SailGPT is reachable, but slower than usual.",
                f"Last check: {ts}",
                f"Response time: {time_txt} (normal ~{BASELINE_TIME:.2f} s) = {factor_txt}.",
                f"Page size: {size_txt} (normal ~{BASELINE_SIZE} bytes).",
                "System is up, but performance is degraded. May please monitor and escalate if users report issues."
            ]
            return "  ".join(lines)

        # Fallback ABNORMAL
        lines = [
            "SAILGPT WatchDog: ABNORMAL",
            "SailGPT is reachable, but behaviour is unusual.",
            f"Last check: {ts}",
            f"Status code: {status_code}",
            f"Response time: {time_txt}",
            f"Page size: {size_txt}",
            "Please verify manually."
        ]
        return "  ".join(lines)

    # DOWN
    err_txt = error if error else f"HTTP {status_code}" if status_code is not None else "Unknown error"
    lines = [
        "SAILGPT WatchDog: DOWN",
        "SailGPT is not reachable.",
        f"Last check: {ts}",
        f"Error: {err_txt}.",
        "This indicates an outage at the portal/infra level.",
    ]
    return "  ".join(lines)

def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT_IDS:
        print("WARNING: Telegram not configured (TG_TOKEN/TG_CHAT_IDS missing).", flush=True)
        return

    base_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for cid in TG_CHAT_IDS:
        try:
            resp = requests.get(
                base_url,
                params={"chat_id": cid, "text": message},
                timeout=5,
            )
            
        except Exception as e:
            print(f"WARNING: Telegram send failed for {cid}: {e}", flush=True)



def main():
    status_code = None
    size_bytes = None
    time_sec = None
    error = None

    try:
        start = time.time()
        resp = requests.get(URL, timeout=10)
        time_sec = time.time() - start
        status_code = resp.status_code
        size_bytes = len(resp.content)
    except Exception as e:
        error = str(e)

    state, reason_tag = classify(status_code, size_bytes, time_sec, error)
    message = build_message(state, reason_tag, status_code, size_bytes, time_sec, error)

   
    print(message)
    print("  ") 
    print(f"STATE: {state}")

    if state != "GOOD":
        send_telegram(message)
    

if __name__ == "__main__":
    main()
