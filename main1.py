"""DuoLenium (updated): Selenium 4 + deep-translator.

Env vars (or a .env file): DUO_EMAIL, DUO_PASSWORD, DUO_LANG,
DUO_BROWSER=chrome|firefox, DUO_HEADLESS=1, CHROMEDRIVER, CHROME_BIN, GECKODRIVER
"""
import json
import os
import random
import re
import shutil
import sys
import time
from getpass import getpass

from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LANG_CODES = {
    "french": "fr", "spanish": "es", "german": "de", "italian": "it",
    "portuguese": "pt", "dutch": "nl", "swedish": "sv", "russian": "ru",
    "japanese": "ja", "korean": "ko", "turkish": "tr", "polish": "pl",
}

TOKEN = '[data-test="challenge-tap-token"]'
CHOICE = '[data-test="challenge-choice"], [data-test="challenge-judge-text"]'
INPUT = ('[data-test="challenge-translate-input"], [data-test="challenge-text-input"], '
         '[data-test="challenge-name-input"]')


def _load_env(path=".env"):
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


_load_env()
INTERACTIVE = sys.stdin.isatty()


def make_driver():
    browser = os.environ.get("DUO_BROWSER", "chrome").lower()
    headless = os.environ.get("DUO_HEADLESS", "0") == "1"
    if browser == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        opts = Options()
        if headless:
            opts.add_argument("-headless")
        opts.add_argument("--width=1280")
        opts.add_argument("--height=900")
        # mute all audio (Duolingo's listening exercises)
        opts.set_preference("media.volume_scale", "0.0")
        opts.set_preference("media.autoplay.default", 5)
        opts.set_preference("media.autoplay.blocking_policy", 2)
        gecko = os.environ.get("GECKODRIVER") or shutil.which("geckodriver")
        return webdriver.Firefox(options=opts, service=Service(gecko) if gecko else Service())
    from selenium.webdriver.chrome.service import Service
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--mute-audio")
    opts.add_argument("--window-size=1280,900")
    if os.environ.get("CHROME_BIN"):
        opts.binary_location = os.environ["CHROME_BIN"]
    drv = os.environ.get("CHROMEDRIVER")
    return webdriver.Chrome(options=opts, service=Service(drv) if drv else Service())


driver = make_driver()
wait = WebDriverWait(driver, 20)
lang_name = ""
lang_code = ""


def q(css):
    return driver.find_element(By.CSS_SELECTOR, css)


def qs(css):
    return driver.find_elements(By.CSS_SELECTOR, css)


def data_test(name):
    return f'[data-test="{name}"]'


def js_click(el):
    driver.execute_script("arguments[0].click();", el)


def usable(els):
    out = []
    for e in els:
        try:
            if e.is_displayed() and e.get_attribute("aria-disabled") != "true" \
                    and e.get_attribute("disabled") is None:
                out.append(e)
        except StaleElementReferenceException:
            pass
    return out


def text_of(el):
    try:
        return (el.get_attribute("innerText") or "").strip()
    except StaleElementReferenceException:
        return ""


CACHE_FILE = "translations.json"
_blocked_until = 0.0
_last_call = 0.0


def _load_cache():
    try:
        return {tuple(k.split("\x1f", 2)): v for k, v in json.load(open(CACHE_FILE, encoding="utf-8")).items()}
    except Exception:
        return {}


def _save_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"\x1f".join(k): v for k, v in _cache.items() if v}, f, ensure_ascii=False)
    except Exception:
        pass


_cache = _load_cache()


def _live_translate(src, tgt, text):
    try:
        return GoogleTranslator(source=src, target=tgt).translate(text) or ""
    except Exception as e:
        if "TooManyRequests" not in type(e).__name__:
            raise
    # Google is limiting us: try MyMemory once (needs a real source language)
    from deep_translator import MyMemoryTranslator
    s_lang = lang_name if src == "auto" else src
    t_lang = "english" if tgt == "en" else lang_name
    return MyMemoryTranslator(source=s_lang, target=t_lang).translate(text) or ""


