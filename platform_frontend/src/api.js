export const SESSION_KEY = "my_rag_chatbot_user";
const assignmentViews = new Map();
let assignmentVersion = 0;
const viewKey = path => `${session()?.access_token || ""}:${path}`;
const isAssignmentView = path => /^\/platform\/assignments(?:\?.*|\/[^/?]+)?$/.test(path);
export function cachedAssignmentView(path) {
  const entry=assignmentViews.get(viewKey(path));
  return entry && entry.expires > Date.now() ? entry.data : null;
}
const preloads = new Map();
export function pendingAssignmentDetail(id) {
  const path=`/platform/assignments/${id}`;
  const pending=preloads.get(viewKey(path));
  return pending?.then(data=>data || api(path));
}
export function preloadAssignment(id) {
  const path=`/platform/assignments/${id}`, key=viewKey(path);
  if(cachedAssignmentView(path))return Promise.resolve();
  if(preloads.has(key))return preloads.get(key);
  const request=api(path).catch(()=>null).finally(()=>preloads.delete(key));
  preloads.set(key,request);
  return request;
}
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
  const key=viewKey(path), version=assignmentVersion;
  const read=(options.method || "GET").toUpperCase()==="GET";
  if(!read && path.startsWith("/platform/")) {
    assignmentVersion++;
    assignmentViews.clear();
  }
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
  if(read && isAssignmentView(path) && version===assignmentVersion) {
    const expires=Date.now()+60000;
    assignmentViews.set(key,{data,expires});
    // Instructor list responses already contain the complete editable draft.
    // Render it immediately while the detail endpoint revalidates access and status.
    if(Array.isArray(data)) for(const item of data) {
      if(item.id && item.can_manage !== false && (item.status==="draft" || !item.config)) assignmentViews.set(`${saved?.access_token || ""}:/platform/assignments/${item.id}`,{data:item,expires});
    }
  }
  return data;
}
export const TOOLS = {
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
  "student-agent": {
    name: "Student Agent Bot",
    short: "SA",
    mode: "Practice",
    step: "03",
    description:
      "Turn course concepts into guided practice and active learning.",
    color: "#138b80",
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
  "self-directed-learning": {
    name: "Self Directed Learning",
    short: "SDL",
    mode: "Explore",
    step: "05",
    description: "Guide students through an adaptive learning activity.",
    color: "#138b80",
  },
  aiducate: {
    name: "AIducate",
    short: "AI",
    mode: "Create",
    step: "06",
    description: "Configure an AIducate learning activity.",
    color: "#b34e80",
  },
};
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
