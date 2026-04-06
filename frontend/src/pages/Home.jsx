import { useEffect, useMemo, useState } from "react";
import {
  approvePlan,
  cancelPlan,
  createTask,
  deleteSchedule,
  deleteTask,
  fetchEmails,
  fetchMeetings,
  generatePlan,
  getDashboardState,
  getDriveFiles,
  getGoogleAuthUrl,
  getPreferences,
  getGoogleStatus,
  getGithubRepos,
  getSchedules,
  getTasks,
  resetDashboardState,
  updatePreferences,
  updateScheduleStatus,
  updateTaskStatus,
} from "../api/api";

const navItems = [
  { key: "Dashboard", label: "Dashboard", short: "DB", description: "Plan, approve, and review workflows." },
  { key: "Gmail", label: "Gmail", short: "GM", description: "Inbox activity and message summaries." },
  { key: "Calendar", label: "Calendar", short: "CL", description: "Upcoming meetings and scheduling state." },
  { key: "GitHub", label: "GitHub", short: "GH", description: "Repository activity, issues, and analysis." },
  { key: "Tasks", label: "Tasks", short: "TK", description: "Action items created from agent outputs." },
  { key: "Schedules", label: "Schedules", short: "SC", description: "Recurring automations and delivery timing." },
  { key: "Drive", label: "Drive", short: "DR", description: "Files and summarization-ready documents." },
];

const dashboardHighlights = [
  { key: "summary", title: "Summary", description: "Primary execution outcome" },
  { key: "weather", title: "Weather", description: "Forecast and current conditions" },
  { key: "research", title: "Research", description: "Web findings and references" },
  { key: "tasks", title: "Tasks", description: "Created action items" },
  { key: "schedules", title: "Schedules", description: "Recurring deliveries and automation status" },
  { key: "github_updates", title: "GitHub", description: "Repository changes and issues" },
  { key: "sent_email", title: "Delivery", description: "Outbound summary email state" },
];

const formatCount = (value) => `${value ?? 0}`.padStart(2, "0");
const itemMatchesSearch = (item, term) => !term.trim() || JSON.stringify(item).toLowerCase().includes(term.toLowerCase());
const getPanelMeta = (activeNav) => navItems.find((item) => item.key === activeNav) ?? navItems[0];
const themeLabel = (theme) => (theme === "dark" ? "Dark" : "Light");