def safe_translate(src, tgt, text):
    global _blocked_until, _last_call
    text = text.strip()
    if not text:
        return ""
    key = (src, tgt, text)
    if key in _cache:
        return _cache[key]
    if time.time() < _blocked_until:
        return ""  # cooling down: caller falls back to guessing
    wait_s = 2.0 - (time.time() - _last_call)
    if wait_s > 0:
        time.sleep(wait_s)
    _last_call = time.time()
    try:
        out = _live_translate(src, tgt, text)
    except Exception as e:
        print("Translate blocked (%s): pausing translation for 10 min" % type(e).__name__)
        _blocked_until = time.time() + 600
        return ""
    if out:
        _cache[key] = out
        _save_cache()
    return out


def to_lang(text):
    return safe_translate("en", lang_code, text)


def to_english(text):
    if text.strip().isascii():
        return text.strip()
    return safe_translate("auto", "en", text)


# ---------- login / start ----------

def welcome():
    global lang_name, lang_code
    print("Welcome to DuoLenium")
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
    try:
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, data_test("have-account")))).click()
    except TimeoutException:
        pass
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, data_test("email-input"))))
    q(data_test("email-input")).send_keys(email)
    q(data_test("password-input")).send_keys(password)
    q(data_test("register-button")).click()
    try:
        WebDriverWait(driver, 90).until(EC.url_contains("/learn"))
    except TimeoutException:
        print("URL:", driver.current_url)
        try:
            print("Page text:", driver.find_element(By.TAG_NAME, "body").text[:400].replace("\n", " | "))
        except Exception:
            pass
        driver.save_screenshot("login_debug.png")
        if not INTERACTIVE:
            raise SystemExit("Login didn't finish (CAPTCHA or bad credentials?).")
        input("Login didn't finish. Solve any CAPTCHA in the browser, then press Enter...")


def click_by_text(word):
    xp = ("//*[self::button or self::a][contains(translate(normalize-space(.),"
          "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'%s')]" % word)
    for el in driver.find_elements(By.XPATH, xp):
        if el.is_displayed():
            js_click(el)
            return True
    return False


def start_practice():
    sel = '[data-test~="skill-path-level-skill"], [data-test~="skill-path-level-practice"]'
    for i in range(8):
        driver.get("https://www.duolingo.com/learn")
        try:
            for attempt in range(3):
                try:
                    WebDriverWait(driver, 40).until(lambda d: d.find_elements(By.CSS_SELECTOR, sel))
                    break
                except TimeoutException:
                    if attempt == 2:
                        raise
                    print("Path didn't load, retrying in 30s...")
                    time.sleep(30)
                    driver.get("https://www.duolingo.com/learn")
        except TimeoutException:
            print("URL:", driver.current_url)
            driver.save_screenshot("path_debug.png")
            raise SystemExit("Lesson path never appeared.")
        time.sleep(1)
        for el in qs(data_test("notification-drawer-no-thanks-button")):
            try:
                el.click()
            except Exception:
                pass
        nodes = qs(sel)
        print("Found", len(nodes), "lesson nodes; trying", i)
        if i >= len(nodes):
            break
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", nodes[i])
        js_click(nodes[i])
        time.sleep(2)
        if "/lesson" not in driver.current_url:
            click_by_text("START") or click_by_text("PRACTICE")
            time.sleep(2)
        if "/lesson" in driver.current_url and "/test" not in driver.current_url:
            print("Started lesson:", driver.current_url)
            return
        print("Skipped node", i, driver.current_url)
    raise SystemExit("Couldn't start a normal lesson from the path.")


# ---------- answering ----------

def clean_prompt(txt):
    if lang_code in ("ja", "ko"):
        txt = re.sub(r"[A-Za-z]", "", txt)
    return txt.strip()


def prompt_text():
    sep = "" if lang_code in ("ja", "ko") else " "
    for sel in (data_test("hint-token"), data_test("challenge-translate-prompt")):
        txt = clean_prompt(sep.join(text_of(e) for e in qs(sel) if text_of(e)))
        if txt:
            return txt
    # fallback: text next to the header, ignoring labels
    try:
        hdr = q(data_test("challenge-header"))
        raw = driver.execute_script(
            "var p=arguments[0].parentElement.parentElement;return p?p.innerText:'';", hdr)
        skip = {"new word", "new", "previous mistake", hdr.text.strip().lower()}
        lines = [l.strip() for l in raw.split("\n") if l.strip() and l.strip().lower() not in skip]
        return clean_prompt(lines[0])[:80] if lines else ""
    except Exception:
        return ""


def advance():
    for _ in range(2):
        time.sleep(0.6)
        try:
            js_click(q(data_test("player-next")))
        except NoSuchElementException:
            pass


