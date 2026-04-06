const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    if (isJson) {
      const errorBody = await response.json();
      throw new Error(errorBody.detail || errorBody.message || "Request failed");
    }
    const errorText = await response.text();
    throw new Error(errorText || "Request failed");
  }

  return isJson ? response.json() : response.text();
}

export function getDashboardState() {
  return request("/dashboard/state");
}

export function resetDashboardState() {
  return request("/dashboard/reset", {
    method: "POST",
  });
}

export function generatePlan(message) {
  return request("/dashboard/plan", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function approvePlan(sessionId) {
  return request("/dashboard/approve", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function cancelPlan(sessionId) {
  return request("/dashboard/cancel", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function getGoogleStatus() {
  return request("/integrations/google/status");
}

export function getGoogleAuthUrl(redirectUri) {
  const search = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : "";
  return request(`/integrations/google/auth-url${search}`);
}

export function exchangeGoogleCode(code, state, redirectUri) {
  return request("/integrations/google/exchange-code", {
    method: "POST",
    body: JSON.stringify({
      code,
      state,
      redirect_uri: redirectUri,
    }),
  });
}

export function fetchEmails({ refresh = false, limit = 8 } = {}) {
  return request(`/email/fetch?refresh=${refresh}&limit=${limit}`, {
    method: "POST",
  });
}

export function fetchMeetings(limit = 6) {
  return request(`/calendar/meetings?limit=${limit}`);
}

export function getTasks() {
  return request("/tasks");
}

export function getSchedules() {
  return request("/schedules");
}

export function updateScheduleStatus(scheduleId, active) {
  return request(`/schedules/${scheduleId}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  });
}

export function deleteSchedule(scheduleId) {
  return request(`/schedules/${scheduleId}`, {
    method: "DELETE",
  });
}

export function getPreferences() {
  return request("/preferences");
}

export function updatePreferences(payload) {
  return request("/preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function createTask(payload) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTaskStatus(taskId, status) {
  return request(`/tasks/${taskId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function deleteTask(taskId) {
  return request(`/tasks/${taskId}`, {
    method: "DELETE",
  });
}

export function getDriveFiles(limit = 6) {
  return request(`/drive/files?limit=${limit}`);
}

export function getGithubRepos(username = "", limit = 6) {
  const params = new URLSearchParams();
  if (username) params.set("username", username);
  params.set("limit", String(limit));
  const search = params.toString() ? `?${params.toString()}` : "";
  return request(`/github/repos${search}`);
}
