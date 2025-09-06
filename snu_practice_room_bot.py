# snu_practice_room_bot.py
from datetime import datetime, timedelta, timezone
import time
import os
import sys
import random

# --- Make stdout/stderr UTF-8 and never crash on weird chars ---
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from selenium import webdriver
from selenium.common.exceptions import (
    WebDriverException,
    StaleElementReferenceException,
    NoSuchElementException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ---------- CONFIG ----------
PROFILE_DIR = r"C:\SNU_Booker\chrome_snu_profile"
START_URL = "https://ssims.snu.ac.kr/"

# Run only on WEEKDAYS (0=Mon ... 6=Sun)
BOOK_DAYS = {0, 1, 2, 3, 4}

CLICK_PAUSE = 1.5
CALENDAR_WAIT = 20
RES_BUTTON_WAIT = 4
FORM_WAIT = 10
DEBUG = True

# Optional: auto-fill these ONLY if blank
OPTIONAL_PHONE = ""        # e.g. "01012345678"
OPTIONAL_EMAIL = ""        # e.g. "you@snu.ac.kr"

# ---------- TIMEZONE: use Korea time regardless of host PC ----------
KST = timezone(timedelta(hours=9))
def now_kst():
    return datetime.now(tz=timezone.utc).astimezone(KST)

# ---------- TIME CONFIG (per weekday) ----------
# 0=Mon ... 6=Sun   ->  (start_hour, start_min, end_hour, end_min)
TIME_CONFIG = {
    0: ("19", "00", "20", "00"),  # Mon
    1: ("13", "00", "14", "00"),  # Tue
    2: ("19", "00", "20", "00"),  # Wed
    3: ("13", "00", "14", "30"),  # Thu
    4: ("14", "00", "16", "00"),  # Fri
    # Weekends present for completeness; they won't run due to BOOK_DAYS guard:
    5: ("08", "30", "09", "30"),  # Sat
    6: ("14", "00", "15", "00"),  # Sun
}
DEFAULT_TIMES = ("07", "00", "08", "00")

# ---------- ROOM PRIORITY (per weekday) ----------
ROOM_PRIORITY = {
    0: ["311", "302", "318", "303", "305", "304"],  # Mon
    1: ["302", "311", "318", "303", "305", "304"],  # Tue
    2: ["302", "311", "318", "303", "305", "304"],  # Wed
    3: ["302", "311", "318", "303", "305", "304"],  # Thu
    4: ["311", "302", "318", "303", "305", "304"],  # Fri
    # Sat/Sun entries are fine; will be skipped by BOOK_DAYS guard:
    5: ["302", "311", "318", "303", "305", "304"],
    6: ["311", "302", "318", "303", "305", "304"],
}
ROOM_SELECTORS = {
    "311": "#S_SPACE_CD > ul > li:nth-child(12)",
    "302": "#S_SPACE_CD > ul > li:nth-child(8)",
    "318": "#S_SPACE_CD > ul > li:nth-child(13)",
    "303": "#S_SPACE_CD > ul > li:nth-child(9)",
    "304": "#S_SPACE_CD > ul > li:nth-child(10)",
    "305": "#S_SPACE_CD > ul > li:nth-child(11)",
}

# ---------- BROWSER ----------
def build_driver(headless=False):
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    # Use Selenium Manager (built-in)
    return webdriver.Chrome(options=options)

# ---------- UTILS ----------
def log(step):
    try:
        print(step, flush=True)
    except UnicodeEncodeError:
        try:
            print(step.encode("utf-8", "ignore").decode("ascii", "ignore"), flush=True)
        except Exception:
            print("[LOG] (unprintable message)", flush=True)

def wait_for_idle(driver, timeout=20):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")

def wait_find_css(driver, css, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

def wait_click_css(driver, css, timeout=20, retries=4, post_pause=CLICK_PAUSE):
    """
    Resilient click helper:
    - waits for clickable
    - scrolls into view
    - tiny random pause to avoid race
    - JS-click fallback
    - retries on stale / transient WebDriver errors
    """
    last_err = None
    for _ in range(retries):
        try:
            el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.12 + random.random() * 0.25)
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(post_pause)
            return el
        except (StaleElementReferenceException, NoSuchElementException, WebDriverException) as e:
            last_err = e
            time.sleep(0.5 + random.random() * 0.4)
    raise last_err

def type_text_css(driver, css, text, clear_first=True, timeout=20):
    el = wait_find_css(driver, css, timeout=timeout)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        if clear_first:
            el.clear()
    except Exception:
        pass
    el.send_keys(text)
    time.sleep(CLICK_PAUSE)
    return el

def dump_debug(driver, tag="debug"):
    ts = now_kst().strftime("%Y%m%d_%H%M%S")
    png = f"snu_bot_{tag}_{ts}.png"
    html = f"snu_bot_{tag}_{ts}.html"
    try:
        driver.save_screenshot(png)
    except Exception:
        pass
    try:
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception:
        pass
    try:
        print(f"[DEBUG] Saved debug artifacts: {png} and {html}")
    except Exception:
        print("[DEBUG] Artifacts saved.")

def body_contains_text(driver, txt):
    try:
        return bool(driver.execute_script(
            "return (document.body && document.body.innerText && document.body.innerText.indexOf(arguments[0]) !== -1);",
            txt
        ))
    except Exception:
        return False

def wait_for_text_present(driver, txt, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        if body_contains_text(driver, txt):
            return True
        time.sleep(0.2)
    return False

# ---------- DATEPICKER (ROBUST, WITH HEADER LOGGING) ----------
_MONTH_ABBR_MAP = {
    # Handles three-letter caps + the special "Sept"
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def _read_dp_year_month(driver):
    """Return (year, month_int) and print the header raw text that the widget shows."""
    wait_find_css(driver, "#ui-datepicker-div", timeout=20)

    # Raw header elements (as you described)
    mo_el = driver.find_element(By.CSS_SELECTOR, "#ui-datepicker-div > div > div > span.ui-datepicker-month")
    yr_el = driver.find_element(By.CSS_SELECTOR, "#ui-datepicker-div > div > div > span.ui-datepicker-year")

    mo_raw = (mo_el.text or "").strip()   # e.g., "Aug" or "Sept" (title-cased)
    yr_raw = (yr_el.text or "").strip()   # e.g., "2025"

    # Log raw header text
    log(f"[datepicker] header raw -> month='{mo_raw}', year='{yr_raw}'")

    # Parse year
    try:
        year = int(''.join(ch for ch in yr_raw if ch.isdigit()))
    except Exception:
        year = now_kst().year

    # Parse month from abbr map; also handle numeric like '9' or '9월'
    month = None
    if mo_raw in _MONTH_ABBR_MAP:
        month = _MONTH_ABBR_MAP[mo_raw]
    else:
        # numeric fallback
        digits = ''.join(ch for ch in mo_raw if ch.isdigit())
        if digits:
            try:
                month = int(digits)
            except Exception:
                month = now_kst().month
        else:
            # last resort
            month = now_kst().month

    # Log parsed result
    log(f"[datepicker] parsed -> {year}-{month:02d}")
    return year, month

def pick_date_with_rules(driver, today, target_date):
    """
    Robust: normalize the datepicker to the target year/month by reading its header
    and clicking prev/next until it matches, then click the target day by text.
    Also prints what header it reads before/after normalization.
    """
    wait_find_css(driver, "#ui-datepicker-div", timeout=20)

    ty, tm = target_date.year, target_date.month
    # First read/log what's showing initially
    cy, cm = _read_dp_year_month(driver)
    log(f"[datepicker] showing {cy}-{cm:02d}, target {ty}-{tm:02d}")

    max_steps = 14  # safety bound across multi-month drift
    steps = 0
    while (cy, cm) != (ty, tm) and steps < max_steps:
        # Decide direction
        if (cy < ty) or (cy == ty and cm < tm):
            # click next month
            wait_click_css(driver, "#ui-datepicker-div .ui-datepicker-next", timeout=5, post_pause=0.25)
        else:
            # click prev month
            wait_click_css(driver, "#ui-datepicker-div .ui-datepicker-prev", timeout=5, post_pause=0.25)
        time.sleep(0.15)
        cy, cm = _read_dp_year_month(driver)  # read after each nav
        steps += 1

    if (cy, cm) != (ty, tm):
        log("[datepicker] Could not fully align month/year after several steps; proceeding best-effort.")

    # Final state before selecting day
    log(f"[datepicker] final calendar -> {cy}-{cm:02d}, selecting day {target_date.day}")

    # Click the exact day number in the (aligned) month
    _click_day_by_text(driver, target_date.day)

def _click_day_by_text(driver, day_int):
    day_xpath = ("//div[@id='ui-datepicker-div']"
                 "//td[not(contains(@class,'ui-datepicker-other-month'))]"
                 f"/a[normalize-space()='{day_int}']")
    el = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, day_xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)
    time.sleep(CLICK_PAUSE)

# ---------- MODAL / IFRAME AWARE WAIT ----------
def find_visible_modal_root(driver):
    for sel in ["div[role='dialog']", ".ui-dialog", ".modal", ".swal2-container"]:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if el.is_displayed():
                    return el
            except Exception:
                continue
    return None

def switch_into_iframe_if_any(driver, container):
    try:
        if not container:
            return False
        for fr in container.find_elements(By.TAG_NAME, "iframe"):
            if fr.is_displayed():
                driver.switch_to.frame(fr)
                return True
    except Exception:
        pass
    return False

def wait_for_calendar_render(driver, timeout=CALENDAR_WAIT):
    end = time.time() + timeout
    tried_iframe = False
    while time.time() < end:
        modal = find_visible_modal_root(driver)
        if modal and not tried_iframe:
            tried_iframe = switch_into_iframe_if_any(driver, modal)
            if tried_iframe:
                time.sleep(0.5)

        btns = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'Reservation') or contains(normalize-space(.), '예약')]")
        if any(b.is_displayed() for b in btns):
            log("Reservation button detected.")
            return "buttons"

        tubs = driver.find_elements(By.CSS_SELECTOR, ".fc-header-toolbar, #calendarZone .fc-header-toolbar")
        if any(t.is_displayed() for t in tubs):
            log("FullCalendar toolbar detected.")
            return "toolbar"

        none = driver.find_elements(By.XPATH, "//*[contains(text(),'No data') or contains(text(),'검색 결과가 없습니다')]")
        if any(n.is_displayed() for n in none):
            log("No-results message detected.")
            return "no-results"

        time.sleep(0.5)
    raise TimeoutError("Calendar/Reservation UI did not appear.")

