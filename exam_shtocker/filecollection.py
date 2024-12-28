import requests
from typing import Optional
import hashlib
import os
import logging
import re
import pypdf

logger = logging.getLogger(__name__)


def get_category_slug_for_infr_code(
    session: requests.Session, infr_code: str
) -> Optional[str]:
    # Does not need login
    r = session.get(
        f"https://files.betterinformatics.com/api/category/slugfromeuclidcode?code={infr_code}"
    )
    if r.status_code != 200:
        return None

    return r.json()["value"]


def get_hashes_for_category(session: requests.Session, slug: str) -> list[bytes]:
    logger.debug(f"Getting exam list for category {slug}...")
    print(f"...downloading existing exams in {slug}...", end="\r")

    # Requires login
    r = session.get(
        f"https://files.betterinformatics.com/api/category/listexams/{slug}/",
        headers={"X-COMMUNITY-SOLUTIONS-API-KEY": os.environ["BI_API_KEY"]},
    )
    if r.status_code != 200:
        return []

    hashes: list[bytes] = []
    for exam_file in r.json()["value"]:
        logger.debug(
            f"Downloading {exam_file['category_displayname']} {exam_file['displayname']} ({exam_file['filename']})..."
        )
        r = session.get(
            f"https://files.betterinformatics.com/api/exam/pdf/exam/{exam_file['filename']}/",
            headers={"X-COMMUNITY-SOLUTIONS-API-KEY": os.environ["BI_API_KEY"]},
        )
        if r.status_code != 200:
            return []

        contents = session.get(r.json()["value"]).content

        # Return the hash of the file
        hashes.append(hashlib.sha256(contents).digest())

    logger.debug(f"Got {len(hashes)} hashes.")
    return hashes


def get_diet_for_exam(pdf_filepath: str) -> Optional[str]:
    pdf_reader = pypdf.PdfReader(pdf_filepath)
    text = pdf_reader.pages[0].extract_text()
    match = re.search(
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|(Nov|Dec)(?:ember)?)\D?(\d{1,2}\D?)?\D?((19[7-9]\d|20\d{2})|\d{2})",
        text,
    )
    if match:
        return match.group(0)
    return None


def upload_exam(session: requests.Session, infr_code: str, filepath: str) -> bool:
    logger.info(f"Uploading {filepath} for {infr_code}...")
    # Requires login
    slug = get_category_slug_for_infr_code(session, infr_code)
    if not slug:
        return False

    diet = get_diet_for_exam(filepath)

    # Get the upload page to get the CSRF token in the cookies
    r = session.get("https://files.betterinformatics.com/uploadpdf/")

    r = session.post(
        f"https://files.betterinformatics.com/api/exam/upload/exam/",
        headers={
            "X-COMMUNITY-SOLUTIONS-API-KEY": os.environ["BI_API_KEY"],
            "X-CSRFToken": session.cookies["csrftoken"],
            # Referer needed to pass the CSRF check in addition to cookies
            "Referer": f"https://files.betterinformatics.com/uploadpdf/",
        },
        data={
            "category": slug,
            "displayname": diet or f"{infr_code} - Unknown diet",
        },
        files={"file": open(filepath, "rb")},
    )
    if r.status_code != 200:
        logger.error(f"Failed to upload {filepath} for {infr_code}.")
        logger.error(r.text)
        exit(1)

    return r.status_code == 200