function formatDisplayDate(value) {
  if (!value) return "No date";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function cleanMultilineText(value) {
  return (value || "").replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function getInitialTheme() {
  const storedTheme = window.localStorage.getItem("aid-theme");
  if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function normalizePanelItems(activeNav, records) {
  if (activeNav === "Gmail") {
    return records.map((email) => {
      const body = cleanMultilineText(email.body || email.preview || "No message content available.");
      const preview = cleanMultilineText(email.preview || body).slice(0, 220);
      return {
        id: email.id,
        badge: email.read ? "Read" : "Unread",
        title: email.subject || "(No subject)",
        subtitle: email.from || "Unknown sender",
        description: preview || "No preview available.",
        meta: formatDisplayDate(email.date),
        tone: email.read ? "neutral" : "attention",
        roleLabel: "Message",
        href: email.url || "",
        hrefLabel: email.url ? "Open in Gmail" : "",
        detailTitle: email.subject || "(No subject)",
        detailSummary: email.from || "Unknown sender",
        detailBody: body,
        detailSections: [
          { label: "Sender", value: email.from || "Unknown sender" },
          { label: "Date", value: formatDisplayDate(email.date) },
          { label: "Status", value: email.read ? "Read" : "Unread" },
        ],
      };
    });
  }

  if (activeNav === "Calendar") {
    return records.map((meeting) => ({
      id: meeting.id,
      badge: `${meeting.duration_minutes || 0} min`,
      title: meeting.title || "Untitled meeting",
      subtitle: formatDisplayDate(meeting.date),
      description: meeting.description || "No meeting details provided.",
      meta: meeting.location || "No location",
      tone: "info",
      roleLabel: "Meeting",
      href: meeting.url || "",
      hrefLabel: meeting.url ? "Open calendar item" : "",
      detailTitle: meeting.title || "Untitled meeting",
      detailSummary: meeting.location || "No location",
      detailBody: cleanMultilineText(meeting.description || "No meeting details provided."),
      detailSections: [
        { label: "Start", value: formatDisplayDate(meeting.date) },
        { label: "End", value: formatDisplayDate(meeting.end_date || "") || "Not available" },
        { label: "Attendees", value: (meeting.attendees || []).join(", ") || "No attendees listed" },
        { label: "Location", value: meeting.location || "No location" },
      ],
    }));
  }

  if (activeNav === "GitHub") {
    return records.map((repo) => ({
      id: repo.id,
      badge: `${repo.open_issues || 0} issues`,
      title: repo.full_name || repo.name || "Repository",
      subtitle: repo.language || "Unknown stack",
      description: repo.description || "No repository description.",
      meta: formatDisplayDate(repo.updated_at),
      tone: "info",
      roleLabel: "Repository",
      href: repo.url || "",
      hrefLabel: repo.url ? "Open repository" : "",
      detailTitle: repo.full_name || repo.name || "Repository",
      detailSummary: repo.description || "No repository description.",
      detailBody: cleanMultilineText(`Language: ${repo.language || "Unknown"}\nStars: ${repo.stars || 0}\nForks: ${repo.forks || 0}\nOpen issues: ${repo.open_issues || 0}`),
      detailSections: [
        { label: "Updated", value: formatDisplayDate(repo.updated_at) },
        { label: "Topics", value: (repo.topics || []).join(", ") || "No topics listed" },
        { label: "Language", value: repo.language || "Unknown" },
      ],
    }));
  }

  if (activeNav === "Tasks") {
    return records.map((task) => ({
      id: task.id,
      badge: task.priority || "medium",
      title: task.title || "Untitled task",
      subtitle: task.status || "pending",
      description: task.description || "No task description.",
      meta: formatDisplayDate(task.created_at),
      tone: task.priority === "high" ? "attention" : task.priority === "low" ? "success" : "warning",
      roleLabel: "Task",
      href: "",
      hrefLabel: "",
      detailTitle: task.title || "Untitled task",
      detailSummary: `${task.priority || "medium"} priority`,
      detailBody: cleanMultilineText(task.description || "No task description."),
      detailSections: [
        { label: "Status", value: task.status || "pending" },
        { label: "Source", value: task.source || "manual" },
        { label: "Created", value: formatDisplayDate(task.created_at) },
        { label: "Due", value: formatDisplayDate(task.due_date) },
      ],
    }));
  }

  if (activeNav === "Schedules") {
    return records.map((schedule) => ({
      id: schedule.id,
      badge: schedule.active ? "Active" : "Paused",
      title: schedule.name || "Recurring schedule",
      subtitle: `${schedule.time_local || "18:00"} · ${schedule.timezone || "Asia/Calcutta"}`,
      description: `${schedule.city || "Preferred location"} -> ${schedule.recipient_email || "No recipient"}`,
      meta: formatDisplayDate(schedule.next_run_at),
      tone: schedule.active ? "success" : "neutral",
      roleLabel: "Schedule",
      href: "",
      hrefLabel: "",
      detailTitle: schedule.name || "Recurring schedule",
      detailSummary: `${schedule.recurrence || "daily"} weather delivery`,
      detailBody: cleanMultilineText(
        `City: ${schedule.city || "Preferred location"}\nRecipient: ${schedule.recipient_email || "Not set"}\nNext run: ${formatDisplayDate(schedule.next_run_at)}\nLast run: ${formatDisplayDate(schedule.last_run_at)}\nLast status: ${schedule.last_status || "scheduled"}${schedule.last_error ? `\nLast error: ${schedule.last_error}` : ""}`,
      ),
      detailSections: [
        { label: "Status", value: schedule.active ? "Active" : "Paused" },
        { label: "Time", value: `${schedule.time_local || "18:00"} ${schedule.timezone || "Asia/Calcutta"}` },
        { label: "Recipient", value: schedule.recipient_email || "Not set" },
        { label: "Next run", value: formatDisplayDate(schedule.next_run_at) },
      ],
    }));
  }

  if (activeNav === "Drive") {
    return records.map((file) => ({
      id: file.id,
      badge: file.type || "file",
      title: file.name || "Unnamed file",
      subtitle: formatDisplayDate(file.modified),
      description: file.mimeType || file.type || "No file metadata.",
      meta: file.size_kb ? `${file.size_kb} KB` : "Size unavailable",
      tone: "neutral",
      roleLabel: "Document",
      href: file.url || "",
      hrefLabel: file.url ? "Open file" : "",
      detailTitle: file.name || "Unnamed file",
      detailSummary: file.type || "File",
      detailBody: cleanMultilineText(`Type: ${file.type || "Unknown"}\nMime type: ${file.mimeType || "Not available"}\nSize: ${file.size_kb ? `${file.size_kb} KB` : "Unavailable"}`),
      detailSections: [
        { label: "Modified", value: formatDisplayDate(file.modified) },
        { label: "Source", value: file.source || "Unknown" },
      ],
    }));
  }

  return records;
}

function Header({ searchTerm, onSearchChange, onConnectGoogle, onRefreshActive, onToggleTheme, theme, googleStatus, activeNav, busy }) {
  const connected = googleStatus?.authorized;
  return (
    <header className="top-bar">
      <div className="brand-cluster">
        <div className="brand-logo" aria-hidden="true"><span>AID</span></div>
        <div>
          <div className="top-brand">AI Digital Assistant</div>
          <div className="top-subtitle">Multi-tool planning, approvals, and execution in one workspace</div>
        </div>
      </div>
      <div className="header-actions">
        <label className="search-shell" htmlFor="global-search">
          <span className="search-label">Search</span>
          <input id="global-search" className="top-search" value={searchTerm} onChange={(event) => onSearchChange(event.target.value)} placeholder={`Filter ${activeNav.toLowerCase()} content`} />
        </label>
        <button className="secondary-button" type="button" onClick={onToggleTheme}>{themeLabel(theme)} theme</button>
        <button className="secondary-button" type="button" onClick={onRefreshActive} disabled={busy}>Refresh {activeNav}</button>
        <button className="approve-button" type="button" onClick={onConnectGoogle} disabled={busy}>{connected ? "Google Connected" : "Connect Google"}</button>
      </div>
    </header>
  );
}

function Sidebar({ activeNav, onSelectNav, onReset, dashboard, googleStatus }) {
  const summaryCount = dashboard?.plan_steps?.length ?? 0;
  const taskCount = dashboard?.artifacts?.tasks?.length ?? 0;
  const emailCount = dashboard?.artifacts?.emails?.length ?? 0;
  const googleState = googleStatus?.authorized ? "Online" : "Pending";
  return (
    <aside className="left-rail">
      <div className="rail-brand-card">
        <div className="rail-badge">AID</div>
        <div>
          <div className="brand-title">Control Center</div>
          <div className="brand-subtitle">Theme-aware workspace with expandable records and live actions.</div>
        </div>
      </div>
      <div className="rail-summary-grid">
        <div className="mini-stat-card"><span className="metric-label">Plan Steps</span><span className="metric-value">{formatCount(summaryCount)}</span></div>
        <div className="mini-stat-card"><span className="metric-label">Tasks</span><span className="metric-value">{formatCount(taskCount)}</span></div>
        <div className="mini-stat-card"><span className="metric-label">Inbox</span><span className="metric-value">{formatCount(emailCount)}</span></div>
        <div className="mini-stat-card"><span className="metric-label">Google</span><span className="metric-value metric-value-small">{googleState}</span></div>
      </div>
      <nav className="nav-list">
        {navItems.map((item) => (
          <button key={item.key} className={`nav-item ${activeNav === item.key ? "is-active" : ""}`} type="button" onClick={() => onSelectNav(item.key)}>
            <span className="nav-icon">{item.short}</span>
            <span className="nav-copy">
              <span className="nav-title">{item.label}</span>
              <span className="nav-description">{item.description}</span>
            </span>
          </button>
        ))}
      </nav>
      <button className="primary-rail-button" type="button" onClick={onReset}>Reset workspace</button>
    </aside>
  );
}

function OverviewStrip({ dashboard, googleStatus }) {
  const artifacts = dashboard.artifacts ?? {};
  const cards = [
    { title: "Execution State", value: dashboard.approval_label || "Idle", detail: dashboard.current_step || "Ready", tone: "info" },
    { title: "Google Access", value: googleStatus?.authorized ? "Connected" : "Pending", detail: googleStatus?.active_redirect_uri || "Redirect not configured", tone: googleStatus?.authorized ? "success" : "warning" },
    { title: "Tasks Drafted", value: `${artifacts.tasks?.length ?? 0}`, detail: `${artifacts.emails?.length ?? 0} emails cached`, tone: "attention" },
    { title: "Token Usage", value: `${dashboard.token_usage?.used?.toLocaleString?.() ?? 0}`, detail: `of ${dashboard.token_usage?.limit?.toLocaleString?.() ?? 0}`, tone: "neutral" },
  ];
  return <section className="overview-strip">{cards.map((card) => <article key={card.title} className={`overview-card tone-${card.tone}`}><div className="overview-title">{card.title}</div><div className="overview-value">{card.value}</div><div className="overview-detail">{card.detail}</div></article>)}</section>;
}

function Composer({ value, onChange, onSubmit, onClear, busy }) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="panel-header"><div><div className="eyebrow">Prompt Studio</div><h2>Describe the workflow you want</h2></div></div>
      <label className="composer-label" htmlFor="prompt-input">The planner will generate the exact tool sequence before anything runs.</label>
      <textarea id="prompt-input" className="composer-input" rows={5} value={value} onChange={(event) => onChange(event.target.value)} placeholder="Try: Check my emails, summarize the urgent ones, and create tasks. Or: Search the web for AI coding tools and email me the summary." />
      <div className="composer-actions">
        <button className="approve-button" type="submit" disabled={busy || !value.trim()}>Generate Plan</button>
        <button className="secondary-button" type="button" onClick={onClear} disabled={busy}>Clear Dashboard</button>
      </div>
    </form>
  );
}

function PlanCard({ dashboard, busy, onApprove, onCancel, onEdit }) {
  const steps = dashboard.plan_steps ?? [];
  return (
    <section className="panel-card">
      <div className="panel-header">
        <div><div className="eyebrow">Planner</div><h2>Execution plan</h2><div className="section-subtitle">Each step is ordered for the selected workflow.</div></div>
        <span className="status-pill">{dashboard.approval_label}</span>
      </div>
      <div className="plan-list">
        {steps.length ? steps.map((step, index) => (
          <article key={step.id} className={`plan-step is-${step.status}`}>
            <div className="step-index">{index + 1}</div><div className={`step-dot is-${step.status}`} />
            <div><div className="step-title">{step.title}</div><div className="step-description">{step.description}</div><div className="step-meta">{step.tool}</div></div>
          </article>
        )) : <div className="artifact-empty">Generate a plan to review which agents and tools will run.</div>}
      </div>
      <div className="planner-actions">
        <button className="approve-button" type="button" onClick={onApprove} disabled={busy || !steps.length}>Run Plan</button>
        <button className="secondary-button" type="button" onClick={onEdit} disabled={busy}>Reuse Prompt</button>
        <button className="text-button" type="button" onClick={onCancel} disabled={busy || !steps.length}>Cancel</button>
      </div>
    </section>
  );
}

function ResponseCard({ dashboard }) {
  return <section className="panel-card"><div className="panel-header"><div><div className="eyebrow">Response</div><h2>Agent response</h2></div></div><div className="response-copy">{dashboard.response || "Execution results will appear here after the plan runs."}</div></section>;
}

function ArtifactCard({ title, description, content, tone = "neutral" }) {
  return <article className={`artifact-card tone-${tone}`}><div className="artifact-card-head"><div className="section-title">{title}</div><div className="artifact-card-subtitle">{description}</div></div><div className="artifact-card-body">{content}</div></article>;
}

function ArtifactsGrid({ artifacts }) {
  const weather = artifacts.weather ?? {};
  const research = artifacts.research ?? {};
  const githubUpdates = artifacts.github_updates ?? {};
  const sentEmail = artifacts.sent_email ?? {};
  const tasks = artifacts.tasks ?? [];
  const schedules = artifacts.schedules ?? [];
  return (
    <section className="artifact-grid">
      <ArtifactCard title="Summary" description="Primary execution output" tone="warning" content={<p className="artifact-copy">{artifacts.summary || "No summary yet."}</p>} />
      <ArtifactCard title="Weather" description="Current conditions" tone="info" content={weather.city ? <div className="artifact-stack"><div className="metric-value">{weather.city}</div><div className="artifact-copy">{weather.temperature_c} C, {weather.condition}</div><div className="artifact-copy">Wind {weather.wind_speed_kmh ?? "--"} km/h</div></div> : <div className="artifact-empty">Weather results appear here when used.</div>} />
      <ArtifactCard title="Research" description="Web findings" tone="neutral" content={<p className="artifact-copy">{research.summary || "Web research results appear here when used."}</p>} />
      <ArtifactCard title="Tasks" description="Created action items" tone="success" content={<div className="artifact-list">{tasks.length ? tasks.map((task) => <div key={task.id} className="artifact-row compact-row"><div><div className="step-title">{task.title}</div><div className="step-description">{task.description || "No details provided."}</div></div><span className={`priority-tag is-${task.priority}`}>{task.priority}</span></div>) : <div className="artifact-empty">No tasks created yet.</div>}</div>} />
      <ArtifactCard title="Schedules" description="Recurring automations" tone="success" content={<div className="artifact-list">{schedules.length ? schedules.map((schedule) => <div key={schedule.id} className="artifact-row compact-row"><div><div className="step-title">{schedule.name}</div><div className="step-description">{schedule.time_local} {schedule.timezone} {"->"} {schedule.recipient_email}</div></div><span className={`priority-tag is-${schedule.active ? "low" : "medium"}`}>{schedule.active ? "active" : "paused"}</span></div>) : <div className="artifact-empty">No recurring jobs created in this session.</div>}</div>} />
      <ArtifactCard title="GitHub Updates" description="Repo issues and PR activity" tone="info" content={<p className="artifact-copy">{githubUpdates.summary || "GitHub activity appears here when used."}</p>} />
      <ArtifactCard title="Email Delivery" description="Outbound result" tone="attention" content={sentEmail.to ? <div className="artifact-stack"><div className="metric-value">Sent</div><div className="artifact-copy">{sentEmail.subject} to {sentEmail.to}</div></div> : <div className="artifact-empty">Outbound Gmail actions appear here when used.</div>} />
    </section>
  );
}

function LogsCard({ logs }) {
  return <section className="panel-card"><div className="panel-header"><div><div className="eyebrow">Execution Log</div><h2>Workflow trace</h2></div></div><div className="log-list">{logs?.length ? logs.map((log) => <div key={`${log.timestamp}-${log.message}`} className="log-line"><span className="log-stamp">{log.timestamp}</span><span>{log.message}</span></div>) : <div className="artifact-empty">Execution logs appear here after a plan runs.</div>}</div></section>;
}

function InsightsPanel({ dashboard }) {
  const artifacts = dashboard.artifacts ?? {};
  const cards = dashboardHighlights.map((item) => {
    if (item.key === "tasks") return { ...item, value: `${artifacts.tasks?.length ?? 0} ready`, tone: "success" };
    if (item.key === "schedules") return { ...item, value: `${artifacts.schedules?.length ?? 0} active`, tone: "success" };
    if (item.key === "summary") return { ...item, value: artifacts.summary ? "Available" : "Waiting", tone: "warning" };
    if (item.key === "weather") return { ...item, value: artifacts.weather?.city || "Inactive", tone: "info" };
    if (item.key === "research") return { ...item, value: artifacts.research?.query || "Inactive", tone: "neutral" };
    if (item.key === "github_updates") return { ...item, value: artifacts.github_updates?.repos?.length ? "Loaded" : "Inactive", tone: "info" };
    return { ...item, value: artifacts.sent_email?.to || "Inactive", tone: "attention" };
  });
  return <section className="panel-card"><div className="panel-header"><div><div className="eyebrow">Artifacts</div><h2>Operational highlights</h2></div></div><div className="insight-grid">{cards.map((card) => <article key={card.key} className={`insight-card tone-${card.tone}`}><div className="insight-title">{card.title}</div><div className="insight-value">{card.value}</div><div className="insight-description">{card.description}</div></article>)}</div></section>;
}

function TaskQuickCreate({ form, onChange, onSubmit, busy }) {
  return (
    <form className="task-quick-form" onSubmit={onSubmit}>
      <div className="section-title">Quick create</div>
      <input className="top-search" value={form.title} onChange={(event) => onChange("title", event.target.value)} placeholder="Task title" />
      <textarea className="composer-input task-form-textarea" value={form.description} onChange={(event) => onChange("description", event.target.value)} placeholder="Description" rows={3} />
      <div className="task-form-row">
        <input className="top-search" value={form.due_date} onChange={(event) => onChange("due_date", event.target.value)} placeholder="Due date or ISO datetime" />
        <select className="top-search task-select" value={form.priority} onChange={(event) => onChange("priority", event.target.value)}>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="low">low</option>
        </select>
      </div>
      <button className="approve-button" type="submit" disabled={busy || !form.title.trim()}>Create task</button>
    </form>
  );
}

function PreferenceForm({ preferencesForm, onPreferencesChange, onPreferencesSave, preferencesBusy }) {
  return (
    <form className="task-quick-form" onSubmit={onPreferencesSave}>
      <div className="section-title">Default weather location</div>
      <input className="top-search" value={preferencesForm.weather_location} onChange={(event) => onPreferencesChange(event.target.value)} placeholder="Dharwad, Karnataka, India" />
      <button className="approve-button" type="submit" disabled={preferencesBusy || !preferencesForm.weather_location.trim()}>Save location</button>
    </form>
  );
}

function DetailPane({
  item,
  meta,
  taskForm,
  onTaskFormChange,
  onTaskCreate,
  onTaskStatusChange,
  onTaskDelete,
  onScheduleStatusChange,
  onScheduleDelete,
  taskBusy,
  preferencesForm,
  onPreferencesChange,
  onPreferencesSave,
  preferencesBusy,
}) {
  if (!item) {
    return (
      <section className="detail-pane">
        <div className="artifact-empty">Select a {meta.label.toLowerCase()} item to inspect it in detail.</div>
        {meta.key === "Tasks" ? <TaskQuickCreate form={taskForm} onChange={onTaskFormChange} onSubmit={onTaskCreate} busy={taskBusy} /> : null}
        {meta.key === "Schedules" ? <PreferenceForm preferencesForm={preferencesForm} onPreferencesChange={onPreferencesChange} onPreferencesSave={onPreferencesSave} preferencesBusy={preferencesBusy} /> : null}
      </section>
    );
  }
  return (
    <section className="detail-pane">
      <div className="detail-pane-head">
        <div><div className="eyebrow">{item.roleLabel}</div><h3>{item.detailTitle}</h3><div className="detail-subtitle">{item.detailSummary}</div></div>
        {item.href ? <a className="approve-button detail-link" href={item.href} target="_blank" rel="noreferrer">{item.hrefLabel || "Open source"}</a> : null}
      </div>
      <div className="detail-grid">
        {(item.detailSections || []).map((section) => <div key={section.label} className="detail-chip"><span className="metric-label">{section.label}</span><span className="detail-chip-value">{section.value}</span></div>)}
      </div>
      <div className="detail-content"><div className="section-title">Full details</div><div className="detail-body">{item.detailBody}</div></div>
      {meta.key === "Tasks" ? (
        <div className="detail-actions">
          <div className="task-action-row">
            <button className="secondary-button" type="button" onClick={() => onTaskStatusChange(item.id, "pending")} disabled={taskBusy}>Mark pending</button>
            <button className="secondary-button" type="button" onClick={() => onTaskStatusChange(item.id, "in_progress")} disabled={taskBusy}>In progress</button>
            <button className="secondary-button" type="button" onClick={() => onTaskStatusChange(item.id, "done")} disabled={taskBusy}>Done</button>
          </div>
          <button className="text-button danger-link" type="button" onClick={() => onTaskDelete(item.id)} disabled={taskBusy}>Delete task</button>
          <TaskQuickCreate form={taskForm} onChange={onTaskFormChange} onSubmit={onTaskCreate} busy={taskBusy} />
        </div>
      ) : null}
      {meta.key === "Schedules" ? (
        <div className="detail-actions">
          <div className="task-action-row">
            <button className="secondary-button" type="button" onClick={() => onScheduleStatusChange(item.id, true)} disabled={taskBusy}>Resume</button>
            <button className="secondary-button" type="button" onClick={() => onScheduleStatusChange(item.id, false)} disabled={taskBusy}>Pause</button>
          </div>
          <button className="text-button danger-link" type="button" onClick={() => onScheduleDelete(item.id)} disabled={taskBusy}>Delete schedule</button>
          <PreferenceForm preferencesForm={preferencesForm} onPreferencesChange={onPreferencesChange} onPreferencesSave={onPreferencesSave} preferencesBusy={preferencesBusy} />
        </div>
      ) : null}
    </section>
  );
}

function DataPanel({
  activeNav,
  items,
  selectedItemId,
  onSelectItem,
  loading,
  searchTerm,
  onReload,
  taskForm,
  onTaskFormChange,
  onTaskCreate,
  onTaskStatusChange,
  onTaskDelete,
  onScheduleStatusChange,
  onScheduleDelete,
  taskBusy,
  preferencesForm,
  onPreferencesChange,
  onPreferencesSave,
  preferencesBusy,
}) {
  const meta = getPanelMeta(activeNav);
  const filteredItems = items.filter((item) => itemMatchesSearch(item, searchTerm));
  const selectedItem = filteredItems.find((item) => item.id === selectedItemId) || filteredItems[0] || null;
  return (
    <section className="panel-card panel-card-large">
      <div className="panel-header">
        <div><div className="eyebrow">{meta.label}</div><h2>{meta.description}</h2><div className="section-subtitle">Select any {meta.label.toLowerCase()} card to expand it. Source links appear when the backend provides a URL.</div></div>
        <button className="secondary-button" type="button" onClick={onReload}>Refresh data</button>
      </div>
      {loading ? <div className="artifact-empty">Loading {meta.label.toLowerCase()} data...</div> : null}
      {!loading && !filteredItems.length ? <div className="artifact-empty">No {meta.label.toLowerCase()} records matched the current filter.</div> : null}
      {!loading && filteredItems.length ? (
        <div className="data-view-shell">
          <div className="data-card-grid">
            {filteredItems.map((item) => (
              <button key={item.id ?? item.title} type="button" className={`data-card tone-${item.tone || "neutral"} ${selectedItem?.id === item.id ? "is-selected" : ""}`} onClick={() => onSelectItem(item.id)}>
                <div className="data-card-top"><span className={`data-badge tone-${item.tone || "neutral"}`}>{item.badge || meta.short}</span><span className="data-meta">{item.meta || ""}</span></div>
                <div className="data-title">{item.title}</div>
                <div className="data-subtitle">{item.subtitle}</div>
                <p className="artifact-copy">{item.description}</p>
                <span className="link-button detail-trigger">View full details</span>
              </button>
            ))}
          </div>
          <DetailPane
            item={selectedItem}
            meta={meta}
            taskForm={taskForm}
            onTaskFormChange={onTaskFormChange}
            onTaskCreate={onTaskCreate}
            onTaskStatusChange={onTaskStatusChange}
            onTaskDelete={onTaskDelete}
            onScheduleStatusChange={onScheduleStatusChange}
            onScheduleDelete={onScheduleDelete}
            taskBusy={taskBusy}
            preferencesForm={preferencesForm}
            onPreferencesChange={onPreferencesChange}
            onPreferencesSave={onPreferencesSave}
            preferencesBusy={preferencesBusy}
          />
        </div>
      ) : null}
    </section>
  );
}

function RightRail({ dashboard, googleStatus, activeNav, onConnectGoogle, theme }) {
  const statusLabel = googleStatus?.authorized ? "Connected" : "Pending";
  const responseLength = dashboard.response?.length ?? 0;
  return (
    <aside className="right-rail">
      <div className="rail-section"><div className="section-title">Brand</div><div className="brand-poster"><div className="poster-logo">AID</div><div><div className="poster-title">AI Digital Assistant</div><div className="artifact-copy">Theme mode: {themeLabel(theme)}. Expandable records are active across data panels.</div></div></div></div>
      <div className="rail-section"><div className="section-title">Integrations</div><div className="metric-card"><div className="metric-label">Google status</div><div className="metric-value">{statusLabel}</div><div className="artifact-copy compact-copy">Redirect: {googleStatus?.active_redirect_uri || "Not configured"}</div><button className="link-button" type="button" onClick={onConnectGoogle}>Manage Google access</button></div></div>
      <div className="rail-section"><div className="section-title">Session</div><div className="metric-card"><div className="metric-label">Current step</div><div className="metric-value">{dashboard.current_step}</div></div><div className="metric-card"><div className="metric-label">Intent accuracy</div><div className="metric-value">{dashboard.intent_accuracy}%</div></div><div className="metric-card"><div className="metric-label">Visible area</div><div className="metric-value">{activeNav}</div><div className="artifact-copy compact-copy">{responseLength} response characters captured</div></div></div>
    </aside>
  );
}

export default function Home() {
  const [activeNav, setActiveNav] = useState("Dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [googleStatus, setGoogleStatus] = useState(null);
  const [message, setMessage] = useState("What's the weather today?");
  const [searchTerm, setSearchTerm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sectionItems, setSectionItems] = useState([]);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [theme, setTheme] = useState(getInitialTheme);
  const [taskBusy, setTaskBusy] = useState(false);
  const [preferencesBusy, setPreferencesBusy] = useState(false);
  const [preferencesForm, setPreferencesForm] = useState({ weather_location: "" });
  const [taskForm, setTaskForm] = useState({
    title: "",
    description: "",
    priority: "medium",
    due_date: "",
  });

  async function refreshState() {
    const state = await getDashboardState();
    setDashboard(state);
    return state;
  }

  async function refreshGoogleStatus() {
    const status = await getGoogleStatus();
    setGoogleStatus(status);
    return status;
  }

  async function refreshPreferences() {
    const preferences = await getPreferences();
    setPreferencesForm({ weather_location: preferences.weather_location || "" });
    return preferences;
  }

  async function loadNavData(navKey, options = {}) {
    const { refresh = false } = options;
    if (navKey === "Dashboard") {
      await refreshState();
      return;
    }
    setSectionLoading(true);
    try {
      let records = [];
      if (navKey === "Gmail") records = await fetchEmails({ refresh, limit: 8 });
      else if (navKey === "Calendar") records = await fetchMeetings(6);
      else if (navKey === "GitHub") records = await getGithubRepos("", 6);
      else if (navKey === "Tasks") records = await getTasks();
      else if (navKey === "Schedules") records = await getSchedules();
      else if (navKey === "Drive") records = await getDriveFiles(6);
      const normalized = normalizePanelItems(navKey, records);
      setSectionItems(normalized);
      setSelectedItemId(normalized[0]?.id || "");
      if (navKey === "Schedules") await refreshPreferences();
      setError("");
    } catch (loadError) {
      setSectionItems([]);
      setSelectedItemId("");
      setError(loadError.message);
    } finally {
      setSectionLoading(false);
    }
  }

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("aid-theme", theme);
  }, [theme]);

  useEffect(() => {
    void (async () => {
      try {
        await refreshState();
        await refreshGoogleStatus();
        await refreshPreferences();
      } catch (loadError) {
        setError(loadError.message);
      }
    })();
  }, []);

  useEffect(() => {
    void loadNavData(activeNav);
  }, [activeNav]);

  useEffect(() => {
    function handleOAuthMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === "google-oauth-success") void refreshGoogleStatus();
      if (event.data?.type === "google-oauth-error") setError(event.data.message || "Google authorization failed.");
    }
    window.addEventListener("message", handleOAuthMessage);
    return () => window.removeEventListener("message", handleOAuthMessage);
  }, []);

  const navSummary = useMemo(() => {
    const artifacts = dashboard?.artifacts ?? {};
    return {
      Dashboard: dashboard?.plan_steps?.length ?? 0,
      Gmail: artifacts.emails?.length ?? 0,
      Calendar: artifacts.meetings?.length ?? 0,
      GitHub: artifacts.repos?.length ?? 0,
      Tasks: artifacts.tasks?.length ?? 0,
      Schedules: activeNav === "Schedules" ? sectionItems.length : artifacts.schedules?.length ?? 0,
      Drive: sectionItems.length,
    };
  }, [dashboard, sectionItems]);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const nextState = await generatePlan(message);
      setDashboard(nextState);
      setActiveNav("Dashboard");
      setError("");
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleApprove() {
    if (!dashboard) return;
    setBusy(true);
    try {
      const nextState = await approvePlan(dashboard.session_id);
      setDashboard(nextState);
      setError("");
    } catch (approveError) {
      setError(approveError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!dashboard) return;
    setBusy(true);
    try {
      const nextState = await cancelPlan(dashboard.session_id);
      setDashboard(nextState);
      setError("");
    } catch (cancelError) {
      setError(cancelError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    try {
      const freshState = await resetDashboardState();
      setDashboard(freshState);
      setMessage("");
      setSearchTerm("");
      setError("");
      setSectionItems([]);
      setSelectedItemId("");
      setTaskForm({ title: "", description: "", priority: "medium", due_date: "" });
      setPreferencesForm({ weather_location: "" });
      setActiveNav("Dashboard");
      await refreshGoogleStatus();
      await refreshPreferences();
    } catch (loadError) {
      setError(loadError.message);
    }
  }

  async function handleConnectGoogle() {
    try {
      const auth = await getGoogleAuthUrl();
      window.open(auth.auth_url, "google-oauth", "popup,width=520,height=720");
    } catch (connectError) {
      setError(connectError.message);
    }
  }

  async function handleRefreshActive() {
    await loadNavData(activeNav, { refresh: activeNav === "Gmail" });
    if (activeNav === "Dashboard") await refreshGoogleStatus();
  }

  function handleToggleTheme() {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  function handleTaskFormChange(field, value) {
    setTaskForm((current) => ({ ...current, [field]: value }));
  }

  function handlePreferencesChange(value) {
    setPreferencesForm({ weather_location: value });
  }

  async function handleTaskCreate(event) {
    event.preventDefault();
    setTaskBusy(true);
    try {
      await createTask(taskForm);
      setTaskForm({ title: "", description: "", priority: "medium", due_date: "" });
      await loadNavData("Tasks");
      setActiveNav("Tasks");
      setError("");
    } catch (taskError) {
      setError(taskError.message);
    } finally {
      setTaskBusy(false);
    }
  }

  async function handleTaskStatusChange(taskId, status) {
    setTaskBusy(true);
    try {
      await updateTaskStatus(taskId, status);
      await loadNavData("Tasks");
      setSelectedItemId(taskId);
      setError("");
    } catch (taskError) {
      setError(taskError.message);
    } finally {
      setTaskBusy(false);
    }
  }

  async function handleTaskDelete(taskId) {
    setTaskBusy(true);
    try {
      await deleteTask(taskId);
      await loadNavData("Tasks");
      setError("");
    } catch (taskError) {
      setError(taskError.message);
    } finally {
      setTaskBusy(false);
    }
  }

  async function handleScheduleStatusChange(scheduleId, active) {
    setTaskBusy(true);
    try {
      await updateScheduleStatus(scheduleId, active);
      await loadNavData("Schedules");
      setSelectedItemId(scheduleId);
      setError("");
    } catch (scheduleError) {
      setError(scheduleError.message);
    } finally {
      setTaskBusy(false);
    }
  }

  async function handleScheduleDelete(scheduleId) {
    setTaskBusy(true);
    try {
      await deleteSchedule(scheduleId);
      await loadNavData("Schedules");
      setError("");
    } catch (scheduleError) {
      setError(scheduleError.message);
    } finally {
      setTaskBusy(false);
    }
  }

  async function handlePreferencesSave(event) {
    event.preventDefault();
    setPreferencesBusy(true);
    try {
      await updatePreferences(preferencesForm);
      await refreshPreferences();
      if (activeNav === "Schedules") await loadNavData("Schedules");
      setError("");
    } catch (preferencesError) {
      setError(preferencesError.message);
    } finally {
      setPreferencesBusy(false);
    }
  }

  if (!dashboard) return <div className="loading-shell">Loading AI Digital Assistant...</div>;

  return (
    <div className="app-shell">
      <div className="page-accent accent-one" />
      <div className="page-accent accent-two" />
      <Header searchTerm={searchTerm} onSearchChange={setSearchTerm} onConnectGoogle={handleConnectGoogle} onRefreshActive={handleRefreshActive} onToggleTheme={handleToggleTheme} theme={theme} googleStatus={googleStatus} activeNav={activeNav} busy={busy} />
      <Sidebar activeNav={activeNav} onSelectNav={setActiveNav} onReset={handleReset} dashboard={dashboard} googleStatus={googleStatus} />
      <main className="main-column">
        <OverviewStrip dashboard={dashboard} googleStatus={googleStatus ?? {}} />
        {error ? <div className="error-banner">{error}</div> : null}
        {activeNav === "Dashboard" ? (
          <>
            <Composer value={message} onChange={setMessage} onSubmit={handleSubmit} onClear={handleReset} busy={busy} />
            <InsightsPanel dashboard={dashboard} />
            <PlanCard dashboard={dashboard} busy={busy} onApprove={handleApprove} onCancel={handleCancel} onEdit={() => setMessage(dashboard.prompt_preview || message)} />
            <ResponseCard dashboard={dashboard} />
            <ArtifactsGrid artifacts={dashboard.artifacts ?? {}} />
            <LogsCard logs={dashboard.logs ?? []} />
          </>
        ) : (
          <DataPanel
            activeNav={activeNav}
            items={sectionItems}
            selectedItemId={selectedItemId}
            onSelectItem={setSelectedItemId}
            loading={sectionLoading}
            searchTerm={searchTerm}
            onReload={handleRefreshActive}
            taskForm={taskForm}
            onTaskFormChange={handleTaskFormChange}
            onTaskCreate={handleTaskCreate}
            onTaskStatusChange={handleTaskStatusChange}
            onTaskDelete={handleTaskDelete}
            onScheduleStatusChange={handleScheduleStatusChange}
            onScheduleDelete={handleScheduleDelete}
            taskBusy={taskBusy}
            preferencesForm={preferencesForm}
            onPreferencesChange={handlePreferencesChange}
            onPreferencesSave={handlePreferencesSave}
            preferencesBusy={preferencesBusy}
          />
        )}
      </main>
      <RightRail dashboard={dashboard} googleStatus={googleStatus ?? {}} activeNav={`${activeNav} (${formatCount(navSummary[activeNav])})`} onConnectGoogle={handleConnectGoogle} theme={theme} />
    </div>
  );
}
