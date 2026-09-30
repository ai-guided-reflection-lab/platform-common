const USER_KEY = "adaptive-instructor-user";

export const currentUser = () => localStorage.getItem(USER_KEY) || "instructor-demo";
export const setCurrentUser = (id) => localStorage.setItem(USER_KEY, id);

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Demo-User", currentUser());
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(item => `${item.loc?.slice(1).join(" ") || "Input"}: ${item.msg}`).join("; ") : detail?.issues ? `${detail.message} ${detail.issues.join(" ")}` : `Request failed (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}
