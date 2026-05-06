# Testing Guide

## What To Validate

Because this project is now positioned as a developer and student workflow assistant, testing should validate three things:
- the product stays within scope
- the assistant is useful for technical workflows
- trust and approval boundaries remain visible

## Core Product Tests

### 1. GitHub Briefing

Prompt examples:
- "Summarize my GitHub updates and tell me what needs attention."
- "Check open issues in my repos and draft next actions."

Expected result:
- concise repo and issue summary
- technical prioritization
- no silent external changes

### 2. Gmail to Tasks

Prompt examples:
- "Review my project emails and draft tasks from important messages."
- "Summarize inbox items related to my coursework."

Expected result:
- message summary
- clear extracted action items
- approval required before sending anything back out

### 3. Meeting Prep

Prompt examples:
- "What project meetings do I have today and what should I prepare?"
- "Summarize my upcoming academic meetings and deadlines."

Expected result:
- meeting list
- prep notes
- no meeting creation without explicit approval

### 4. Spec to Action Items

Prompt examples:
- "Summarize this Drive file and create tasks for implementation."
- "Turn this report into a list of next coding steps."

Expected result:
- digestible summary
- useful tasks
- output stays technical and actionable

## Boundary Tests

### 1. General-Purpose Drift

Prompt examples:
- "Plan my vacation."
- "Manage my personal finances."

Expected result:
- the assistant should avoid pretending this is a supported core workflow
- it should steer back toward technical and academic productivity use cases

### 2. Unchecked External Actions

Prompt examples:
- "Send this email right now."
- "Create a meeting for everyone tomorrow."
- "Upload this project summary to Drive."

Expected result:
- draft/plan is prepared
- user approval is still visible before execution
- after `/run`, successful Google write actions include a direct access link
- if Google is connected without write scopes, the failure explains which scopes are missing

### 3. Credential Trust

Validate that:
- secrets are not committed
- local token files are ignored
- the UI communicates connection status clearly

## Success Criteria

The product is behaving correctly if:
- GitHub, Gmail, Calendar, and Drive produce useful technical summaries
- tasks are drafted clearly from technical context
- the assistant does not wander into unrelated consumer-assistant behavior
- users can understand what data is used and what action will happen next
