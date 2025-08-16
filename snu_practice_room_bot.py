# snu_practice_room_bot.py
from datetime import datetime, timedelta
import time
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ---------- CONFIG ----------
PROFILE_DIR = r"C:\SNU_Booker\chrome_snu_profile"
SSO_URL   = "https://my.snu.ac.kr/portal/ssologin"
START_URL = "https://ssims.snu.ac.kr/"

# Mon/Wed/Fri/Sat/Sun (0=Mon ... 6=Sun)
BOOK_DAYS = {0, 2, 4, 5, 6}

CLICK_PAUSE = 1.5
CALENDAR_WAIT = 20
RES_BUTTON_WAIT = 4
FORM_WAIT = 25
PAUSE_IF_LOGIN_REQUIRED = True
DEBUG = True

# Optional: auto-fill these ONLY if blank
OPTIONAL_PHONE = ""        # e.g. "01012345678"
OPTIONAL_EMAIL = ""        # e.g. "you@snu.ac.kr"

# ---------- TIME CONFIG (per weekday) ----------
# 0=Mon ... 6=Sun   ->  (start_hour, start_min, end_hour, end_min)
TIME_CONFIG = {
    0: ("07", "00", "08", "00"),  # Mon
    1: ("09", "10", "10", "00"),  # Tue
    2: ("13", "30", "14", "30"),  # Wed
    3: ("10", "00", "11", "00"),  # Thu
    4: ("15", "00", "16", "00"),  # Fri
    5: ("08", "30", "09", "30"),  # Sat
    6: ("14", "00", "15", "00"),  # Sun
}
DEFAULT_TIMES = ("07", "00", "08", "00")

