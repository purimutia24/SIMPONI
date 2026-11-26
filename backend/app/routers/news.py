import hashlib
import html
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import struct_time
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException, Query, Request as FastAPIRequest
from fastapi.responses import FileResponse

router = APIRouter(prefix="/news", tags=["Berita"])
NEWS_IMAGE_DIR = Path(__file__).resolve().parents[3] / "fe" / "src" / "assets" / "images"
NEWS_LOCAL_IMAGES = (
    "jabar1.png",
    "jabar2.png",
    "jabar3.png",
    "jabar4.png",
    "jabar1.1.png",
    "jabar1.2.png",
    "jabar1.3.png",
    "jabar5.jpg",
    "jabar6.jpg",
    "seminar.jpeg",
    "pernikahan-dini.jpeg",
)

NEWS_QUERIES = (
    '"pernikahan dini" "Jawa Barat"',
    '"perkawinan anak" "Jawa Barat"',
    '"dispensasi kawin" "Jawa Barat"',
)
CHILD_MARRIAGE_TERMS = (
    "pernikahan dini",
    "perkawinan dini",
    "pernikahan anak",
    "perkawinan anak",
    "pernikahan di bawah umur",
    "perkawinan di bawah umur",
    "pernikahan bawah umur",
    "perkawinan bawah umur",
    "dispensasi kawin",
    "dispensasi nikah",
    "child marriage",
)
WEST_JAVA_LOCATIONS = (
    "jawa barat",
    "jabar",
    "bandung barat",
    "kabupaten bandung",
    "kota bandung",
    "kabupaten bogor",
    "kota bogor",
    "kabupaten bekasi",
    "kota bekasi",
    "kabupaten sukabumi",
    "kota sukabumi",
    "kabupaten cirebon",
    "kota cirebon",
    "kabupaten tasikmalaya",
    "kota tasikmalaya",
    "kabupaten garut",
    "kabupaten ciamis",
    "kota banjar",
    "kabupaten kuningan",
    "kabupaten sumedang",
    "kabupaten indramayu",
    "kabupaten subang",
    "kabupaten purwakarta",
    "kabupaten karawang",
    "kabupaten cianjur",
    "kabupaten majalengka",
    "kabupaten pangandaran",
    "kota cimahi",
    "kota depok",
    "kota banjar",
    "garut",
    "ciamis",
    "kuningan",
    "sumedang",
    "indramayu",
    "subang",
    "purwakarta",
    "karawang",
    "cianjur",
    "majalengka",
    "pangandaran",
    "cimahi",
    "depok",
    "bogor",
    "bekasi",
    "sukabumi",
    "cirebon",
    "tasikmalaya",
    "bandung",
    "banjar",
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
        tag_name = _local_name(child.tag)
        if tag_name in {
            "content",
            "thumbnail",
            "enclosure",
            "media_content",
            "media_thumbnail",
        }:
            image_url = (
                child.attrib.get("url", "")
                or child.attrib.get("href", "")
                or child.attrib.get("src", "")
            )
            media_type = child.attrib.get("type", "")
            if image_url and (media_type.startswith("image/") or tag_name != "enclosure"):
                return image_url

        if tag_name == "link":
            relation = child.attrib.get("rel", "").lower().split()
            media_type = child.attrib.get("type", "").lower()
            image_url = child.attrib.get("href", "") or child.attrib.get("url", "")
            if image_url and (
                "image" in relation
                or ("enclosure" in relation and media_type.startswith("image/"))
            ):
                return image_url

        if tag_name == "img":
            image_url = child.attrib.get("src", "") or child.attrib.get("data-src", "")
            if image_url:
                return html.unescape(image_url)

    for name in ("description", "summary", "content", "encoded"):
        description = _find_child(element, name)
        if description is None:
            continue
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
        if not title or not link:
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


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
        for phrase in phrases
    )


def _is_relevant_article(article: dict[str, object]) -> bool:
    searchable_text = " ".join(
        str(article.get(field, ""))
        for field in ("title", "description", "source")
    ).casefold()
    if not (
        _contains_phrase(searchable_text, CHILD_MARRIAGE_TERMS)
        and _contains_phrase(searchable_text, WEST_JAVA_LOCATIONS)
    ):
        return False

    localities = tuple(
        location for location in WEST_JAVA_LOCATIONS if location not in {"jawa barat", "jabar"}
    )
    is_national_province_roundup = (
        _contains_phrase(searchable_text, ("provinsi",))
        and _contains_phrase(searchable_text, ("indonesia",))
        and not _contains_phrase(searchable_text, localities)
    )
    return not is_national_province_roundup


def _fetch_feed(query: str) -> list[dict[str, object]]:
    request = Request(
        GOOGLE_NEWS_RSS_URL.format(query=quote(query)),
        headers={"Accept": "application/rss+xml, application/xml", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return _parse_feed(response.read())


@router.get("/images/{image_name}", name="serve_news_local_image")
def serve_news_local_image(image_name: str) -> FileResponse:
    if image_name not in NEWS_LOCAL_IMAGES:
        raise HTTPException(status_code=404, detail="Gambar berita tidak ditemukan")
    image_path = NEWS_IMAGE_DIR / image_name
    if not image_path.is_file():
        raise HTTPException(status_code=503, detail="Gambar berita tidak tersedia di server")
    media_type, _ = mimetypes.guess_type(image_path.name)
    return FileResponse(image_path, media_type=media_type)


@router.get("", response_model=list[dict[str, object]])
def get_news(
    request: FastAPIRequest,
    limit: int = Query(default=9, ge=1, le=9),
) -> list[dict[str, object]]:
    articles: list[dict[str, object]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(NEWS_QUERIES)) as executor:
        futures = {
            executor.submit(_fetch_feed, query): query for query in NEWS_QUERIES
        }
        for future in as_completed(futures):
            try:
                articles.extend(future.result())
            except (
                HTTPError,
                URLError,
                TimeoutError,
                OSError,
                ElementTree.ParseError,
                ValueError,
            ) as exc:
                errors.append(f"{futures[future]}: {exc}")

    if not articles and errors:
        raise HTTPException(status_code=502, detail="Feed berita tidak dapat diakses")

    deduplicated: dict[str, dict[str, object]] = {}
    for article in articles:
        if not _is_relevant_article(article):
            continue
        deduplicated.setdefault(str(article["link"]), article)
    sorted_articles = sorted(
        deduplicated.values(),
        key=lambda article: article["_published"],
        reverse=True,
    )
    results = []
    used_local_images: set[str] = set()
    for article in sorted_articles[:limit]:
        result = {key: value for key, value in article.items() if not key.startswith("_")}
        if not result["image"]:
            start_index = int.from_bytes(
                hashlib.sha256(str(article["link"]).encode("utf-8")).digest()[:4],
                "big",
            ) % len(NEWS_LOCAL_IMAGES)
            for offset in range(len(NEWS_LOCAL_IMAGES)):
                image_name = NEWS_LOCAL_IMAGES[(start_index + offset) % len(NEWS_LOCAL_IMAGES)]
                if image_name not in used_local_images:
                    used_local_images.add(image_name)
                    result["image"] = str(
                        request.url_for("serve_news_local_image", image_name=image_name)
                    )
                    break
        results.append(result)
    return results
