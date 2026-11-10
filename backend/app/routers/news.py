import html
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/news", tags=["Berita"])

NEWS_QUERIES = (
    "pernikahan dini Indonesia",
    "perkawinan anak Indonesia",
    "dispensasi kawin Indonesia",
)
TOPIC_KEYWORDS = (
    "pernikahan dini",
    "perkawinan anak",
    "pernikahan anak",
    "dispensasi kawin",
    "dispensasi nikah",
)
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
REQUEST_TIMEOUT = float(os.getenv("NEWS_REQUEST_TIMEOUT", "8"))
USER_AGENT = "SIMPONI/2.0 (+https://news.google.com/)"
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return WHITESPACE_RE.sub(" ", " ".join(element.itertext())).strip()


def _strip_html(value: str) -> str:
    return WHITESPACE_RE.sub(" ", html.unescape(HTML_TAG_RE.sub(" ", value))).strip()


def _normalise_url(value: str) -> str:
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _parse_published(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if isinstance(value, struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _find_child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    return next((child for child in element if _local_name(child.tag) == name), None)


def _find_image(element: ElementTree.Element) -> str:
    for child in element.iter():
        if _local_name(child.tag) in {
            "content",
            "thumbnail",
            "enclosure",
            "media_content",
            "media_thumbnail",
        }:
            image_url = child.attrib.get("url", "") or child.attrib.get("href", "")
            media_type = child.attrib.get("type", "")
            if image_url and (media_type.startswith("image/") or _local_name(child.tag) != "enclosure"):
                return image_url

    description = _find_child(element, "description")
    if description is not None:
        raw_description = "".join(description.itertext())
        match = re.search(r'<img[^>]+src=["\']([^"\']+)', raw_description, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return ""


def _parse_feed(payload: bytes) -> list[dict[str, object]]:
    root = ElementTree.fromstring(payload)
    articles: list[dict[str, object]] = []
    for item in root.iter():
        if _local_name(item.tag) not in {"item", "entry"}:
            continue
        title = _text(_find_child(item, "title"))
        link_element = _find_child(item, "link")
        link = _text(link_element)
        if not link and link_element is not None:
            link = link_element.attrib.get("href", "")
        link = _normalise_url(link)
        description = _strip_html(_text(_find_child(item, "description")) or _text(_find_child(item, "summary")))
        searchable = f"{title} {description}".casefold()
        if not title or not link or not any(keyword in searchable for keyword in TOPIC_KEYWORDS):
            continue
        date_values = (
            _text(_find_child(item, "published")),
            _text(_find_child(item, "updated")),
            _text(_find_child(item, "published_parsed")),
            _text(_find_child(item, "updated_parsed")),
            _text(_find_child(item, "pubDate")),
        )
        published = next((_parse_published(value) for value in date_values if value), None)
        published = published or datetime.now(timezone.utc)
        source = _text(_find_child(item, "source"))
        if not source and " - " in title:
            title, source = title.rsplit(" - ", 1)
        articles.append(
            {
                "title": title.strip(),
                "link": link,
                "source": source.strip(),
                "description": description,
                "published_at": published.isoformat() if published else None,
                "image": _find_image(item),
                "_published": published or datetime.min.replace(tzinfo=timezone.utc),
            }
        )
    return articles


def _fetch_feed(query: str) -> list[dict[str, object]]:
    request = Request(
        GOOGLE_NEWS_RSS_URL.format(query=quote(query)),
        headers={"Accept": "application/rss+xml, application/xml", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return _parse_feed(response.read())


@router.get("", response_model=list[dict[str, object]])
def get_news(limit: int = Query(default=6, ge=1, le=50)) -> list[dict[str, object]]:
    articles: list[dict[str, object]] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            articles.extend(_fetch_feed(query))
        except (HTTPError, URLError, TimeoutError, OSError, ElementTree.ParseError, ValueError) as exc:
            errors.append(f"{query}: {exc}")

    if not articles and errors:
        raise HTTPException(status_code=502, detail="Feed berita tidak dapat diakses")

    deduplicated: dict[str, dict[str, object]] = {}
    for article in articles:
        deduplicated.setdefault(str(article["link"]), article)
    sorted_articles = sorted(
        deduplicated.values(),
        key=lambda article: article["_published"],
        reverse=True,
    )
    return [
        {key: value for key, value in article.items() if not key.startswith("_")}
        for article in sorted_articles[:limit]
    ]
