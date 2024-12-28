import requests
import bs4
import logging

logger = logging.getLogger(__name__)


class Exam:
    def __init__(self, title: str, infr_code: str, download_url: str):
        self.title = title
        self.infr_code = infr_code
        self.download_url = download_url

    def __str__(self):
        return f"{self.infr_code}: {self.title} - {self.download_url}"

    def __repr__(self):
        return str(self)


def scrape_exams_on_page(
    session: requests.Session, page: int
) -> tuple[bool, list[Exam]]:
    r = session.post(
        f"https://exampapers.ed.ac.uk/discover",
        data={
            "search-result": "true",
            # Search by "INFR" to get all Informatics exams
            "query": "infr",
            "scope": "/",
            "rpp": 100,
            "etal": 0,
            "sort_by": "dc.date.issued_dt",
            "group_by": "none",
            "order": "desc",
            "page": str(page),
        },
    )
    if r.status_code != 200:
        logger.error(f"Failed to get page {page}.")
        return True, []

    soup = bs4.BeautifulSoup(r.text, "html.parser")

    # Find pagination-info element which contains the total number of items
    pagination_info_elem = soup.find("p", class_="pagination-info")
    if pagination_info_elem is None:
        logger.error("Could not find pagination info.")
        return True, []

    # Parse "Now showing items 101-200 of 1481" to check if we are on the last page
    now_showing_text = pagination_info_elem.text
    total_items = now_showing_text.split(" of ")[1]
    total_items = int(total_items)
    last_item_on_page = now_showing_text.split("-")[1].split(" ")[0]
    last_item_on_page = int(last_item_on_page)
    this_page_final = last_item_on_page == total_items

    # Parse exams
    exams: list[Exam] = []
    for exam_elem in soup.find_all("div", class_="ds-artifact-item"):
        course_code = exam_elem.find("span", class_="coursecode").text
        title = exam_elem.find("h4").text

        # Skip exams with no PDF available
        if exam_elem.find("span", class_="pdf-unavailable"):
            continue

        download_url = exam_elem.find("span", class_="pdf-download").find("a")["href"]
        exams.append(Exam(title, course_code, download_url))

    return this_page_final, exams
