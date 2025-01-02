import logging
import argparse
import random
from colorama import Fore
import requests
import sys
import os
import auth
import scraper
import time
import filecollection
import hashlib
import tempfile
from loader import Loader

REMOTE_URL = "https://git.tardisproject.uk/betterinformatics/exam-shtocker"
REMOTE_ISSUES_URL = REMOTE_URL + "/-/issues"
REMOTE_VERSION_URL = REMOTE_URL + "/-/raw/main/VERSION"
VERSION = "1.0.0"


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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

    # Setup authenticated session for the script
    session = auth.setup_session()
    if not session:
        logger.error("Could not setup authenticated session.")
        print(Fore.RED + "Could not setup authenticated session." + Fore.RESET)
        return 1

    # Create an instance of the ExamProcessor to process exams
    processor = ExamProcessor(session)

    # Loop through all pages of exams (search query: INFR) and process each one.
    more_exams_exist = True
    page = 1
    try:
        while more_exams_exist:
            this_page_final, exams = scraper.scrape_exams_on_page(session, page)
            more_exams_exist = not this_page_final
            logger.info(
                f"Processing page {page} with {len(exams)} downloadable exams. This page is {'' if this_page_final else 'not '}the last page."
            )

            processor.process_exams(exams)

            # Sleeping for 15 seconds to avoid rate-limiting
            time.sleep(15)
            page += 1
        return 0
    except Exception as e:
        print(Fore.RED + str(e) + Fore.RESET)
        exit(1)


class ExamProcessor:
    session: requests.Session
    uploaded_hashes_by_infr_code: dict[str, list[bytes]]

    loader = None

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
        assert self.loader is not None

        if infr_code not in self.uploaded_hashes_by_infr_code:
            logger.debug(f"Determining BI slug for {infr_code}...")
            self.loader.desc = f"Determining BI slug for {infr_code}..."

            slug = filecollection.get_category_slug_for_infr_code(
                self.session, infr_code
            )

            logger.debug(f"Downloading and calculating hashes for {str(slug)}...")
            self.loader.desc = f"Calculating hashes for {slug}..."

            self.uploaded_hashes_by_infr_code[infr_code] = (
                filecollection.get_hashes_for_category(self.session, slug)
            )

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
            i_str = f"{i + 1}/{len(exams)}"
            if self.loader is None:
                self.loader = Loader(f"{i_str} Waiting...", "", 0.1).start()
            else:
                self.loader.desc = f"{i_str} Waiting..."

            # Sleep for up to 5 seconds between each exam to avoid having
            # ease account being flagged for abuse
            time.sleep(random.randint(1, 5))

            logger.debug(f"{i_str} Processing exam: {exam}")
            self.loader.desc = f"{i_str} Downloading {exam.infr_code}: {exam.title}..."

            # First, download the exam to a temporary directory and calculate
            # its file hash
            downloaded_filepath, file_hash = self.download_exam(exam)

            # Check if the file has already been uploaded by comparing against
            # the hashes of all exams for the INFR code on BI
            if file_hash in self.get_hashes_for_infr_code(exam.infr_code):
                logger.info(f"Skipping upload: Already exists.")
                os.remove(downloaded_filepath)
                # We reuse the same loader instance, so we don't set self.loader = None
                continue

            # Upload the file
            logger.debug(f"{i_str} Uploading to BI: {exam.infr_code} {exam.title}...")
            self.loader.desc = f"{i_str} Uploading {exam.title}..."
            url = filecollection.upload_exam(
                self.session, exam.infr_code, downloaded_filepath
            )

            # Show a completed line that remains on screen by stopping the loader
            self.loader.stop(f"Done ({url}).")
            self.loader = None

    def download_exam(self, exam: scraper.Exam) -> tuple[str, bytes]:
        """Given an Exam object, download the exam from exampapers to a
        temporary file and return the file path and hash.

        Parameters
        ----------
        exam : scraper.Exam
            Exam to download.

        Returns
        -------
        tuple[Optional[str], bytes]
            File path of the downloaded exam and its hash.
        """
        logger.debug(f"Downloading {exam.infr_code}: {exam.title}...")
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
        filename="exam_shtocker.log",
        filemode="a",
        format="%(asctime)s,%(msecs)d %(name)s %(levelname)s%(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # Color the log level prefixes unless the output is INFO or is piped
    logging.addLevelName(logging.INFO, f"   info ")
    logging.addLevelName(logging.ERROR, f"  error ")
    logging.addLevelName(logging.WARNING, f"warning ")
    logging.addLevelName(logging.DEBUG, f"  debug ")

    sys.exit(main(args))
