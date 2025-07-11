import itertools
import requests
import logging
from loader import Loader

logger = logging.getLogger(__name__)


class Exam:
    """Represents an exam paper on exampaers.ed.ac.uk"""

    def __init__(self, title: str, infr_code: str, download_url: str):
        self.title = title
        self.infr_code = infr_code
        self.download_url = download_url

    def __str__(self):
        return f"{self.infr_code}: {self.title} - {self.download_url}"

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

    data = r.json()
    if "_embedded" not in data or "searchResult" not in data["_embedded"]:
        raise Exception("Unexpected response format from the API: _embedded.searchResult not found")

    # Check if this is the final page using the pagination info
    if ("page" not in data["_embedded"]["searchResult"] or
        "totalPages" not in data["_embedded"]["searchResult"]["page"] or
        "number" not in data["_embedded"]["searchResult"]["page"] or
        "size" not in data["_embedded"]["searchResult"]["page"]):
        raise Exception("Unexpected response format from the API: _embedded.searchResult.page.totalPages/number not found")

    this_page_final = data["_embedded"]["searchResult"]["page"]["totalPages"] == data["_embedded"]["searchResult"]["page"]["number"] + 1
    items_on_page = data["_embedded"]["searchResult"]["page"]["size"]

    # Parse exams
    exams: list[Exam] = []
    if ("_embedded" not in data["_embedded"]["searchResult"] or
        "objects" not in data["_embedded"]["searchResult"]["_embedded"]):
        raise Exception("Unexpected response format from the API: _embedded.searchResult._embedded.objects not found")

    for exam_node in data["_embedded"]["searchResult"]["_embedded"]["objects"]:
        if "_embedded" not in exam_node or "indexableObject" not in exam_node["_embedded"]:
            raise Exception("Unexpected response format from the API: Exam node doesn't have indexableObject")

        if "metadata" not in exam_node["_embedded"]["indexableObject"]:
            raise Exception("Unexpected response format from the API: indexableObject doesn't have metadata")

        if ("dc.identifier" not in exam_node["_embedded"]["indexableObject"]["metadata"] or
            "dc.date.issued" not in exam_node["_embedded"]["indexableObject"]["metadata"] or
            "dc.title" not in exam_node["_embedded"]["indexableObject"]["metadata"]):
            raise Exception("Unexpected response format from the API: indexableObject metadata missing euclid code or exam date")

        course_code = exam_node["_embedded"]["indexableObject"]["metadata"]["dc.identifier"][0]["value"]
        title = exam_node["_embedded"]["indexableObject"]["metadata"]["dc.title"][0]["value"]

        # There's a lot of useless nesting in the DSpace API when requesting embedded resources
        if ("_embedded" not in exam_node["_embedded"]["indexableObject"] or
            "bundles" not in exam_node["_embedded"]["indexableObject"]["_embedded"] or
            "_embedded" not in exam_node["_embedded"]["indexableObject"]["_embedded"]["bundles"] or
            "bundles" not in exam_node["_embedded"]["indexableObject"]["_embedded"]["bundles"]["_embedded"]):
            raise Exception("Unexpected response format from the API: indexableObject doesn't have bundles")

        # Get all bitstream nodes in all bundles
        bitstreams = itertools.chain.from_iterable(
            bundle["_embedded"]["bitstreams"]["_embedded"]["bitstreams"]
            for bundle in exam_node["_embedded"]["indexableObject"]["_embedded"]["bundles"]["_embedded"]["bundles"]
        )

        # Filter for the bitstream in the original bundle, which contains the PDF
        original_node = [
            b for b in bitstreams if "bundleName" in b and b["bundleName"] == "ORIGINAL"
        ][0]

        download_url = original_node["_links"]["content"]["href"]
        exams.append(Exam(title, course_code, download_url))

    loader.stop(
        f"{items_on_page} exams downloadable."
    )

    return this_page_final, exams