def click_reservation_button(driver, timeout=RES_BUTTON_WAIT):
    end = time.time() + timeout
    while time.time() < end:
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), 'Reservation') or contains(normalize-space(.), '예약')]")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.12 + random.random() * 0.2)
            try:
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(CLICK_PAUSE)
            return True
        except Exception:
            pass
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "#calendarZone > div.fc-header-toolbar.fc-toolbar > div:nth-child(3) > button")
            if btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.1)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(CLICK_PAUSE)
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

# ---------- AFTER RESERVATION ----------
def land_on_reservation_form(driver, previous_handles, timeout=FORM_WAIT):
    end = time.time() + timeout
    while time.time() < end:
        current = driver.window_handles
        new_handles = [h for h in current if h not in previous_handles]
        if new_handles:
            driver.switch_to.window(new_handles[-1])
            break
        time.sleep(0.3)

    try:
        driver.switch_to.default_content()
    except Exception:
        pass

    WebDriverWait(driver, timeout).until(
        EC.any_of(
            EC.visibility_of_element_located((By.ID, "bodyContentArea-RESV")),
            EC.url_contains("reser"),
            EC.url_contains("Apply"),
            EC.url_contains("Reservation")
        )
    )
    time.sleep(0.5)

# ---------- PURPOSE & TIME ----------
def select_purpose_others(driver, timeout=10):
    sel = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, "RESER_APLY_TYPE_CD")))
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#RESER_APLY_TYPE_CD option[value='RV14000099']")))
    Select(sel).select_by_value("RV14000099")
    time.sleep(0.5)

