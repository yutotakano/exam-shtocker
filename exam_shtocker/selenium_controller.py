import enum
import logging
import os
from threading import Event
import time
from typing import Any, NotRequired, Optional, TypedDict

import requests
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.options import Options as FFOptions
from selenium.webdriver.firefox.service import Service as FFService
from selenium.webdriver.firefox.webdriver import WebDriver

logger = logging.getLogger(__name__)

HEADLESS = True
WAIT_SECONDS = 30


class SeleniumLauncherReturnValues(TypedDict):
    error: NotRequired[Exception]
    driver: NotRequired[WebDriver]


def initialise_selenium(return_values: SeleniumLauncherReturnValues, ready: Event):
    logger.info("Initialising Selenium")
    try:
        d = make_driver()
        d.get("https://www.myed.ed.ac.uk/uPortal/Login?refUrl=%2Fmyed-progressive%2")
        return_values["driver"] = d
    except Exception as e:
        return_values["error"] = e
    finally:
        ready.set()


def make_driver() -> WebDriver:
    logger.info("Creating Firefox WebDriver")
    logger.debug(f"HEADLESS={HEADLESS}")

    ff_opts = FFOptions()
    if HEADLESS:
        ff_opts.add_argument("-headless")

    ff_service = FFService(log_output=os.devnull)

    driver = webdriver.Firefox(options=ff_opts, service=ff_service)

    if HEADLESS:
        driver.set_window_size(1920, 1080)  # type: ignore because selenium doesn't provide argument types here
    else:
        try:
            driver.maximize_window()
        except Exception:
            driver.set_window_size(1920, 1080)  # type: ignore because selenium doesn't provide argument types here

    return driver


def wait_presence_soft(
    driver: WebDriver, by: str, locator: str, timeout: float = WAIT_SECONDS
):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, locator))
        )
    except TimeoutException:
        return None


def send_keys_if_present(
    driver: WebDriver,
    by: str,
    locator: str,
    keys: str,
    timeout: float = WAIT_SECONDS,
    clear_first: bool = True,
):
    el = wait_presence_soft(driver, by, locator, timeout)
    if not el:
        return False
    try:
        if clear_first:
            try:
                el.clear()
            except Exception:
                pass
        el.send_keys(keys)
        return True
    except Exception:
        return False


def click_if_present(
    driver: WebDriver, by: str, locator: str, timeout: float = WAIT_SECONDS
):
    try:
        if timeout:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, locator))
            )
        else:
            el = driver.find_element(by, locator)

        el.click()
        return True
    except (TimeoutException, NoSuchElementException, WebDriverException):
        return False


def wait_until_source_contains_any(
    driver: WebDriver,
    phrases: list[str],
    timeout: float = WAIT_SECONDS,
    poll_interval: float = 0.5,
):
    end = time.time() + timeout
    lowers = [p.lower() for p in phrases]
    while time.time() < end:
        try:
            src = (driver.page_source or "").lower()
            for i, p in enumerate(lowers):
                if p in src:
                    return phrases[i]
        except Exception:
            pass
        time.sleep(poll_interval)
    return None


def get_text_if_present(
    driver: WebDriver, by: str, locator: str, timeout: float = WAIT_SECONDS
):
    el = wait_presence_soft(driver, by, locator, timeout)
    try:
        return (el.text or "").strip() if el else ""
    except Exception:
        return ""


def xpath_present(driver: WebDriver, by: str, locator: str) -> bool:
    try:
        return bool(driver.find_elements(by, locator))
    except Exception:
        return False


def page_contains(driver: WebDriver, phrase: str) -> bool:
    try:
        return phrase.lower() in (driver.page_source or "").lower()
    except Exception:
        return False


def submit_validate_username_password(
    driver: WebDriver, username: str, password: str
) -> bool:
    logger.info("Sending username & password once elements are present")
    if not send_keys_if_present(driver, By.ID, "userNameInput", username + "@ed.ac.uk"):
        return False
    if not send_keys_if_present(driver, By.ID, "passwordInput", password):
        return False

    logger.info("Clicking submission button")
    if not click_if_present(driver, By.ID, "submitButton"):
        return False

    logger.info("Waiting for incorrect response or correct response")
    if not wait_until_source_contains_any(
        driver,
        phrases=["lightboxTemplateContainer", "Incorrect user ID or password"],
        timeout=WAIT_SECONDS,
        poll_interval=0.5,
    ):
        return False

    if page_contains(driver, "Incorrect user ID or password"):
        return False

    if not wait_presence_soft(driver, By.XPATH, '//*[@id="idSIButton9"]'):
        return False
    if not click_if_present(driver, By.XPATH, '//*[@id="idSIButton9"]'):
        return False

    return True


