import logging
import argparse
from colorama import Fore
import sys
import auth
import update_checker
import scraper
import time
from processor import ExamProcessor
from VERSION import VERSION


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
parser.add_argument(
    "-n",
    "--dry-run",
    action="store_true",
    help="Do not upload any files, just print what would be uploaded. Still requires a valid BI_API_KEY.",
)
parser.add_argument(
    "--continue-on-unknown-code",
    help="Provide without arguments to keep processing when encountering any unknown code. Provide with an argument to specify comma-separated prefixes to skip, and otherwise error on unknown codes. For example, `--continue-on-unknown-code EPCC` will skip EPCC codes but error on unknown INFR codes.",
    action="store",
    default=None,
    type=str,
    nargs="?",
    const="",
    metavar="PREFIXES",
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

    if not args.skip_update_check:
        logger.info("Checking for updates...")
        update_checker.check_for_updates()
    else:
        logger.info("Skipping update check.")

    if args.dry_run:
        logger.warning("Running as a dry run.")
        print(
            Fore.YELLOW
            + "Dry run. The script will check for exams and print what would be uploaded, but not actually upload anything."
            + Fore.RESET
        )
        print(
            Fore.YELLOW
            + "To upload exams, run the script without --dry-run."
            + Fore.RESET
        )

    if args.continue_on_unknown_code is not None:
        if args.continue_on_unknown_code == "":
            args.continue_on_unknown_code = [""]  # prefix to match all unknown codes
            logger.info("Continuing without error on any unknown code.")
        else:
            args.continue_on_unknown_code = args.continue_on_unknown_code.split(",")
            args.continue_on_unknown_code = [
                prefix.strip() for prefix in args.continue_on_unknown_code
            ]
            logger.info(
                f"Continuing without error on unknown codes with prefixes: {args.continue_on_unknown_code}"
            )
    else:
        logger.info(
            "Will error on unknown codes. Use --continue-on-unknown-code to change this behavior."
        )

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
    page = 0
    try:
        while more_exams_exist:
            this_page_final, exams = scraper.scrape_exams_on_page(session, page)
            more_exams_exist = not this_page_final
            logger.info(
                f"Processing page {page} with {len(exams)} downloadable exams. This page is {'' if this_page_final else 'not '}the last page."
            )

            processor.process_exams(exams, args.dry_run, args.continue_on_unknown_code)

            # Sleeping for 15 seconds to avoid rate-limiting
            time.sleep(15)
            page += 1
        return 0
    except Exception as e:
        print(Fore.RED + str(e) + Fore.RESET)
        exit(1)


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
