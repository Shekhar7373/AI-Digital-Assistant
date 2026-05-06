"""
GitHub Service.

Uses the public GitHub REST API (no auth required for public repos).
For private repos or higher rate limits, set GITHUB_TOKEN in .env.
"""

import os
import httpx
from agent.prompt import GITHUB_ANALYSIS_SYSTEM

GITHUB_API   = "https://api.github.com"


def _token() -> str:
    return os.getenv("GITHUB_TOKEN", "")

# Default headers — add auth if token is available
def _headers():
    h = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AgenticAssistant/1.0"}
    token = _token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def fetch_repos(username: str, limit: int = 6) -> list[dict]:
    """
    Fetch public repositories for a GitHub username.
    Returns simplified repo dicts.
    """
    per_page = max(1, min(limit or 6, 8))
    async with httpx.AsyncClient(timeout=10) as client:
        if username:
            resp = await client.get(
                f"{GITHUB_API}/users/{username}/repos",
                headers=_headers(),
                params={"sort": "updated", "per_page": per_page},
            )
            resp.raise_for_status()
            repos = resp.json()
        elif _token():
            resp = await client.get(
                f"{GITHUB_API}/user/repos",
                headers=_headers(),
                params={"sort": "updated", "per_page": per_page, "affiliation": "owner,collaborator,organization_member"},
            )
            resp.raise_for_status()
            repos = resp.json()
        else:
            return []

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "full_name": r["full_name"],
            "description": r.get("description") or "",
            "language": r.get("language") or "Unknown",
            "stars": r["stargazers_count"],
            "forks": r["forks_count"],
            "open_issues": r["open_issues_count"],
            "url": r["html_url"],
            "updated_at": r["updated_at"],
            "topics": r.get("topics", []),
        }
        for r in repos
    ]


async def analyze_repo(repo: dict) -> dict:
    """
    Analyze a single repository dict using the LLM.
    Returns analysis text.
    """
    if not repo:
        return {"analysis": "No repository data provided."}

    repo_text = (
        f"Repository: {repo.get('full_name', repo.get('name', '?'))}\n"
        f"Description: {repo.get('description', 'N/A')}\n"
        f"Language: {repo.get('language', 'Unknown')}\n"
        f"Stars: {repo.get('stars', 0)} | Forks: {repo.get('forks', 0)}\n"
        f"Open Issues: {repo.get('open_issues', 0)}\n"
        f"Topics: {', '.join(repo.get('topics', []))}\n"
        f"Last Updated: {repo.get('updated_at', 'Unknown')}"
    )

    try:
        from llm.router import llm_chat

        analysis = await llm_chat(GITHUB_ANALYSIS_SYSTEM, repo_text)
    except Exception as error:
        print(f"[GitHubService] LLM analysis failed: {error}")
        analysis = (
            f"{repo.get('name', 'Repository')} is primarily {repo.get('language', 'Unknown')} "
            f"with {repo.get('stars', 0)} stars and {repo.get('open_issues', 0)} open issues."
        )
    return {"repo": repo.get("name"), "analysis": analysis}


async def fetch_github_updates(username: str, limit: int = 5) -> dict:
    """
    Fetch recent repository updates plus issue and pull request counts.
    """
    repo_limit = max(1, min(limit or 5, 8))
    repos = await fetch_repos(username, limit=repo_limit)
    if not repos:
        return {"summary": "No repositories found.", "repos": []}

    async with httpx.AsyncClient(timeout=12) as client:
        enriched = []
        for repo in repos[:repo_limit]:
            full_name = repo.get("full_name", "")
            if not full_name:
                enriched.append(
                    {
                        **repo,
                        "open_pull_requests": 0,
                        "issues_preview": [],
                        "pull_requests_preview": [],
                    }
                )
                continue

            issues_response = await client.get(
                f"{GITHUB_API}/repos/{full_name}/issues",
                headers=_headers(),
                params={"state": "open", "per_page": 6},
            )
            pulls_response = await client.get(
                f"{GITHUB_API}/repos/{full_name}/pulls",
                headers=_headers(),
                params={"state": "open", "per_page": 6},
            )

            issues = issues_response.json() if issues_response.status_code < 400 else []
            pulls = pulls_response.json() if pulls_response.status_code < 400 else []

            issue_items = [item for item in issues if "pull_request" not in item]
            enriched.append(
                {
                    **repo,
                    "open_pull_requests": len(pulls),
                    "issues_preview": [
                        {
                            "title": item.get("title", ""),
                            "url": item.get("html_url", ""),
                            "number": item.get("number"),
                        }
                        for item in issue_items[:3]
                    ],
                    "pull_requests_preview": [
                        {
                            "title": item.get("title", ""),
                            "url": item.get("html_url", ""),
                            "number": item.get("number"),
                        }
                        for item in pulls[:3]
                    ],
                }
            )

    highlights = []
    for repo in enriched:
        highlights.append(
            f"{repo['full_name']}: {repo.get('open_issues', 0)} open issues, "
            f"{repo.get('open_pull_requests', 0)} open PRs"
        )

    return {
        "summary": "Recent GitHub updates: " + "; ".join(highlights[:3]),
        "repos": enriched,
    }
