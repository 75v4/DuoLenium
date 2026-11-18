"""DuoLenium (updated): Selenium 4 + deep-translator, no bundled drivers.

Selenium Manager (built into Selenium 4.6+) downloads the matching
chromedriver automatically, so chromedriver.exe is no longer needed.
"""
import os
import random
import shutil
import sys
import time
from getpass import getpass

from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LANG_CODES = {
    "french": "fr", "spanish": "es", "german": "de", "italian": "it",
    "portuguese": "pt", "dutch": "nl", "swedish": "sv", "russian": "ru",
    "japanese": "ja", "korean": "ko", "turkish": "tr", "polish": "pl",
}

INTERACTIVE = sys.stdin.isatty()


def make_driver():
    """DUO_BROWSER=chrome|firefox, DUO_HEADLESS=1, CHROMEDRIVER / CHROME_BIN optional."""
    browser = os.environ.get("DUO_BROWSER", "chrome").lower()
    headless = os.environ.get("DUO_HEADLESS", "0") == "1"
    if browser == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        opts = Options()
        if headless:
            opts.add_argument("-headless")
        gecko = os.environ.get("GECKODRIVER") or shutil.which("geckodriver")
        return webdriver.Firefox(options=opts, service=Service(gecko) if gecko else Service())
    from selenium.webdriver.chrome.service import Service
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    if os.environ.get("CHROME_BIN"):
        opts.binary_location = os.environ["CHROME_BIN"]
    drv = os.environ.get("CHROMEDRIVER")
    return webdriver.Chrome(options=opts, service=Service(drv) if drv else Service())


driver = make_driver()
wait = WebDriverWait(driver, 20)
lang_name = ""
lang_code = ""
wrong_answers = set()


def q(css):
    return driver.find_element(By.CSS_SELECTOR, css)


def qs(css):
    return driver.find_elements(By.CSS_SELECTOR, css)


def data_test(name):
    return f'[data-test="{name}"]'


def to_lang(text):
    return GoogleTranslator(source="en", target=lang_code).translate(text)


def to_english(text):
    return GoogleTranslator(source="auto", target="en").translate(text)


def click_next():
    q(data_test("player-next")).click()


def welcome():
    global lang_name, lang_code
    print("Welcome to DuoLenium")
    # Non-interactive mode (GitHub Actions etc.): DUO_EMAIL, DUO_PASSWORD, DUO_LANG
    email = os.environ.get("DUO_EMAIL") or input("Duolingo email: ")
    password = os.environ.get("DUO_PASSWORD") or getpass("Duolingo password (hidden): ")
    lang_name = os.environ.get("DUO_LANG", "").strip().lower()
    while lang_name not in LANG_CODES:
        lang_name = input(f"Language you're learning ({', '.join(LANG_CODES)}): ").strip().lower()
    lang_code = LANG_CODES[lang_name]
    return email, password


def login(email, password):
    print("Logging in...")
    driver.get("https://www.duolingo.com/?isLoggingIn=true")
    # If the login form isn't shown directly, click the "I already have an account" link.
    try:
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, data_test("have-account")))).click()
    except TimeoutException:
        pass
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, data_test("email-input"))))
    q(data_test("email-input")).send_keys(email)
    q(data_test("password-input")).send_keys(password)
    q(data_test("register-button")).click()
    # Wait until we've left the login page. If a CAPTCHA appears, solve it by hand.
    try:
        wait.until(EC.url_contains("/learn"))
    except TimeoutException:
        if not INTERACTIVE:
            raise SystemExit("Login didn't finish (CAPTCHA or bad credentials?).")
        input("Login didn't finish automatically. Solve any CAPTCHA/popup in the browser, then press Enter...")


def start_practice():
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, data_test("global-practice")))).click()


# ---------- question handlers ----------

def hint_sentence():
    return " ".join(h.get_attribute("innerText") for h in qs(data_test("hint-token")))


def check_and_continue():
    click_next()          # "Check"
    time.sleep(0.3)
    click_next()          # "Continue"


def write_in_english():
    q(data_test("challenge-translate-input")).send_keys(to_english(hint_sentence()))
    check_and_continue()


def write_in_language():
    q(data_test("challenge-translate-input")).send_keys(to_lang(hint_sentence()))
    check_and_continue()


def write_blank(english_word):
    q(data_test("challenge-text-input")).send_keys(to_lang(english_word))
    check_and_continue()


def choose_missing():
    options = qs(data_test("challenge-judge-text"))
    fresh = [o for o in options if o.get_attribute("innerText") not in wrong_answers] or options
    pick = random.choice(fresh)
    text = pick.get_attribute("innerText")
    pick.click()
    click_next()
    time.sleep(0.3)
    if qs('[data-test="blame blame-incorrect"]'):
        wrong_answers.add(text)
    else:
        wrong_answers.clear()
    click_next()


def mark_correct_meaning():
    # The prompt element's CSS class changes often; fall back through a few options.
    english = ""
    for sel in (data_test("challenge-header") + " + div", data_test("hint-token"), "h1"):
        els = qs(sel)
        if els and els[0].text.strip():
            english = els[0].text.strip()
            break
    target = to_english(to_lang(english)).lower()
    for choice in qs(data_test("challenge-judge-text")):
        text = choice.get_attribute("innerText")
        if to_english(text).lower() == target:
            choice.click()
            check_and_continue()
            return
    # No match found: guess.
    choose_missing()


def skip_question():
    q(data_test("player-skip")).click()
    time.sleep(0.3)
    click_next()


def dismiss_popups():
    for name in ("no-thanks-to-plus", "plus-no-thanks"):
        for el in qs(data_test(name)):
            try:
                el.click()
            except Exception:
                pass


def training():
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, data_test("challenge-header"))))
    while True:
        time.sleep(1)
        dismiss_popups()

        if qs(data_test("player-end-carousel")) or "/lesson" not in driver.current_url and "/practice" not in driver.current_url:
            try:
                click_next()
            except NoSuchElementException:
                pass
            print("Reached the end of the session.")
            return

        try:
            header = q(data_test("challenge-header") + " span").text.lower()
        except NoSuchElementException:
            # Motivational/interstitial screen
            try:
                click_next()
            except NoSuchElementException:
                pass
            continue

        print("Question:", header)
        try:
            if header == "write this in english":
                write_in_english()
            elif header == f"write this in {lang_name}":
                write_in_language()
            elif header.startswith("write “") or header.startswith('write "'):
                word = header.split("“")[1].split("”")[0] if "“" in header else header.split('"')[1]
                write_blank(word)
            elif header in ("select the missing word", "fill in the blank"):
                choose_missing()
            elif header == "mark the correct meaning":
                mark_correct_meaning()
            else:
                skip_question()
        except Exception as e:
            print("Handler failed, skipping question:", type(e).__name__, e)
            try:
                skip_question()
            except Exception:
                pass


if __name__ == "__main__":
    email, password = welcome()
    login(email, password)
    start_practice()
    try:
        training()
    finally:
        if INTERACTIVE and os.environ.get("DUO_HEADLESS") != "1":
            input("Done. Press Enter to close the browser...")
        driver.quit()
