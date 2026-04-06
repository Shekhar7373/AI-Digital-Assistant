import httpx

async def search_wikipedia(query: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_")
        )
        if resp.status_code == 404:
            return {"error": f"No Wikipedia article found for '{query}'"}
        data = resp.json()
    return {"title": data.get("title"), "summary": data.get("extract"), "url": data.get("content_urls", {}).get("desktop", {}).get("page")}