def select_dropdown_by_text(driver, selector, visible_text, timeout=10):
    sel = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
    Select(sel).select_by_visible_text(visible_text)

def select_times_for_day(driver, weekday):
    start_hour, start_min, end_hour, end_min = TIME_CONFIG.get(weekday, DEFAULT_TIMES)
    select_dropdown_by_text(driver, "#SPACE_RESER_FR_T", f"{start_hour} h")
    select_dropdown_by_text(driver, "#SPACE_RESER_FR_M", f"{start_min} min")
    select_dropdown_by_text(driver, "#SPACE_RESER_TO_T", f"{end_hour} h")
    select_dropdown_by_text(driver, "#SPACE_RESER_TO_M", f"{end_min} min")
    time.sleep(0.5)

# ---------- OPTIONAL ----------
def fill_contact_if_empty(driver):
    try:
        phone = driver.find_element(By.ID, "APLYT_CNTINFO")
        email = driver.find_element(By.ID, "APLYT_EMAIL")
    except Exception:
        return
    try:
        if phone.get_attribute("value").strip() == "" and OPTIONAL_PHONE:
            phone.clear(); phone.send_keys(OPTIONAL_PHONE); time.sleep(0.2)
        if email.get_attribute("value").strip() == "" and OPTIONAL_EMAIL:
            email.clear(); email.send_keys(OPTIONAL_EMAIL); time.sleep(0.2)
    except Exception:
        pass

