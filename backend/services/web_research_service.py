"""
Web research service.

Uses DuckDuckGo's instant answer API first, then falls back to Wikipedia.
This keeps web-style lookups lightweight and API-key free.
"""

from __future__ import annotations

import re

import httpx


DUCKDUCKGO_API = "https://api.duckduckgo.com/"
WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/api.php"
REQUEST_HEADERS = {
    "User-Agent": "AgenticAI/1.0 (+http://localhost:5173)",
    "Accept": "application/json",
}


def _clean_query(query: str) -> str:
    cleaned = query.strip()
    cleaned = re.sub(r"^[\"'\s]+|[\"'\s]+$", "", cleaned)
    cleaned = re.sub(r"\b(send|mail|email)\b.*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(make|write)\s+(a\s+)?summary\b.*$", "", cleaned, flags=re.IGNORECASE).strip()

    for prefix in [
        "search web",
        "search the web",
        "search",
        "research",
        "look up",
        "find information about",
        "tell me about",
    ]:
        pattern = rf"^{prefix}\s+"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    quoted = re.findall(r'"([^"]+)"', query)
    if quoted:
        cleaned = quoted[0].strip()

    return cleaned.strip(" ?.,")


async def research_web(query: str) -> dict:
    normalized_query = _clean_query(query)
    if not normalized_query:
        return {"error": "A search query is required."}

    ddg_data = {}
    async with httpx.AsyncClient(timeout=12, headers=REQUEST_HEADERS, follow_redirects=True) as client:
        try:
            ddg_response = await client.get(
                DUCKDUCKGO_API,
                params={
                    "q": normalized_query,
                    "format": "json",
                    "no_html": 1,
                    "no_redirect": 1,
                    "skip_disambig": 1,
                },
            )
            ddg_response.raise_for_status()
            ddg_data = ddg_response.json()
        except Exception:
            ddg_data = {}

        abstract = (ddg_data.get("AbstractText") or "").strip()
        heading = (ddg_data.get("Heading") or normalized_query).strip()
        abstract_url = ddg_data.get("AbstractURL", "")

        related = []
        for item in ddg_data.get("RelatedTopics", []):
            if isinstance(item, dict) and item.get("Text"):
                related.append(
                    {
                        "title": item.get("Text", "").split(" - ")[0].strip() or heading,
                        "summary": item.get("Text", "").strip(),
                        "url": item.get("FirstURL", ""),
                        "source": "duckduckgo",
                    }
                )
            elif isinstance(item, dict):
                for nested in item.get("Topics", []):
                    if nested.get("Text"):
                        related.append(
                            {
                                "title": nested.get("Text", "").split(" - ")[0].strip() or heading,
                                "summary": nested.get("Text", "").strip(),
                                "url": nested.get("FirstURL", ""),
                                "source": "duckduckgo",
                            }
                        )

        if abstract:
            items = [
                {
                    "title": heading or normalized_query,
                    "summary": abstract,
                    "url": abstract_url,
                    "source": "duckduckgo",
                }
            ]
            items.extend(related[:4])
            return {
                "query": normalized_query,
                "summary": abstract,
                "items": items[:5],
                "source": "duckduckgo",
            }

        wiki_response = await client.get(
            WIKIPEDIA_SEARCH_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": normalized_query,
                "utf8": 1,
                "format": "json",
                "origin": "*",
            },
        )
        wiki_response.raise_for_status()
        wiki_data = wiki_response.json()
        matches = wiki_data.get("query", {}).get("search", [])

    if not matches:
        return {"error": f"No web results found for '{normalized_query}'."}

    items = []
    for match in matches[:5]:
        title = match.get("title", "Untitled")
        snippet = (
            match.get("snippet", "")
            .replace("<span class=\"searchmatch\">", "")
            .replace("</span>", "")
        )
        items.append(
            {
                "title": title,
                "summary": snippet,
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "source": "wikipedia",
            }
        )

    return {
        "query": normalized_query,
        "summary": items[0]["summary"],
        "items": items,
        "source": "wikipedia",
    }
