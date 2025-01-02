import requests
from typing import Optional
import logging
import getpass
import re
import os
import pickle
import html
from colorama import Style
from loader import Loader

import requests.cookies

logger = logging.getLogger(__name__)


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
    if "ease.ed.ac.uk/cosign" in r.url or "idp.ed.ac.uk" in r.url:
        loader.cancel("Session needs login.")

        username = perform_interactive_ease_login(session)
        if not username:
            logger.error("Could not log into EASE (invalid credentials?).")
            return None

        try:
            perform_exampapers_login(session)
        except Exception as e:
            logger.error("Failed to log into ExamPapers: " + str(e))
            loader.cancel("Failed: " + str(e))
            return None
    else:
        loader.stop("Session authenticated.")

    loader = Loader("Finalizing session setup...", "", 0.1).start()

    with open("session_auth_pickle", "wb") as f:
        pickle.dump(session.cookies, f)

    loader.stop("Done.")
    return session
