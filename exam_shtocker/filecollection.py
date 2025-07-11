import requests
from typing import Optional
import hashlib
import os
import logging
import re
import pypdf

logger = logging.getLogger(__name__)

bi_api_key = os.environ.get("BI_API_KEY")
if bi_api_key is None:
    raise Exception("BI_API_KEY environment variable not set.")

def get_category_slug_for_infr_code(session: requests.Session, infr_code: str) -> str:
    """Get the Better Informatics category slug for a given INFR EUCLID code.

    Parameters
    ----------
    session : requests.Session
        Session to use for the request.
    infr_code : str
        EUCLID code of the course.

    Returns
    -------
    str
        Better Informatics category slug.

    Raises
    ------
    Exception
        If the request fails, for example if the INFR code is invalid or if no
        category was found on BI matching the provided EUCLID code.
    """
    # Does not need login
    r = session.get(
        f"https://files.betterinformatics.com/api/category/slugfromeuclidcode?code={infr_code}"
    )
    if r.status_code != 200:
        raise Exception(
            f"Failed ({r.status_code}) to get slug for INFR code: {infr_code}"
        )

    return r.json()["value"]


def get_hashes_for_category(session: requests.Session, slug: str) -> list[bytes]:
    """Retrieve the hashes of all exams in a given Better Informatics category.
    Requires the `BI_API_KEY` environment variable to be set with the BI API
    key defined in the BI container manifest (e.g. docker-compose.yaml or k8s).

    Parameters
    ----------
    session : requests.Session
        Session to use for the request.
    slug : str
        Slug of the category to get the hashes for. Use get_category_slug_for_infr_code
        to get the slug for a given INFR code.

    Returns
    -------
    list[bytes]
        List of file hashes for all exams in the category.

    Raises
    ------
    Exception
        If the BI_API_KEY environment variable is not set.
    Exception
        If the request fails, for example if the category slug is invalid.
    Exception
        If the download of an exam fails.
    """
    logger.debug(f"Getting exam list for category {slug}...")

    # Requires login
    r = session.get(
        f"https://files.betterinformatics.com/api/category/listexams/{slug}/",
        headers={"X-COMMUNITY-SOLUTIONS-API-KEY": bi_api_key},
    )
    if r.status_code != 200:
        raise Exception(
            f"Failed ({r.status_code}) to get exam list for category: {slug}."
        )

    hashes: list[bytes] = []
    for exam_file in r.json()["value"]:
        logger.debug(
            f"Downloading {exam_file['category_displayname']} {exam_file['displayname']} ({exam_file['filename']})..."
        )
        r = session.get(
            f"https://files.betterinformatics.com/api/exam/pdf/exam/{exam_file['filename']}/",
            headers={"X-COMMUNITY-SOLUTIONS-API-KEY": bi_api_key},
        )
        if r.status_code != 200:
            raise Exception(
                f"Failed ({r.status_code}) to download exam {exam_file['filename']}."
            )

        contents = session.get(r.json()["value"]).content

        # Return the hash of the file
        hashes.append(hashlib.sha256(contents).digest())

    logger.debug(f"Got {len(hashes)} hashes.")
    return hashes


def try_parse_exam_pdf_diet(pdf_filepath: str) -> Optional[str]:
    """Given a PDF file, try to extract the exam diet from the first page. The
    exam diet is assumed to be in the format "Month Year", such as "May 2021".

    Parameters
    ----------
    pdf_filepath : str
        Path to the PDF file.

    Returns
    -------
    Optional[str]
        Extracted exam diet if found, None otherwise.
    """
    pdf_reader = pypdf.PdfReader(pdf_filepath)
    text = pdf_reader.pages[0].extract_text()
    match = re.search(
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|(Nov|Dec)(?:ember)?)\D?(\d{1,2}\D?)?\D?((19[7-9]\d|20\d{2})|\d{2})",
        text,
    )
    if match:
        return match.group(0)

    return None


def upload_exam(session: requests.Session, infr_code: str, filepath: str) -> str:
    """Upload an exam PDF to Better Informatics under the category matching the
    given INFR EUCLID code.

    Parameters
    ----------
    session : requests.Session
        Session to use for uploading.
    infr_code : str
        EUCLID code of the course.
    filepath : str
        Path to the PDF file to upload.

    Returns
    -------
    str
        The URL of the uploaded exam.

    Raises
    ------
    Exception
        If upload fails, for example if the file is too large, the API key is
        invalid, the file does not end with a .pdf extension, or there was no
        category on BI matching the provided EUCLID code.
    """
    logger.info(f"Uploading {filepath} for {infr_code}...")

    slug = get_category_slug_for_infr_code(session, infr_code)

    diet = try_parse_exam_pdf_diet(filepath)

    # Get the upload page to get the CSRF token in the cookies
    r = session.get("https://files.betterinformatics.com/uploadpdf/")

    with open(filepath, "rb") as file:
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
            files={"file": file},
        )
    if r.status_code != 200:
        raise Exception(f"Failed to upload {filepath} for {infr_code}: {r.text}")

    filename = r.json()["filename"]
    return f"https://files.betterinformatics.com/exams/{filename}"