# ---------- NAV HELPERS ----------
def click_english(driver):
    try:
        wait_click_css(driver, "#Tmp_resvUserTop > div.top > div > div > a:nth-child(8)", timeout=8)
        time.sleep(0.8)
    except Exception:
        pass

def open_filters_and_select_building(driver):
    # First attempt only: English + Building
    click_english(driver)
    wait_click_css(driver, "#Tmp_resvUserBody > div > div:nth-child(1) > ul > li:nth-child(1) > div > button", retries=4)
    wait_click_css(driver, "#S_BD_CD > ul > li:nth-child(4)")

def select_room_by_code(driver, room_code):
    wait_click_css(driver, "#Tmp_resvUserBody > div > div:nth-child(1) > ul > li.col-lg-4 > div > button", retries=4)
    css = ROOM_SELECTORS[room_code]
    wait_click_css(driver, css)

def go_home(driver):
    # Click home logo and WAIT 4 SECONDS before doing anything else
    wait_click_css(driver, "#Tmp_resvUserTop > div.logoarea > div > a > img", timeout=15)
    time.sleep(4.0)
    # Ensure top-level context & alive; if not, force rebuild by raising
    try:
        driver.switch_to.default_content()
        _ = driver.current_url
        _ = driver.window_handles
    except Exception:
        raise RuntimeError("SESSION_LOST_AFTER_HOME")

# ---------- SWEETALERT HANDLER ----------
def _read_swal_text(driver):
    for sel in ("#swal2-html-container", "#swal2-content", ".swal2-title"):
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed():
                return (el.text or "").strip()
        except Exception:
            continue
    return ""

def handle_swal_after_reserve(driver, timeout=12):
    try:
        WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.swal2-container.swal2-center.swal2-backdrop-show"))
        )
    except Exception:
        return "none"

    text1 = _read_swal_text(driver)
    if DEBUG: print(f"[SWAL #1] {text1}")
    confirm_css = "div.swal2-container.swal2-center.swal2-backdrop-show button.swal2-confirm.swal2-styled"
    try:
        confirm_btn = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, confirm_css)))
    except Exception:
        confirm_btn = None

    if "예약이 중복되었습니다" in text1:
        if confirm_btn:
            try: confirm_btn.click()
            except Exception: driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(0.4)
        return "duplicate"

    if confirm_btn:
        try: confirm_btn.click()
        except Exception: driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(0.6)

    try:
        WebDriverWait(driver, 2.5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "div.swal2-container.swal2-center.swal2-backdrop-show"))
        )
        text2 = _read_swal_text(driver)
        if DEBUG: print(f"[SWAL #2] {text2}")
        try:
            confirm_btn2 = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, confirm_css)))
        except Exception:
            confirm_btn2 = None

        if "예약이 중복되었습니다" in text2:
            if confirm_btn2:
                try: confirm_btn2.click()
                except Exception: driver.execute_script("arguments[0].click();", confirm_btn2)
            time.sleep(0.4)
            return "duplicate"

        if confirm_btn2:
            try: confirm_btn2.click()
            except Exception: driver.execute_script("arguments[0].click();", confirm_btn2)
            time.sleep(0.4)

        return "confirmed" if text2 else "other"
    except Exception:
        return "confirmed" if text1 else "other"

