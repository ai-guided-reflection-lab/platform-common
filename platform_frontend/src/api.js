export const SESSION_KEY = "my_rag_chatbot_user";
export function session() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}
export function logout() {
  localStorage.removeItem(SESSION_KEY);
  location.assign("/");
}
export async function api(path, options = {}) {
  const saved = session();
  const headers = {
    ...options.headers,
    Authorization: `Bearer ${saved?.access_token || ""}`,
  };
  let body = options.body;
  if (body && !(body instanceof FormData)) {
    body = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`/api${path}`, { ...options, headers, body });
  if (res.status === 401) {
    logout();
    throw new Error("Your session expired. Please sign in again.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e) => `${e.loc?.slice(1).join(".")}: ${e.msg}`).join("; ")
        : typeof detail === "string"
          ? detail
          : "The request could not be completed. Please retry.",
    );
  }
  return data;
}
export const TOOLS = {
  socratic: {
    name: "Socratic Reasoning",
    short: "SC",
    description: "Questions grounded in your course materials.",
    color: "#2861a0",
  },
  reflections: {
    name: "Reflections",
    short: "RF",
    description: "Make space to connect, reflect, and go deeper.",
    color: "#745099",
  },
  "student-agent": {
    name: "Self-Directed Learning",
    short: "SDL",
    description: "Study resources, complete a diagnostic, and follow your adaptive learning path.",
    color: "#28756b",
  },
};
export const toolInfo = (id) =>
  TOOLS[id === "self-directed-learning" ? "student-agent" : id];
export const toolSlug = (id) =>
  id === "student-agent" ? "self-directed-learning" : id;
export const toolIdFromSlug = (slug) =>
  slug === "self-directed-learning" ? "student-agent" : slug;
export const date = (value) =>
  value
    ? new Date(value).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "No due date";
export const label = (value) =>
  ({
    not_started: "Not started",
    in_progress: "In progress",
    completed: "Completed",
    draft: "Draft",
    published: "Published",
    archived: "Archived",
  })[value] || value;
