"""
Tool Router — maps LLM-identified intent strings to actual service function calls.

This is the "manual function calling" layer that compensates for local LLMs
that don't natively support tool/function calling.

Features:
- Automatic data passing between tool results and next tool inputs
- Context sharing through params dictionary
- Error handling and result aggregation
"""

from services.email_service import fetch_emails, process_emails, summarize_emails
from services.task_service import create_task_from_context, get_all_tasks
from services.weather_service import get_weather
from services.github_service import fetch_repos, analyze_repo, fetch_github_updates
from services.calendar_service import fetch_meetings, schedule_meeting_mock
from services.drive_service import create_drive_text_file, list_files, summarize_file_mock
from services.notification_service import send_summary_email
from services.schedule_service import create_recurring_weather_email_schedule
from services.web_research_service import research_web
from services.wikipedia_service import search_wikipedia

DEFAULT_WEATHER_LOCATION = "SDMCET, Dharwad, Karnataka, India"


# Maps tool name → async callable
TOOL_REGISTRY: dict = {
    "fetch_emails":       lambda params: fetch_emails(),
    "summarize_emails":   lambda params: summarize_emails(params.get("emails", [])),
    "create_task":        lambda params: create_task_from_context(params),
    "get_tasks":          lambda params: get_all_tasks(),
    "fetch_weather":      lambda params: get_weather(params.get("city", DEFAULT_WEATHER_LOCATION)),
    "fetch_github_repos": lambda params: fetch_repos(params.get("username", "")),
    "fetch_github_updates": lambda params: fetch_github_updates(params.get("username", "")),
    "analyze_github":     lambda params: analyze_repo(params.get("repo", {})),
    "fetch_meetings":     lambda params: fetch_meetings(),
    "schedule_meeting":   lambda params: schedule_meeting_mock(params),
    "list_drive_files":   lambda params: list_files(),
    "summarize_file":     lambda params: summarize_file_mock(params.get("file_id", "")),
    "create_drive_doc":   lambda params: create_drive_text_file(params),
    "web_research":       lambda params: research_web(params.get("query", "")),
    "send_email":         lambda params: send_summary_email(
        params.get("recipient_email", ""),
        params.get("email_subject", "Agentic AI Summary"),
        params.get("email_body", ""),
        params.get("email_context"),
    ),
    "create_recurring_weather_email_schedule": lambda params: create_recurring_weather_email_schedule(params),
    "wikipedia_search":   lambda params: search_wikipedia(params.get("query", "")),
}


async def execute_tools(tool_names: list[str], params: dict = None) -> dict:
    """
    Execute a list of tools in sequence order.
    Each tool's output is automatically made available to subsequent tools.
    
    Auto-wiring rules:
    - fetch_emails output → emails param for summarize_emails
    - summarize_emails output → summaries param for create_task
    - fetch_github_repos output → repo param for analyze_github
    - list_drive_files output → file_id param for summarize_file
    - fetch_weather output → weather param for compose_response
    
    Returns a dict mapping tool_name → result.
    """
    params = params or {}
    results = {}
    
    for tool_name in tool_names:
        if tool_name == "general_chat":
            # Handled separately in the agent
            continue

        handler = TOOL_REGISTRY.get(tool_name)
        if not handler:
            results[tool_name] = {"error": f"Unknown tool: {tool_name}"}
            continue

        try:
            # Make previous tool results available for context
            params["_previous_results"] = results
            
            # Execute the tool
            result = await handler(params)
            results[tool_name] = result
            
            # Auto-wire common data dependencies for next tools
            # ─────────────────────────────────────────────────
            
            # Email pipeline: fetch → summarize → create_task
            if tool_name == "fetch_emails" and isinstance(result, list):
                params["emails"] = result
                print(f"[ToolRouter] Auto-wired {len(result)} emails for next tool")
            
            if tool_name == "process_emails" and isinstance(result, list):
                params["processed_emails"] = result
                print(f"[ToolRouter] Auto-wired {len(result)} processed emails for next tool")
            
            if tool_name == "summarize_emails" and isinstance(result, dict):
                params["summaries"] = result.get("summaries", [])
                params["summary_text"] = result.get("summary", "")
                print(f"[ToolRouter] Auto-wired {len(params['summaries'])} summaries for next tool")
            
            # GitHub pipeline: fetch_repos → analyze_github
            if tool_name == "fetch_github_repos" and isinstance(result, list) and result:
                # Pass first repo for analysis, or all for bulk analysis
                params["repos"] = result
                if result:
                    params["repo"] = result[0]  # Default to first repo
                print(f"[ToolRouter] Auto-wired {len(result)} repos for next tool")

            if tool_name == "fetch_github_updates" and isinstance(result, dict):
                repos = result.get("repos", [])
                params["github_updates"] = result
                params["repos"] = repos
                if repos:
                    params["repo"] = repos[0]
                print(f"[ToolRouter] Auto-wired {len(repos)} GitHub updates for next tool")
            
            # Drive pipeline: list_drive_files → summarize_file
            if tool_name == "list_drive_files" and isinstance(result, list) and result:
                params["files"] = result
                if result:
                    params["file_id"] = result[0].get("id", "")  # Default to first file
                print(f"[ToolRouter] Auto-wired {len(result)} files for next tool")
            
            # Weather: fetch_weather result available for response composition
            if tool_name == "fetch_weather" and isinstance(result, dict):
                params["weather"] = result
                print(f"[ToolRouter] Cached weather result for response composition")

            if tool_name == "web_research" and isinstance(result, dict):
                params["research"] = result
                params["email_body"] = result.get("summary", "")
                params["email_context"] = result
                if result.get("query") and not params.get("email_subject"):
                    params["email_subject"] = f"Research summary: {result['query']}"
                print("[ToolRouter] Cached web research result for response composition")
                
            # Tasks: get_tasks result available for display
            if tool_name == "get_tasks" and isinstance(result, list):
                params["all_tasks"] = result
                print(f"[ToolRouter] Cached {len(result)} tasks for response composition")
                
        except Exception as e:
            error_msg = str(e)
            results[tool_name] = {"error": error_msg}
            print(f"[ToolRouter] Error executing {tool_name}: {error_msg}")

    return results
