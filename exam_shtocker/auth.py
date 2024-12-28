import requests
from typing import Optional
import logging
import getpass
import re
import os
import pickle
import html

import requests.cookies

logger = logging.getLogger(__name__)


def perform_ease_login(session: requests.Session) -> Optional[str]:
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
    logging.info(
        "This course requires authentication. Please provide your EASE credentials."
    )
    username = input("Username: ")
    password = getpass.getpass("Password: ")

    # Get once to set the cookies
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
        return None

    return username


def create_auth_session() -> Optional[requests.Session]:
    session = requests.Session()

    if os.path.exists("session_auth_pickle"):
        with open("session_auth_pickle", "rb") as f:
            cookies: requests.cookies.RequestsCookieJar = pickle.load(f)
            session.cookies = cookies

    # Try to get it on the first try, if it fails, try logging in
    r = session.get("https://exampapers.ed.ac.uk")
    if "ease.ed.ac.uk/cosign" in r.url or "idp.ed.ac.uk" in r.url:
        username = perform_ease_login(session)
        if not username:
            logger.error("Could not log into EASE (invalid credentials?).")
            return None

        r = session.get("https://exampapers.ed.ac.uk")

        saml_response = re.search(
            r"<input type=\"hidden\" name=\"SAMLResponse\" value=\"(.*)\"/>", r.text
        )
        if not saml_response:
            logger.error("Could not find SAMLResponse input field.")
            return None

        saml_response = saml_response.group(1)
        logger.debug(f"SAMLResponse: {saml_response}")

        # Get the value of the RelayState input field
        relay_state = re.search(
            r"<input type=\"hidden\" name=\"RelayState\" value=\"(.*)\"/>", r.text
        )
        if not relay_state:
            logger.error("Could not find RelayState input field.")
            return None

        relay_state = html.unescape(relay_state.group(1))
        logger.debug(f"RelayState: {relay_state}")

        # Login to ExamPapers
        logger.info("Sending exampapers the SAMLResponse...")
        r = session.post(
            "https://exampapers.ed.ac.uk/Shibboleth.sso/SAML2/POST",
            data={"SAMLResponse": saml_response, "RelayState": relay_state},
        )

        if r.url != "https://exampapers.ed.ac.uk/":
            logger.error("Could not log into ExamPapers. Error below ---v")
            logger.debug(r.url)
            logger.debug(r.text)
            return None

    with open("session_auth_pickle", "wb") as f:
        pickle.dump(session.cookies, f)
    return session
