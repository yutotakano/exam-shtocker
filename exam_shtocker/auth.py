from threading import Event, Thread
from typing import Optional
import logging
import getpass
import re
import os
import pickle
import html

import requests
import requests.cookies
from colorama import Style

import selenium_controller
from loader import Loader


logger = logging.getLogger(__name__)


def perform_interactive_microsoft_login(session: requests.Session) -> Optional[str]:
    logger.info("Launching Selenium in background thread")

    # Launch selenium in a background thread and wait for the Microsoft login
    # page to be ready -- we could do this in the foregorund too, but it's a
    # better use of time to ask for credentials during the wait.
    ready = Event()
    return_values: selenium_controller.SeleniumLauncherReturnValues = {}
    Thread(
        target=selenium_controller.initialise_selenium,
        args=(return_values, ready),
        daemon=True,
    ).start()

    logger.info("Prompting for EASE credentials")
    print(
        Style.BRIGHT
        + "This script requires authentication. Please provide your EASE credentials.",
        Style.RESET_ALL,
    )
    username = input("EASE Username: ")
    password = getpass.getpass("     Password: ")

    logger.info("Waiting for Selenium background thread to become ready")
    loader = Loader("Waiting for Selenium Driver to be ready...", "").start()

    ready.wait()
    if "error" in return_values:
        logger.error(f"Failed to start browser: {return_values["error"]}")
        loader.cancel(f"Failed! {return_values["error"]}")
        return None

    if "driver" not in return_values:
        logger.error(f"Failed to start browser for unknown reason")
        loader.cancel(f"Failed for unknown reason...!")
        return None

    driver = return_values["driver"]

    loader.desc = "Sending credentials to Microsoft login page..."
    if not selenium_controller.submit_validate_username_password(
        driver, username, password
    ):
        logger.error("Invalid credentials")
        loader.cancel("Invalid credentials")
        return None

    loader.stop()
    loader.desc = "Waiting for 2FA prompt..."
    prompt_type = selenium_controller.wait_for_2fa_prompt(driver)

    if not prompt_type:
        logger.error("Browser behaved unexpectedly when waiting for 2FA")
        loader.cancel("Failed for unknown reason.")
        return None

    loader.stop()

    if prompt_type[0] == selenium_controller.TWO_FACTOR_TYPE.APPROVE_NUMBER:
        logger.debug("Prompting user to approve a number")
        print(f"Please use your app to approve this sign-in request: {prompt_type[1]}")
        loader = Loader("Waiting for Microsoft to accept the 2FA auth...")
    elif prompt_type[0] == selenium_controller.TWO_FACTOR_TYPE.SIX_DIGIT_CODE:
        logger.debug("Prompting user for 6-digit code")
        otp = input("Please input your 2FA 6-digit code: ").strip()
        loader = Loader("Waiting for Microsoft to accept the 2FA auth...")
        selenium_controller.input_2fa_otp(driver, otp)

    if not selenium_controller.wait_for_2fa_completion(driver):
        logger.error("2FA completion timeout failed")
        loader.cancel("2FA failed!")
        return None

    name = selenium_controller.retrieve_logged_in_name(driver)
    loader.stop(f"Logged in as {name}!")

    loader = Loader("Retrieving cookies...")
    cookies = selenium_controller.retrieve_exampapers_cookies(driver)
    if not cookies:
        logger.error("Failed to retrieve cookies")
        loader.cancel("Failed to retrieve cookies!")
        return None

    selenium_controller.copy_cookies_to_session(cookies, session)
    r = session.get("https://exampapers.ed.ac.uk")
    if "edadfed.ed.ac.uk" in r.url or "Sign In" in r.text:
        logger.error("Retrieved Selenium cookies don't work with requests")
        loader.cancel("Retrieved cookies are invalid")
        return None

    loader.stop()

    return name


