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
  debate: {name:"Debate",short:"DB",mode:"Debate",step:"04",description:"Build and defend your argument.",color:"#005035"},
  socratic: {
    name: "Socratic Chat",
    short: "SC",
    mode: "Guide",
    step: "01",
    description:
      "Guide students through questions grounded in your course materials.",
    color: "#4f5ee8",
  },
  reflections: {
    name: "Reflections",
    short: "RF",
    mode: "Reflect",
    step: "02",
    description:
      "Create structured moments for students to connect ideas and reflect.",
    color: "#8b5cc7",
  },
  "self-directed-learning": {
    name: "Self-Directed Learning",
    short: "SDL",
    description: "Study resources, complete a diagnostic, and follow your adaptive learning path.",
    color: "#28756b",
    mode: "Practice",
    step: "03",
  },
  debate: {
    name: "Debate",
    short: "DB",
    mode: "Challenge",
    step: "04",
    description:
      "Help students build and defend arguments through focused AI challenges.",
    color: "#d15b39",
  },
};
export const toolInfo = (id) => TOOLS[id];
export const toolSlug = (id) => id;
export const toolIdFromSlug = (slug) => slug;
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
