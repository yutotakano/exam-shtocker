import datetime
import itertools
import requests
import logging
from loader import Loader

logger = logging.getLogger(__name__)


class Exam:
    """Represents an exam paper on exampaers.ed.ac.uk"""

    def __init__(self, title: str, euclid_code: str, year: str, download_url: str):
        self.title = title
        self.euclid_code = euclid_code
        self.year = year
        self.download_url = download_url

    def __str__(self):
        return f"{self.euclid_code}: {self.title} ({self.year}) - {self.download_url}"

    def __repr__(self):
        return str(self)


def scrape_exams_on_page(
    session: requests.Session, page: int, academic_year: str | None = None
) -> tuple[bool, list[Exam]]:
    """Given a page number, scrape and return all exams on that page on
    exampapers.ed.ac.uk. The page number is 0-indexed and is used to paginate
    the search results by 100 items per page.

    Parameters
    ----------
    session : requests.Session
        Session to use for the request.
    page : int
        Page number to scrape. 0-indexed.
    academic_year : str | None
        Academic year to filter exams by. If None, all exams will be returned.

    Returns
    -------
    tuple[bool, list[Exam]]
        Whether this is the last page, and a list of exams on the page.

    Raises
    ------
    Exception
        If the request fails.
    Exception
        If any required fields are missing in the API response.
    """
    loader = Loader(f"Retrieving exams on page {page}...", "", 0.1).start()

    r = session.get(
        f"https://exampapers.ed.ac.uk/server/api/discover/search/objects",
        params={
            # Sort by academic year descending
            "sort": "dc.date.accessioned,DESC",
            # Page is 0 indexed in dspace API
            "page": page,
            # Max 100, other granularity is in browser
            "size": 100,
            # Filter by informatics courses
            "f.author": "Informatics, School of,equals",
            # Traverse API resources to get PDF links in one go - see DSpace API docs
            "embed": "bundles/bitstreams",
            # Only include items with a PDF available
            "f.has_content_in_original_bundle": "true,equals",
            # Filter by academic year if provided
            **({"f.datetemporal": academic_year + ",equals"} if academic_year else {}),
        },
    )

    if r.status_code != 200:
        raise Exception(f"Failed to get page {page}. Status code: {r.status_code}")

    try:
        data = r.json()
    except Exception as e:
        logger.error("Could not decode response as JSON, is the user really logged in?")
        raise e

    if "_embedded" not in data or "searchResult" not in data["_embedded"]:
        raise Exception(
            "Unexpected response format from the API: _embedded.searchResult not found"
        )

    search_result = data["_embedded"]["searchResult"]

    # Check if this is the final page using the pagination info
    if (
        "page" not in search_result
        or "totalPages" not in search_result["page"]
        or "number" not in search_result["page"]
    ):
        raise Exception(
            "Unexpected response format from the API: searchResult.page.totalPages/number not found"
        )

    this_page_final = (
        search_result["page"]["totalPages"] == search_result["page"]["number"] + 1
    )
    items_on_page = len(search_result["_embedded"]["objects"])

    # Parse exams
    exams: list[Exam] = []
    if "_embedded" not in search_result or "objects" not in search_result["_embedded"]:
        raise Exception(
            "Unexpected response format from the API: searchResult._embedded.objects not found"
        )

    for exam_node in search_result["_embedded"]["objects"]:
        if (
            "_embedded" not in exam_node
            or "indexableObject" not in exam_node["_embedded"]
        ):
            raise Exception(
                "Unexpected response format from the API: Exam node doesn't have indexableObject"
            )

        if "metadata" not in exam_node["_embedded"]["indexableObject"]:
            raise Exception(
                "Unexpected response format from the API: indexableObject doesn't have metadata"
            )

        metadata = exam_node["_embedded"]["indexableObject"]["metadata"]

        if (
            "dc.identifier" not in metadata
            or "dc.date.issued" not in metadata
            or "dc.title" not in metadata
        ):
            raise Exception(
                "Unexpected response format from the API: metadata missing euclid code or exam date"
            )

        course_code = metadata["dc.identifier"][0]["value"]
        # Parse "YYYY-MM-DD" as date and and create "YYYY MMM"
        try:
            year = datetime.datetime.strptime(
                metadata["dc.date.issued"][0]["value"], "%Y-%m-%d"
            ).strftime("%Y %b")
        except ValueError:
            # Old exams (around 2020) could be in format "DD-MM-YYYY"
            year = datetime.datetime.strptime(
                metadata["dc.date.issued"][0]["value"], "%d-%m-%Y"
            ).strftime("%Y %b")

        title = metadata["dc.title"][0]["value"]

        # There's a lot of useless nesting in the DSpace API when requesting embedded resources
        if (
            "_embedded" not in exam_node["_embedded"]["indexableObject"]
            or "bundles" not in exam_node["_embedded"]["indexableObject"]["_embedded"]
            or "_embedded"
            not in exam_node["_embedded"]["indexableObject"]["_embedded"]["bundles"]
            or "bundles"
            not in exam_node["_embedded"]["indexableObject"]["_embedded"]["bundles"][
                "_embedded"
            ]
        ):
            raise Exception(
                "Unexpected response format from the API: indexableObject doesn't have bundles"
            )

        # Get all bitstream nodes in all bundles
        bitstreams = itertools.chain.from_iterable(
            bundle["_embedded"]["bitstreams"]["_embedded"]["bitstreams"]
            for bundle in exam_node["_embedded"]["indexableObject"]["_embedded"][
                "bundles"
            ]["_embedded"]["bundles"]
        )

        # Filter for the bitstream in the original bundle, which contains the PDF
        original_node = [
            b for b in bitstreams if "bundleName" in b and b["bundleName"] == "ORIGINAL"
        ][0]

        download_url = original_node["_links"]["content"]["href"]
        exams.append(Exam(title, course_code, year, download_url))

    loader.stop(f"{items_on_page} exams downloadable.")

    return this_page_final, exams
