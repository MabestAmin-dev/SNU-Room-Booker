from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os

PROFILE_DIR = r"C:\SNU_Booker\chrome_snu_profile"
os.makedirs(PROFILE_DIR, exist_ok=True)

options = webdriver.ChromeOptions()
options.add_argument(f"--user-data-dir={PROFILE_DIR}")
options.add_argument("--profile-directory=Default")
options.add_argument("--start-maximized")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--no-first-run")
options.add_argument("--no-default-browser-check")

driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

login_url = "https://ssims.snu.ac.kr"  # or "https://my.snu.ac.kr"
driver.get(login_url)

try:
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "input"))
    )
    print("Login page loaded — log in, complete MFA, tick 'Do not use additional authentication in this browser', then close.")
except:
    print("Could not confirm login page — check URL manually.")

# No driver.quit() at the end
print("Login page loaded — log in, complete MFA, tick 'Do not use additional authentication in this browser', then close this Chrome window manually.")
while True:
    pass  # Keeps script alive
