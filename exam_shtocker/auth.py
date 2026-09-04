from typing import Optional
import logging
from getpass import getpass
import json
import os
import pickle

import requests
import requests.cookies
import uoe_ms_auth

from loader import Loader

logger = logging.getLogger(__name__)


def perform_microsoft_login(session: requests.Session) -> bool:
    cookies = uoe_ms_auth.authenticate(
        username=get_email(),
        password=getpass(),
        otp_callback=lambda: input("Please provide an OTP code from your microsoft authenticator: "),
        approval_callback=lambda code: print(f"Please approve the following signin code: {code}\r", end=""),
    )
    if cookies is None:
        return False 
    session.cookies = create_cookie_jar(json.loads(cookies))
    return True 

def create_cookie_jar(cookies_list):
    jar = requests.cookies.RequestsCookieJar()
    for cookie in cookies_list:
        jar.set(
            name=cookie['name'],
            value=cookie['value'],
            domain=cookie.get('domain', ''),
            path=cookie.get('path', '/'),
            secure=cookie.get('secure', False),
            rest={'HttpOnly': cookie.get('httpOnly', False)}
        )
    return jar

def get_email() -> str:
    while True:
        email = input("Please enter your university email: ")
        if email.endswith("@ed.ac.uk"):
            return email 
        print("Please enter email in the format s1234567@ed.ac.uk")


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
            if not perform_microsoft_login(session):
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
