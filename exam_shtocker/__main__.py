import logging
import argparse
import random
import requests
import sys
import os
import auth
import scraper
import time
import filecollection
from typing import Optional
import hashlib
import tempfile

REMOTE_URL = "https://git.tardisproject.uk/betterinformatics/exam-shtocker"
REMOTE_ISSUES_URL = REMOTE_URL + "/-/issues"
REMOTE_VERSION_URL = REMOTE_URL + "/-/raw/main/VERSION"
VERSION = "1.0.0"
OUTPUT_IS_TTY = sys.stdout.isatty()


# A quick lookup table for colors to use in the terminal. If the attached output
# is not a console, we will disable the colors.
class Colors:
    DEBUG = "\033[94m" if OUTPUT_IS_TTY else ""
    ERROR = "\033[91m" if OUTPUT_IS_TTY else ""
    WARNING = "\033[93m" if OUTPUT_IS_TTY else ""
    ENDC = "\033[0m" if OUTPUT_IS_TTY else ""


logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument(
    "-v",
    "--verbose",
    action="store_true",
    help="Prints additional debugging information.",
)
parser.add_argument(
    "--version",
    action="store_true",
    help="Prints the current version of the script and exit.",
)

parser.add_argument(
    "-u",
    "--skip-update-check",
    action="store_true",
    help="Skip checking for updates for the script.",
)


def main(args: argparse.Namespace) -> int:
    """Central logic of the script.

    Parameters
    ----------
    args : argparse.Namespace
        Arguments passed to the script.

    Returns
    -------
    int
        Exit code
    """
    logger.debug("This log line is only visible if --verbose flag is set.")

    if args.version:
        logging.info(VERSION)
        return 0

    # If there are updates, we will warn but not fail
    # if not args.skip_update_check:
    #     try:
    #         remote_version = requests.get(REMOTE_VERSION_URL).text.strip()
    #         if remote_version != VERSION:
    #             logger.warning(
    #                 f"New version available: {remote_version}. You are using {VERSION}."
    #             )
    #             logger.warning(
    #                 f"If you encounter issues, we recommend re-downloading the script from {REMOTE_URL}."
    #             )
    #     except requests.exceptions.ConnectionError:
    #         logger.warning("Could not check for updates.")
    # else:
    #     logger.info("Skipping update check.")

    session = auth.create_auth_session()
    if not session:
        logger.error("Could not create authenticated session.")
        return 1

    processor = ExamProcessor(session)
    more_exams_exist = True
    page = 1
    while more_exams_exist:
        this_page_final, exams = scraper.scrape_exams_on_page(session, page)
        more_exams_exist = not this_page_final
        logger.info(f"Processing page {page} with {len(exams)} exams.")
        page += 1

        processor.process_exams(exams)

        logger.debug(f"Sleeping for 15 seconds to avoid rate-limiting...")
        time.sleep(15)
    return 0


class ExamProcessor:
    session: requests.Session
    uploaded_hashes_by_infr_code: dict[str, list[bytes]]

    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.uploaded_hashes_by_infr_code = {}

    def get_hashes_for_infr_code(self, infr_code: str) -> list[bytes]:
        """Get the hashes of all exams for a given INFR code that have been
        uploaded. If this is unknown, the function will download all files in
        the category and store the hashes.

        Parameters
        ----------
        infr_code : str
            INFR code to get the hashes for.

        Returns
        -------
        list[bytes]
            List of hashes of all exams for the given INFR code that have been uploaded.
        """
        logger.debug(f"Getting hashes for {infr_code}...")
        print("...finding existing exams...", end="\r")
        if infr_code not in self.uploaded_hashes_by_infr_code:
            logger.debug(f"Calculating hashes for {infr_code}...")
            print("...calculating existing hashes...", end="\r")
            slug = filecollection.get_category_slug_for_infr_code(
                self.session, infr_code
            )
            logger.debug("Resolved infr code corresponding slug: " + str(slug))
            if not slug:
                logger.error(f"Could not get slug for INFR code: {infr_code}")
                return []

            self.uploaded_hashes_by_infr_code[infr_code] = (
                filecollection.get_hashes_for_category(self.session, slug)
            )

        print("...comparing...", end="\r")
        return self.uploaded_hashes_by_infr_code[infr_code]

    def process_exams(self, exams: list[scraper.Exam]) -> None:
        """Process a list of exams by downloading each one.

        Parameters
        ----------
        session : requests.Session
            Authenticated session to use for downloading.
        exams : list[scraper.Exam]
            List of exams to process.
        """
        for i, exam in enumerate(exams):
            # Sleep for up to 5 seconds between each exam to avoid having
            # ease account being flagged for abuse
            time.sleep(random.randint(1, 5))

            # Check if we have the hashes of all pre-uploaded exams in this category

            logger.debug(f"{i + 1}/{len(exams)} Processing exam: {exam}")
            print(f"({i + 1}/{len(exams)}) {exam.infr_code}: {exam.title}")

            downloaded_filepath, file_hash = self.download_exam(exam)

            if not downloaded_filepath:
                logger.error(f"Failed to download exam. Check with -v.")
                continue

            # Check if the file has already been uploaded
            if file_hash in self.get_hashes_for_infr_code(exam.infr_code):
                logger.warning(f"Skipping: Already uploaded.")
                os.remove(downloaded_filepath)
                continue

            # Upload the file
            logger.debug(f"Uploading to BI: {exam.infr_code} {exam.title}...")
            print("...uploading...", end="\r")
            succeeded = filecollection.upload_exam(
                self.session, exam.infr_code, downloaded_filepath
            )
            if not succeeded:
                logger.error(f"Failed to upload exam: {exam.title}.")
                continue

            print("...done!")

    def download_exam(self, exam: scraper.Exam) -> tuple[Optional[str], bytes]:
        logger.debug(f"Downloading {exam.infr_code}: {exam.title}...")
        print("...downloading...", end="\r")
        contents = self.session.get(
            "https://exampapers.ed.ac.uk" + exam.download_url
        ).content
        file_hash = hashlib.sha256(contents).digest()

        # write to tmp file
        _, name = tempfile.mkstemp(suffix=".pdf")
        with open(name, "wb") as f:
            f.write(contents)

        logger.debug(f"Downloaded to {name} with hash {file_hash}")
        return name, file_hash


if __name__ == "__main__":
    args = parser.parse_args()

    logging.basicConfig(
        format="%(levelname)s%(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # Color the log level prefixes unless the output is INFO or is piped
    logging.addLevelName(logging.INFO, f"")
    logging.addLevelName(logging.ERROR, f"{Colors.ERROR}ERROR{Colors.ENDC} ")
    logging.addLevelName(logging.WARNING, f"{Colors.WARNING}WARN{Colors.ENDC} ")
    logging.addLevelName(logging.DEBUG, f"{Colors.DEBUG}DEBUG{Colors.ENDC} ")

    sys.exit(main(args))