def skip_question():
    try:
        js_click(q(data_test("player-skip")))
    except NoSuchElementException:
        pass
    advance()


def solve_wordbank(target):
    toks = usable(qs(TOKEN))
    texts = [text_of(t).lower().strip(".,!?。、！？ ") for t in toks]
    t = target.lower()
    used, pos, clicked = set(), 0, 0
    for _ in range(len(toks)):
        best = None
        for idx, txt in enumerate(texts):
            if idx in used or not txt:
                continue
            i = t.find(txt, pos)
            if i != -1 and (best is None or i < best[0]):
                best = (i, idx)
        if not best:
            break
        used.add(best[1])
        try:
            js_click(toks[best[1]])
            clicked += 1
            pos = best[0] + len(texts[best[1]])
            time.sleep(0.2)
        except StaleElementReferenceException:
            pass
    if clicked == 0:  # couldn't work out the answer: just fill the bank so Check unlocks
        for tok in toks[:4]:
            try:
                js_click(tok)
                time.sleep(0.2)
            except StaleElementReferenceException:
                pass


def solve_pairs():
    for _ in range(40):
        toks = usable(qs(TOKEN))
        if len(toks) < 2:
            return
        first = toks[0]
        for other in toks[1:]:
            try:
                js_click(first)
                js_click(other)
            except StaleElementReferenceException:
                break
            time.sleep(0.4)
            if len(usable(qs(TOKEN))) < len(toks):
                break
        else:
            return  # nothing matched; give up


def solve_choice(header, prompt):
    choices = usable(qs(CHOICE))
    texts = [text_of(c).lower() for c in choices]
    m = re.search(r'[“"](.+?)[”"]', header)
    target = (m.group(1) if m else to_english(prompt)).lower().strip()
    pick = None
    if target:
        trs = [""] * len(texts)
        if any(t for t in texts):
            joined = to_english("\n".join(t or "-" for t in texts)).lower().split("\n")
            if len(joined) == len(texts):
                trs = [j.strip() for j in joined]
        for c, txt, tr in zip(choices, texts, trs):
            if not txt:
                continue
            if target == txt or target == tr or (len(target) > 2 and tr and (target in tr or tr in target)):
                pick = c
                break
    js_click(pick or random.choice(choices))


def solve(header, prompt):
    to_english_dir = "english" in header
    target = to_english(prompt) if to_english_dir else to_lang(prompt)
    inputs = qs(INPUT)
    if inputs:
        inputs[0].send_keys(target or "a")
    elif usable(qs(TOKEN)):
        if "matching" in header or "pair" in header:
            solve_pairs()
        else:
            solve_wordbank(target)
    elif usable(qs(CHOICE)):
        solve_choice(header, prompt)
    else:
        names = sorted({e.get_attribute("data-test") for e in qs("[data-test]") if e.get_attribute("data-test")})
        print("  data-test names:", ", ".join(names))
        raise RuntimeError("unknown question layout")
    advance()


def dismiss_popups():
    for name in ("no-thanks-to-plus", "plus-no-thanks", "notification-drawer-no-thanks-button"):
        for el in qs(data_test(name)):
            try:
                js_click(el)
            except Exception:
                pass


def training():
    time.sleep(4)
    idle = 0
    seen = {}
    while True:
        time.sleep(0.8)
        dismiss_popups()
        if "/lesson" not in driver.current_url:
            print("Lesson finished.")
            return
        hdrs = qs(data_test("challenge-header") + " span")
        if not hdrs:
            idle += 1
            if idle > 15:
                print("Nothing left to do.")
                return
            try:
                js_click(q(data_test("player-next")))
            except NoSuchElementException:
                pass
            continue
        idle = 0
        header = hdrs[0].text.lower()
        prompt = prompt_text()
        key = header + prompt
        seen[key] = seen.get(key, 0) + 1
        print("Question:", header, "|", prompt[:30])
        try:
            if seen[key] > 3:
                skip_question()
            else:
                solve(header, prompt)
        except Exception as e:
            print("Handler failed, skipping:", type(e).__name__, str(e)[:80])
            try:
                skip_question()
            except Exception:
                pass


if __name__ == "__main__":
    email, password = welcome()
    login(email, password)
    try:
        start_practice()
        training()
    finally:
        if INTERACTIVE and os.environ.get("DUO_HEADLESS") != "1":
            input("Done. Press Enter to close the browser...")
        driver.quit()
