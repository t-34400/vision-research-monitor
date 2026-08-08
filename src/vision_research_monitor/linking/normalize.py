from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import NormalizedItem

ARXIV_ID_RE = re.compile(
    r"(?i)(?:arxiv:\s*|arxiv\.org/(?:abs|pdf)/)([a-z.-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?"
)
DOI_RE = re.compile(r"(?i)\b(10\.\d{4,9}/[-._;()/:a-z0-9]+)")
OPENREVIEW_RE = re.compile(r"(?i)openreview\.net/(?:forum|pdf)\?id=([^&#\s]+)")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(TITLE_TOKEN_RE.findall(ascii_text.casefold()))


def title_tokens(value: str) -> tuple[str, ...]:
    return tuple(normalize_text(value).split())


def normalize_author(value: str) -> str:
    return normalize_text(value)


def author_key(value: str) -> str | None:
    tokens = normalize_author(value).split()
    if not tokens:
        return None
    if len(tokens) == 1:
        return tokens[0]
    return f"{tokens[-1]}:{tokens[0][0]}"


def author_overlap(left: Iterable[str], right: Iterable[str]) -> float:
    left_keys = {key for author in left if (key := author_key(author))}
    right_keys = {key for author in right if (key := author_key(author))}
    if not left_keys or not right_keys:
        return 0.0
    return len(left_keys & right_keys) / min(len(left_keys), len(right_keys))


def canonicalize_url(
    value: str,
    *,
    tracking_query_prefixes: Iterable[str] = (),
    tracking_query_keys: Iterable[str] = (),
) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None

    host = parsed.hostname.casefold()
    if host.startswith("www."):
        host = host[4:]
    if parsed.port and not (
        (parsed.scheme == "http" and parsed.port == 80)
        or (parsed.scheme == "https" and parsed.port == 443)
    ):
        host = f"{host}:{parsed.port}"

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if host == "arxiv.org":
        match = re.match(
            r"/(?:abs|pdf)/([a-zA-Z.-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$", path
        )
        if match:
            return f"https://arxiv.org/abs/{match.group(1)}"
    if host == "openreview.net" and path in {"/forum", "/pdf"}:
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        note_id = params.get("id")
        if note_id:
            return f"https://openreview.net/forum?id={note_id}"

    if path != "/":
        path = path.rstrip("/")
    prefixes = tuple(prefix.casefold() for prefix in tracking_query_prefixes)
    blocked_keys = {key.casefold() for key in tracking_query_keys}
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in blocked_keys and not key.casefold().startswith(prefixes)
    ]
    query.sort()
    return urlunsplit(("https", host, path, urlencode(query), ""))


def github_repository_identifier(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner = parts[0].casefold()
    repository = parts[1].removesuffix(".git").casefold()
    if not owner or not repository:
        return None
    return f"github:{owner}/{repository}"


def arxiv_identifier(value: str) -> str | None:
    match = ARXIV_ID_RE.search(value)
    return f"arxiv:{match.group(1).casefold()}" if match else None


def openreview_identifier(value: str) -> str | None:
    match = OPENREVIEW_RE.search(value)
    return f"openreview:{match.group(1)}" if match else None


def doi_identifier(value: str) -> str | None:
    match = DOI_RE.search(value)
    if not match:
        return None
    doi = match.group(1).rstrip(".,;)").casefold()
    return f"doi:{doi}"


def extract_urls(value: str) -> list[str]:
    return [match.group(0).rstrip(".,;:!?)]") for match in URL_RE.finditer(value)]


def metadata_strings(item: NormalizedItem, allowed_keys: set[str]) -> list[str]:
    values: list[str] = []
    for key in allowed_keys:
        value = item.metadata.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
        elif isinstance(value, list):
            values.extend(
                str(entry).strip() for entry in value if isinstance(entry, str) and entry.strip()
            )
    return values


def exact_identifiers(item: NormalizedItem, config: dict) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    if item.source == "arxiv":
        identifiers[f"arxiv:{item.source_id.casefold()}"] = "source_id"
    elif item.source == "openreview":
        identifiers[f"openreview:{item.source_id}"] = "source_id"
    elif item.source == "github":
        repo_id = item.source_id.split(":", 1)[0]
        if repo_id.isdigit():
            identifiers[f"github-repository-id:{repo_id}"] = "source_id"

    texts = [item.url]
    texts.extend(metadata_strings(item, set(config["identifier"]["scan_metadata_keys"])))
    for text in texts:
        canonical = canonicalize_url(
            text,
            tracking_query_prefixes=config["url"]["tracking_query_prefixes"],
            tracking_query_keys=config["url"]["tracking_query_keys"],
        )
        if canonical:
            identifiers[f"url:{canonical}"] = "url"
        for url in extract_urls(text):
            canonical_embedded = canonicalize_url(
                url,
                tracking_query_prefixes=config["url"]["tracking_query_prefixes"],
                tracking_query_keys=config["url"]["tracking_query_keys"],
            )
            if canonical_embedded:
                identifiers[f"url:{canonical_embedded}"] = "embedded_url"
            for extractor, label in (
                (github_repository_identifier, "github_repository"),
                (arxiv_identifier, "arxiv"),
                (openreview_identifier, "openreview"),
                (doi_identifier, "doi"),
            ):
                identifier = extractor(url)
                if identifier:
                    identifiers[identifier] = label
        for extractor, label in (
            (arxiv_identifier, "arxiv"),
            (openreview_identifier, "openreview"),
            (doi_identifier, "doi"),
        ):
            identifier = extractor(text)
            if identifier:
                identifiers[identifier] = label

    doi = item.metadata.get("doi")
    if isinstance(doi, str) and doi.strip():
        identifier = doi_identifier(doi if doi.casefold().startswith("10.") else f"doi:{doi}")
        if identifier:
            identifiers[identifier] = "doi"
    return identifiers


def repository_name(item: NormalizedItem) -> str | None:
    if item.kind != "repository":
        return None
    if "/" in item.title:
        return item.title.rsplit("/", 1)[-1]
    identifier = github_repository_identifier(item.url)
    if identifier:
        return identifier.split("/", 1)[-1]
    return item.title
