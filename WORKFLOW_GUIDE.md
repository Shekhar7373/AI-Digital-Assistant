# Workflow Guide

## Product Definition

Agentic AI is a workflow copilot for developers and students. Its job is to turn fragmented technical context into clear next actions.

The intended user outcome is:
- know what changed
- know what matters
- know what to do next

## End Users

- Computer science students managing coursework, project notes, GitHub repos, and deadlines
- Developers tracking repository activity, inbox requests, meetings, and follow-ups
- Small technical teams that want concise execution briefs rather than another chat toy

## Domain Boundary

This project is domain-specific, not general-purpose.

In scope:
- software project work
- academic project work
- technical communication
- repo, document, task, and meeting coordination

Out of scope:
- finance and banking workflows
- healthcare or legal decision support
- unrestricted browser automation
- silent destructive account actions
- broad personal-life assistant behavior

## Autonomy Boundary

The project should be autonomous in preparation, not autonomous in unchecked execution.

Allowed autonomous behavior:
- fetch updates across connected tools
- summarize messages, repos, files, and meetings
- prioritize work and draft tasks
- draft emails, standup notes, issue summaries, and meeting prep
- recommend the next workflow step

Approval-gated behavior:
- send emails
- create calendar events
- update third-party records
- trigger recurring automations
- any destructive or side-effectful external action

This is the key rule:
autonomous context gathering and drafting, explicit approval for external action.

## Core Workflows

### 1. Project Briefing

Inputs:
- GitHub notifications, issues, PRs
- Gmail threads
- Calendar meetings

Outputs:
- daily or on-demand project brief
- top blockers
- next tasks

### 2. Spec to Action Items

Inputs:
- Drive files or docs
- notes or pasted text

Outputs:
- concise summary
- extracted tasks
- follow-up questions

### 3. Student Assignment Copilot

Inputs:
- assignment brief
- repo activity
- schedule/deadline context

Outputs:
- breakdown of work
- milestones
- risks and missing pieces

### 4. Repo Health Review

Inputs:
- repos
- issues
- PR and release activity

Outputs:
- project status summary
- important changes
- recommended next actions

### 5. Chat-Controlled Assistant

Inputs:
- Telegram bot messages
- command-style workflow requests

Outputs:
- plan preview in chat
- explicit approval step via `/run`
- concise execution response back in chat

## Integration Priority

### Tier 1

- GitHub: PRs, issues, notifications, release monitoring
- Gmail: technical communication summaries and follow-up drafting
- Google Calendar: meeting briefings and prep
- Google Drive / Docs: summarize specs, notes, and reports into tasks
- Telegram: mobile-friendly control surface over the existing backend

### Tier 2

- Slack or Discord: team updates and action-item capture
- Notion or Linear: task and project sync

### Tier 3

- Jira: later enterprise path only

## Monetization Direction

- Free: local or limited-usage mode for students and solo builders
- Pro: premium models, recurring briefings, advanced summaries, richer automations
- Team: shared workspace context, team integrations, admin controls

## Trust Model

Users should trust this project because it is:
- transparent about every action
- approval-first for side effects
- minimal in the scopes it requests
- positioned as a workflow assistant, not as an account-taking agent

The product should never require blind trust. It should earn trust through visible control and clear boundaries.