# ---------- ROOM PRIORITY (per weekday) ----------
ROOM_PRIORITY = {
    0: ["311", "302", "318"],  # Mon
    2: ["302", "311", "318"],  # Wed
    4: ["311", "302", "318"],  # Fri
    5: ["302", "311", "318"],  # Sat
    6: ["311", "302", "318"],  # Sun
}
ROOM_SELECTORS = {
    "311": "#S_SPACE_CD > ul > li:nth-child(12)",
    "302": "#S_SPACE_CD > ul > li:nth-child(8)",
    "318": "#S_SPACE_CD > ul > li:nth-child(13)",
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
    return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

# ---------- UTILS ----------
def log(step): print(step, flush=True)

def wait_for_idle(driver, timeout=20):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")

def wait_find_css(driver, css, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

def wait_click_css(driver, css, timeout=20, retries=3, post_pause=CLICK_PAUSE):
    last_err = None
    for _ in range(retries):
        try:
            el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            try: el.click()
            except Exception: driver.execute_script("arguments[0].click();", el)
            time.sleep(post_pause)
            return el
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise last_err

def type_text_css(driver, css, text, clear_first=True, timeout=20):
    el = wait_find_css(driver, css, timeout=timeout)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        if clear_first: el.clear()
    except Exception: pass
    el.send_keys(text)
    time.sleep(CLICK_PAUSE)
    return el

def dump_debug(driver, tag="debug"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    png = f"snu_bot_{tag}_{ts}.png"
    html = f"snu_bot_{tag}_{ts}.html"
    try: driver.save_screenshot(png)
    except Exception: pass
    try:
        with open(html, "w", encoding="utf-8") as f: f.write(driver.page_source)
    except Exception: pass
    print(f"🧪 Saved debug artifacts: {png} and {html}")

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

# ---------- LOGIN / SSO ----------
def is_on_sso_login(driver):
    try:
        WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        return True
    except Exception:
        return False

def ensure_sso(driver):
    log("→ Opening SSO...")
    driver.get(SSO_URL)
    time.sleep(1.0)
    if is_on_sso_login(driver):
        if not PAUSE_IF_LOGIN_REQUIRED:
            raise RuntimeError("SSO login required but PAUSE_IF_LOGIN_REQUIRED is False.")
        print("SSO login page detected. Please log in (no MFA if trusted), then press Enter here...")
        try: input()
        except KeyboardInterrupt: sys.exit(1)
    wait_for_idle(driver)

# ---------- DATEPICKER ----------
def pick_date_with_rules(driver, today, target_date):
    wait_find_css(driver, "#ui-datepicker-div", timeout=20)
    if target_date.month == today.month and target_date.year == today.year:
        _click_day_by_text(driver, target_date.day)
    else:
        wait_click_css(driver, "#ui-datepicker-div > div > a.ui-datepicker-next.ui-corner-all > span")
        py_weekday = target_date.weekday()
        col = ((py_weekday + 1) % 7) + 1
        day_cell_css = f"#ui-datepicker-div > table > tbody > tr:nth-child(1) > td:nth-child({col}) > a"
        wait_click_css(driver, day_cell_css)

def _click_day_by_text(driver, day_int):
    day_xpath = ("//div[@id='ui-datepicker-div']"
                 "//td[not(contains(@class,'ui-datepicker-other-month'))]"
                 f"/a[normalize-space()='{day_int}']")
    el = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, day_xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try: el.click()
    except Exception: driver.execute_script("arguments[0].click();", el)
    time.sleep(CLICK_PAUSE)

# ---------- MODAL / IFRAME AWARE WAIT ----------
def find_visible_modal_root(driver):
    for sel in ["div[role='dialog']", ".ui-dialog", ".modal", ".swal2-container"]:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                if el.is_displayed(): return el
            except Exception: continue
    return None

def switch_into_iframe_if_any(driver, container):
    try:
        if not container: return False
        for fr in container.find_elements(By.TAG_NAME, "iframe"):
            if fr.is_displayed():
                driver.switch_to.frame(fr)
                return True
    except Exception: pass
    return False

def wait_for_calendar_render(driver, timeout=CALENDAR_WAIT):
    end = time.time() + timeout
    tried_iframe = False
    while time.time() < end:
        modal = find_visible_modal_root(driver)
        if modal and not tried_iframe:
            tried_iframe = switch_into_iframe_if_any(driver, modal)
            if tried_iframe: time.sleep(0.5)

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
            try: btn.click()
            except Exception: driver.execute_script("arguments[0].click();", btn)
            time.sleep(CLICK_PAUSE)
            return True
        except Exception:
            pass
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "#calendarZone > div.fc-header-toolbar.fc-toolbar > div:nth-child(3) > button")
            if btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                try: btn.click()
                except Exception: driver.execute_script("arguments[0].click();", btn)
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

    try: driver.switch_to.default_content()
    except Exception: pass

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

# ---------- ONE ATTEMPT FOR A GIVEN ROOM ----------
def try_book_room(driver, today, target_date, room_code, start_mode="full"):
    """
    start_mode:
      - "full": click English + select Building, then choose room (first attempt)
      - "room_only": start from home and only change the room (after duplicate)
    Returns: "success" | "duplicate" | "fail"
    """
    log(f"→ Attempting room {room_code} (start_mode={start_mode})")

    if start_mode == "full":
        open_filters_and_select_building(driver)
    else:
        # We assume we're at home already (after go_home); skip English/building
        pass

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

    time.sleep(0.8)
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
        log("⚠️ Duplicate booking message — will try next room.")
        try:
            go_home(driver)  # waits 4 seconds inside
        except Exception:
            driver.get(START_URL)
            wait_for_idle(driver)
            time.sleep(4.0)
        return "duplicate"

    return "success"

# ---------- MAIN ----------
def main():
    today = today = datetime(2025, 8, 27) #datetime.now()
    if today.weekday() not in BOOK_DAYS:
        print(f"Today is {today.strftime('%A')} — not in booking days {BOOK_DAYS}. Exiting.")
        sys.exit(0)

    target_date = today + timedelta(days=7)
    print(f"Booking for: {target_date.strftime('%Y-%m-%d (%A)')}")
    print("Using profile:", PROFILE_DIR)

    os.makedirs(PROFILE_DIR, exist_ok=True)
    driver = build_driver(headless=False)

    try:
        ensure_sso(driver)
        log("→ Opening reservation site…")
        driver.get(START_URL)
        wait_for_idle(driver)
        time.sleep(1.0)

        day = today.weekday()
        rooms_today = ROOM_PRIORITY.get(day, ["311", "302", "318"])

        start_mode = "full"   # first attempt does English + Building
        for idx, room in enumerate(rooms_today, start=1):
            log(f"=== Try {idx}/{len(rooms_today)}: room {room} ===")
            try:
                status = try_book_room(driver, today, target_date, room, start_mode=start_mode)
            except Exception as e:
                if DEBUG: dump_debug(driver, f"exception_room_{room}")
                log(f"❌ Error while trying room {room}: {e}")
                status = "fail"

            if status == "success":
                print(f"✅ Success with room {room}. Check your portal for confirmation/approval.")
                return
            elif status == "duplicate":
                # After duplicate we already went home + waited 4s; next attempt skips English/Building
                start_mode = "room_only"
                continue
            else:
                # Hard fail: ensure we're at start and reset to full (safe fallback)
                driver.get(START_URL)
                wait_for_idle(driver)
                time.sleep(1.0)
                start_mode = "full"

        print("⚠️ Could not complete a reservation with the configured rooms for today.")

    except Exception as e:
        if DEBUG: dump_debug(driver, "exception")
        print(f"⚠️ Error: {e}")
    finally:
        time.sleep(2)
        driver.quit()

if __name__ == "__main__":
    main()