def perform_interactive_ease_login(session: requests.Session) -> Optional[str]:
    """Perform EASE login and setup the session with the logged-in cookies, so
    that further requests using SAML will work.

    Parameters
    ----------
    session : requests.Session

    Returns
    -------
    Optional[str]
        EASE username if login was successful, None otherwise.
    """
    logging.info("Prompting for EASE credentials")
    print(
        Style.BRIGHT
        + "This script requires authentication. Please provide your EASE credentials.",
        Style.RESET_ALL,
    )
    username = input("EASE Username: ")
    password = getpass.getpass("     Password: ")

    # Get once to set the cookies
    loader = Loader("Logging into EASE...", "", 0.1).start()
    logger.info("Retrieving EASE cookies...")
    session.get("https://www.ease.ed.ac.uk/")

    # Login to CoSign
    logger.info("Logging into EASE CoSign...")
    r = session.post(
        "https://www.ease.ed.ac.uk/cosign.cgi",
        data={"login": username, "password": password},
    )

    # Check if we have a logout button, which means we're logged in
    if "/logout/logout.cgi" not in r.text:
        logger.error("Invalid credentials.")
        loader.cancel("Invalid credentials.")
        return None

    loader.stop(f"Authenticated as {username}.")

    return username


def perform_exampapers_login(session: requests.Session) -> None:
    """Perform login to ExamPapers using the given session.

    Parameters
    ----------
    session : requests.Session
        Session to use for logging in.
    """
    loader = Loader("Logging into ExamPapers...", "", 0.1).start()
    r = session.get("https://exampapers.ed.ac.uk")

    saml_response = re.search(
        r"<input type=\"hidden\" name=\"SAMLResponse\" value=\"(.*)\"/>", r.text
    )
    if not saml_response:
        raise Exception("Could not find SAMLResponse input field.")

    saml_response = saml_response.group(1)
    logger.debug(f"SAMLResponse: {saml_response}")

    # Get the value of the RelayState input field
    relay_state = re.search(
        r"<input type=\"hidden\" name=\"RelayState\" value=\"(.*)\"/>", r.text
    )
    if not relay_state:
        raise Exception("Could not find RelayState input field.")

    relay_state = html.unescape(relay_state.group(1))
    logger.debug(f"RelayState: {relay_state}")

    # Login to ExamPapers
    logger.info("Sending exampapers the SAMLResponse...")

    r = session.post(
        "https://exampapers.ed.ac.uk/Shibboleth.sso/SAML2/POST",
        data={"SAMLResponse": saml_response, "RelayState": relay_state},
    )

    if r.url != "https://exampapers.ed.ac.uk/":
        raise Exception("Could not log into ExamPapers.")

    loader.stop("Done.")


def setup_session() -> Optional[requests.Session]:
    loader = Loader("Setting up session...", "", 0.1).start()
    session = requests.Session()

    if os.path.exists("session_auth_pickle"):
        loader.desc = "Using previous session_auth_pickle..."
        with open("session_auth_pickle", "rb") as f:
            cookies: requests.cookies.RequestsCookieJar = pickle.load(f)
            session.cookies = cookies

    loader.desc = "Checking if session is authenticated..."
    # Try to get it on the first try, if it fails, try logging in
    r = session.get("https://exampapers.ed.ac.uk")
    if "edadfed.ed.ac.uk" in r.url or "Sign In" in r.text:
        loader.cancel("Session needs login.")

        try:
            username = perform_interactive_microsoft_login(session)
            if not username:
                logger.error("Could not log into Microsoft (invalid credentials?).")
                return None
        except Exception as e:
            logger.error("Failed to log into Microsoft: " + str(e))
            loader.cancel("Failed: " + str(e))
            return None
    else:
        loader.stop("Session authenticated.")

    loader = Loader("Finalizing session setup...", "", 0.1).start()

    with open("session_auth_pickle", "wb") as f:
        pickle.dump(session.cookies, f)

    loader.stop("Done.")
    return session
