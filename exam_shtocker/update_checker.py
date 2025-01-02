import logging
import re
import requests
from VERSION import VERSION
from colorama import Fore

REMOTE_URL = "https://git.tardisproject.uk/betterinformatics/exam-shtocker"
REMOTE_ISSUES_URL = REMOTE_URL + "/-/issues"
REMOTE_VERSION_URL = REMOTE_URL + "/-/raw/main/exam_shtocker/VERSION.py"


logger = logging.getLogger(__name__)

# Regex to parse the version string from the VERSION file
# This is a simple regex that matches the version string in the format:
# VERSION = "x.y.z"
version_regex = re.compile(r'VERSION = "(.*)"')


def check_for_updates():
    # If there are updates, we will warn but not fail
    try:
        remote_version_file = requests.get(REMOTE_VERSION_URL).text.strip()
        remote_version_search = version_regex.search(remote_version_file)
        if remote_version_search is None:
            print(
                Fore.YELLOW
                + f"! Could not parse remote version file. Please check {REMOTE_ISSUES_URL} for updates."
                + Fore.RESET
            )
            logger.warning(
                f"Could not parse remote version file. Please check {REMOTE_ISSUES_URL} for updates."
            )
            return
        remote_version = remote_version_search.group(1)

        if remote_version != VERSION:
            print(
                Fore.YELLOW
                + f"! New version available: {remote_version}. You are using {VERSION}."
                + Fore.RESET
            )
            logger.warning(
                f"New version available: {remote_version}. You are using {VERSION}."
            )
            logger.warning(
                f"If you encounter issues, we recommend re-downloading the script from {REMOTE_URL}."
            )
        else:
            logger.info("You are using the latest version.")
    except requests.exceptions.ConnectionError:
        logger.warning("Could not check for updates.")
