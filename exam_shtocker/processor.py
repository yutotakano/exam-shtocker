import hashlib
import os
import random
import time
import requests
from loader import Loader
import logging
import filecollection
import known_bads
import scraper
import tempfile

logger = logging.getLogger(__name__)


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

    def process_exams(
        self,
        exams: list[scraper.Exam],
        dry_run: bool,
        continue_on_unknown_code: list[str] | None,
    ) -> None:
        """Process a list of exams by downloading each one.

        Parameters
        ----------
        session : requests.Session
            Authenticated session to use for downloading.
        exams : list[scraper.Exam]
            List of exams to process.
        dry_run : bool
            If True, the function will not actually upload the file, but will
            print what would be uploaded.
        continue_on_unknown_code : list[str] | None
            If None, the function will error on unknown codes. If a list of
            prefixes is provided, the function will skip any exam with a prefix
            in the list and error on any other unknown code.
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

            logger.info(f"{i_str} Processing exam: {exam}")
            self.loader.desc = f"{i_str} Downloading {exam.infr_code}: {exam.title}..."

            # First, download the exam to a temporary directory and calculate
            # its file hash
            downloaded_filepath, file_hash = self.download_exam(exam)
            logger.info(f"{i_str} Hash: {file_hash.hex()}")

            # Check if this is a known bad hash
            if file_hash in known_bads.known_bad_hashes:
                logger.info(
                    f"Skipping {exam.infr_code}: {exam.title} due to known bad hash."
                )
                os.remove(downloaded_filepath)
                continue

            # Check if the file has already been uploaded by comparing against
            # the hashes of all exams for the INFR code on BI
            try:
                if file_hash in self.get_hashes_for_infr_code(exam.infr_code):
                    logger.info(f"Skipping upload: Already exists.")
                    os.remove(downloaded_filepath)
                    # We reuse the same loader instance, so we don't set self.loader = None
                    continue
            except Exception as e:
                if continue_on_unknown_code is not None:
                    # If we are continuing on unknown codes, we skip this exam
                    if any(
                        exam.infr_code.startswith(prefix)
                        for prefix in continue_on_unknown_code
                    ):
                        logger.warning(
                            f"Skipping {exam.infr_code}: {exam.title} due to code matching known continuation prefixes."
                        )
                        if (
                            len(continue_on_unknown_code) == 1
                            and continue_on_unknown_code[0] == ""
                        ):
                            # If the user specified continuation but without any prefixes,
                            # warn explicitly that it was skipped. But if they gave prefixes,
                            # silently skip.
                            self.loader.stop(
                                f"Skipping: {exam.infr_code} {exam.title} does not exist on BI and --continue-on-unknown-code provided. Provide an explicit skip prefix to hide this message."
                            )
                            self.loader = None
                        os.remove(downloaded_filepath)
                        continue
                raise e

            # Upload the file
            logger.debug(f"{i_str} Uploading to BI...")
            self.loader.desc = f"{i_str} Uploading {exam.title} ({exam.year})..."
            if dry_run:
                logger.info(f"Skipping upload: Dry run.")
                self.loader.stop(
                    f"Skipping: Dry run. To upload, run without --dry-run."
                )
                self.loader = None
                continue

            url = filecollection.upload_exam(
                self.session, exam.infr_code, downloaded_filepath
            )

            # Add the hash to the list of uploaded hashes
            self.uploaded_hashes_by_infr_code[exam.infr_code].append(file_hash)

            # Show a completed line that remains on screen by stopping the loader
            self.loader.stop(f"Done ({url}).")
            self.loader = None

        # Loader must be stopped after processing all exams or else it will try
        # to conflict with the next page's scraping loader
        if self.loader is not None:
            self.loader.stop("All exams on page processed.")
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
        contents = self.session.get(exam.download_url).content
        file_hash = hashlib.sha256(contents).digest()

        # write to tmp file
        f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        f.write(contents)
        f.close()

        logger.debug(f"Downloaded to {f.name} with hash {file_hash}")
        return f.name, file_hash