# ---------- N S S O  L O G I N  H O O K ----------
def maybe_login_nsso(driver):
    """
    If the SNU nsso password page shows up, fill password in #login_pwd and click #loginProcBtn.
    Reads password from env var SNU_PW; if missing, prompts once in console.
    """
    try:
        pw_box = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#login_pwd"))
        )
        # We’re on the login page
        password = os.environ.get("SNU_PW", "")
        if not password:
            print("SNU_PW env var not set. Type your SNU password then press Enter:")
            password = input().strip()

        pw_box.clear()
        pw_box.send_keys(password)
        time.sleep(0.2)

        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#loginProcBtn"))
        )
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)

        time.sleep(3.0)
        wait_for_idle(driver, timeout=20)
    except Exception:
        # No nsso login page; continue normally
        pass

# ---------- ONE ATTEMPT FOR A GIVEN ROOM ----------
def try_book_room(driver, today, target_date, room_code, start_mode="full"):
    """
    start_mode:
      - "full": click English + select Building, then choose room (first attempt)
      - "room_only": start from home and only change the room (after duplicate)
    Returns: "success" | "duplicate" | "fail"
    """
    log(f"-> Attempting room {room_code} (start_mode={start_mode})")

    if start_mode == "full":
        open_filters_and_select_building(driver)

    select_room_by_code(driver, room_code)

    # Open calendar & pick date
    wait_click_css(driver, "#S_SPACE_RESER_USE_DT")
    pick_date_with_rules(driver, today, target_date)

    # Search & wait for calendar UI
    wait_click_css(driver, "#Tmp_resvUserBody > div > div:nth-child(1) > ul > li.col-lg-2 > div > button.btn2.searchPlusbtn")
    try:
        state = wait_for_calendar_render(driver, timeout=CALENDAR_WAIT)
    except Exception:
        if DEBUG: dump_debug(driver, f"calendar_timeout_{room_code}")
        return "fail"

    time.sleep(0.6)
    if state == "no-results":
        log("No available slots listed for this date/room.")
        return "fail"

    # Reservation button -> land on form
    prev_handles = driver.window_handles[:]
    if not click_reservation_button(driver, timeout=RES_BUTTON_WAIT):
        if DEBUG: dump_debug(driver, f"no_res_btn_{room_code}")
        return "fail"
    land_on_reservation_form(driver, prev_handles, timeout=FORM_WAIT)

    # Purpose + times
    select_purpose_others(driver, timeout=10)
    select_times_for_day(driver, today.weekday())

    # Optional contact
    fill_contact_if_empty(driver)

    # Subject/Content
    type_text_css(driver, "#SPACE_RESER_TTL", "Vocal Music")
    type_text_css(driver, "#SPACE_RESER_CTNT", "Practicing Vocal Music")

    # Agree & submit
    driver.execute_script("window.scrollBy(0, 400);"); time.sleep(CLICK_PAUSE)
    wait_click_css(driver, "#PERS_INFO_UTILIZ_CONSNT_YN")
    wait_click_css(driver, "#ATTNT_CTNT_CONSNT_YN")
    wait_click_css(driver, "#reserInsertBtn")

    # Handle SweetAlert2 popup
    result = handle_swal_after_reserve(driver, timeout=12)
    if result == "duplicate" or wait_for_text_present(driver, "예약이 중복되었습니다", timeout=3):
        log("Duplicate booking message — will try next room.")
        # Try to go home (verify session). If it fails, propagate so caller can rebuild driver.
        go_home(driver)  # may raise RuntimeError("SESSION_LOST_AFTER_HOME")
        return "duplicate"

    return "success"