class TWO_FACTOR_TYPE(enum.Enum):
    SIX_DIGIT_CODE = 0
    APPROVE_NUMBER = 1


def wait_for_2fa_prompt(
    driver: WebDriver,
) -> Optional[tuple[TWO_FACTOR_TYPE, Optional[str]]]:
    wait_until_source_contains_any(
        driver,
        phrases=[
            "trouble verifying your account",
            "Open your Authenticator",
            "Enter the code displayed",
        ],
        timeout=WAIT_SECONDS,
        poll_interval=0.5,
    )

    if page_contains(driver, "trouble verifying your account"):
        proof1 = '//*[@id="idDiv_SAOTCS_Proofs"]/div[1]/div'
        proof2 = '//*[@id="idDiv_SAOTCS_Proofs"]/div[2]/div'

        while True:
            has1 = xpath_present(driver, By.XPATH, proof1)
            has2 = xpath_present(driver, By.XPATH, proof2)

            # Exit when neither XPath is on the page
            if not (has1 or has2):
                # print("breaking")
                break

            if has1:
                # print("found 1")
                while True:
                    if page_contains(driver, "lightbox-cover disable-lightbox"):
                        # print("1: loading wait")
                        time.sleep(0.5)
                    else:
                        break
                # print("broke 1")
                click_if_present(driver, By.XPATH, proof1)

            if has2:
                # print("found 2")
                while True:
                    if page_contains(driver, "lightbox-cover disable-lightbox"):
                        # print("2: loading wait")
                        time.sleep(0.5)
                    else:
                        break
                # print("broke 2")
                click_if_present(driver, By.XPATH, proof2)

            time.sleep(0.5)

        wait_until_source_contains_any(
            driver,
            phrases=["Open your Authenticator", "Enter the code displayed"],
            timeout=WAIT_SECONDS,
            poll_interval=0.5,
        )

    if page_contains(driver, "Enter the code displayed"):
        return (TWO_FACTOR_TYPE.SIX_DIGIT_CODE, None)
    elif page_contains(driver, "Open your Authenticator"):
        ctx_text = get_text_if_present(driver, By.ID, "idRichContext_DisplaySign")
        return (TWO_FACTOR_TYPE.APPROVE_NUMBER, ctx_text)

    return None


def input_2fa_otp(driver: WebDriver, otp_code: str):
    send_keys_if_present(driver, By.XPATH, '//*[@id="idTxtBx_SAOTCC_OTC"]', otp_code)

    wait_presence_soft(driver, By.ID, "idSubmit_SAOTCC_Continue")
    if not click_if_present(driver, By.ID, "idSubmit_SAOTCC_Continue"):
        wait_presence_soft(driver, By.XPATH, '//*[@id="idSubmit_SAOTCC_Continue"]')
        click_if_present(driver, By.XPATH, '//*[@id="idSubmit_SAOTCC_Continue"]')


def wait_for_2fa_completion(driver: WebDriver):
    if not wait_presence_soft(driver, By.ID, "idSIButton9"):
        return False
    if not click_if_present(driver, By.ID, "idSIButton9"):
        return False

    return wait_presence_soft(driver, By.ID, "notification-icon")


def retrieve_logged_in_name(driver: WebDriver) -> Optional[str]:
    welcome_raw = (
        get_text_if_present(
            driver, By.XPATH, '//*[@id="region-eyebrow"]/div/div[2]/div/div[3]'
        )
        or ""
    )

    if not welcome_raw:
        return None

    t = welcome_raw.replace("\xa0", " ").strip()

    parts = [p.strip() for p in t.splitlines() if p.strip()]
    if not parts:
        return None

    if parts[0].lower().startswith("you are signed in as"):
        name = parts[-1]
    else:
        name = parts[-1]

    return name.strip() or None


def retrieve_exampapers_cookies(driver: WebDriver) -> Optional[list[dict[str, str]]]:
    driver.get("https://exampapers.ed.ac.uk")
    if not wait_presence_soft(
        driver,
        By.XPATH,
        "/html/body/ds-app/ds-themed-root/ds-root/div/div/main/div/ds-themed-home-page/ds-home-page/div/ds-themed-search-form/ds-search-form/form/div/div/input",
    ):
        return None

    try:
        return driver.get_cookies()  # type: ignore
    except:
        return None


def copy_cookies_to_session(cookies: list[dict[str, Any]], session: requests.Session):
    for cookie in cookies:
        if "httpOnly" in cookie:
            httpO = cookie.pop("httpOnly")
            cookie["rest"] = {"httpOnly": httpO}
        if "expiry" in cookie:
            cookie["expires"] = cookie.pop("expiry")
        if "sameSite" in cookie:
            del cookie["sameSite"]
        session.cookies.set(**cookie)  # type: ignore

    logger.info(session.cookies.get_dict())
