# Agentic AI

Agentic AI is a trusted workflow assistant for technical users, focused on developers and students building software projects.

The product direction is intentionally narrow:
- It helps users summarize, prioritize, draft actions, and coordinate work across developer workflows.
- It does not act as an unrestricted autonomous operator over personal accounts.
- It is designed to be approval-first for risky actions and transparent about what data it accesses.

## Core Audience

- Student developers working on assignments, hackathons, and portfolio projects
- Solo developers managing code, docs, issues, and communication
- Small technical teams that want one place to review updates and draft next actions

## Product Boundary

The product is domain-specific to technical workflows. It should focus on:
- GitHub updates, PRs, issues, and repo summaries
- Gmail and Calendar briefings for project communication
- Drive and docs summarization for specs, notes, and reports
- Task drafting from technical context
- Research assistance for developer and student workflows

The product should avoid becoming:
- A general assistant for every personal life task
- A background bot with unrestricted write access
- A system that stores or asks for raw credentials beyond secure OAuth flows

## Autonomy Model

Autonomy is allowed inside a strict boundary:
- The assistant may automatically gather context, summarize it, and draft actions
- The assistant may prepare updates, tasks, follow-ups, and suggested schedules
- The assistant should require user approval before sending, scheduling, deleting, or changing external records unless the user has explicitly enabled a trusted automation

In short: autonomous analysis and drafting, controlled execution.

## Integration Direction

Priority integrations for the product direction:
1. GitHub
2. Gmail
3. Google Calendar
4. Google Drive / Docs
5. Slack or Discord
6. Notion or Linear
7. Jira for a later team/enterprise path

## Chat Surfaces

Yes, this assistant can be controlled through chat apps instead of a separate mobile app.

Recommended first mobile-friendly surface:
- Telegram bot

Why Telegram fits this project:
- fast to prototype
- works well with command-driven workflows
- supports files and voice later
- sits cleanly on top of the existing planning and approval model

Current backend support includes a Telegram webhook adapter that can:
- generate plans from plain messages or `/plan`
- show pending plan state with `/status`
- require execution approval via `/run`
- clear pending work with `/cancel`
- create approved Calendar events, local tasks, recurring schedules, and Drive text files
- return direct links for Google Calendar and Drive actions when authorization/scopes are available

## Monetization

Recommended business model:
- Free tier for local experimentation and limited integrations
- Pro subscription for premium models, deeper history, automations, and richer summaries
- Team plan for shared project context, admin controls, and workspace-level integrations

## Trust Principles

- Use OAuth instead of asking users for account passwords
- Request the minimum scopes needed
- Keep the user informed about what will run and why
- Make approval explicit before external side effects
- Let users disconnect integrations and delete their data

See [WORKFLOW_GUIDE.md](c:\Users\shekh\Desktop\All Agents\agentic-ai\WORKFLOW_GUIDE.md), [SETUP_GUIDE.md](c:\Users\shekh\Desktop\All Agents\agentic-ai\SETUP_GUIDE.md), and [TESTING_GUIDE.md](c:\Users\shekh\Desktop\All Agents\agentic-ai\TESTING_GUIDE.md) for the operating model behind this direction.