# ---------- MAIN ----------
def main():
    today = now_kst()
    if today.weekday() not in BOOK_DAYS:
        print(f"Today is {today.strftime('%A')} — not in booking days {BOOK_DAYS}. Exiting.")
        sys.exit(0)

    target_date = today + timedelta(days=7)
    print(f"Booking for: {target_date.strftime('%Y-%m-%d (%A)')} (KST)")
    print("Using profile:", PROFILE_DIR)

    os.makedirs(PROFILE_DIR, exist_ok=True)
    driver = build_driver(headless=False)

    try:
        # Open the portal; if nsso login shows, do it then continue
        log("-> Opening reservation site...")
        driver.get(START_URL)
        wait_for_idle(driver)
        time.sleep(1.0)
        maybe_login_nsso(driver)

        day = today.weekday()
        rooms_today = ROOM_PRIORITY.get(day, ["311", "302", "318"])

        start_mode = "full"   # first attempt does English + Building

        for idx, room in enumerate(rooms_today, start=1):
            log(f"=== Try {idx}/{len(rooms_today)}: room {room} ===")
            try:
                status = try_book_room(driver, today, target_date, room, start_mode=start_mode)

            except RuntimeError as re:
                # Raised when session lost after go_home
                if "SESSION_LOST_AFTER_HOME" in str(re):
                    if DEBUG: dump_debug(driver, f"session_lost_{room}")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    # Rebuild driver and restart from full
                    driver = build_driver(headless=False)
                    driver.get(START_URL)
                    wait_for_idle(driver)
                    time.sleep(1.0)
                    maybe_login_nsso(driver)
                    start_mode = "full"
                    # retry this same room once
                    try:
                        status = try_book_room(driver, today, target_date, room, start_mode=start_mode)
                    except Exception as e2:
                        if DEBUG: dump_debug(driver, f"exception_room_{room}_retry")
                        log(f"Error while retrying room {room}: {e2}")
                        status = "fail"
                else:
                    if DEBUG: dump_debug(driver, f"exception_room_{room}")
                    log(f"Error while trying room {room}: {re}")
                    status = "fail"

            except WebDriverException as e:
                # Handle crashes: tab crashed, invalid session id, etc.
                msg = str(e).lower()
                if "tab crashed" in msg or "invalid session id" in msg or "chrome not reachable" in msg:
                    if DEBUG: dump_debug(driver, f"driver_crashed_{room}")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = build_driver(headless=False)
                    driver.get(START_URL)
                    wait_for_idle(driver)
                    time.sleep(1.0)
                    maybe_login_nsso(driver)
                    start_mode = "full"
                    # retry this room once
                    try:
                        status = try_book_room(driver, today, target_date, room, start_mode=start_mode)
                    except Exception as e2:
                        if DEBUG: dump_debug(driver, f"exception_room_{room}_retry2")
                        log(f"Error while retrying room {room}: {e2}")
                        status = "fail"
                else:
                    if DEBUG: dump_debug(driver, f"exception_room_{room}")
                    log(f"Error while trying room {room}: {e}")
                    status = "fail"

            except Exception as e:
                if DEBUG: dump_debug(driver, f"exception_room_{room}")
                log(f"Error while trying room {room}: {e}")
                status = "fail"

            # handle result
            if status == "success":
                print(f"Success with room {room}. Check your portal for confirmation/approval.")
                return
            elif status == "duplicate":
                # After duplicate + go_home success: skip English/Building next time
                start_mode = "room_only"
                continue
            else:
                # Hard fail: ensure we're at start and reset to full
                try:
                    driver.get(START_URL)
                    wait_for_idle(driver)
                    time.sleep(1.0)
                    maybe_login_nsso(driver)  # if session dropped mid-run
                except Exception:
                    # If even this fails, rebuild browser
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = build_driver(headless=False)
                    driver.get(START_URL)
                    wait_for_idle(driver)
                    time.sleep(1.0)
                    maybe_login_nsso(driver)
                start_mode = "full"

        print("Could not complete a reservation with the configured rooms for today.")

    except Exception as e:
        if DEBUG: dump_debug(driver, "exception")
        print(f"Error: {e}")
    finally:
        try:
            time.sleep(2)
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
