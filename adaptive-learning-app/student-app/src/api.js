const USER_KEY = "adaptive-student-user";
let platformTransport = null;
export const configureStudentTransport = (transport) => { platformTransport = transport; };

export const currentUser = () => localStorage.getItem(USER_KEY) || "student-alex";
export const setCurrentUser = (id) => localStorage.setItem(USER_KEY, id);

export async function api(path, options = {}) {
  if (platformTransport) return platformTransport(path, options);
  const headers = new Headers(options.headers || {});
  headers.set("X-Demo-User", currentUser());
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(item => `${item.loc?.slice(1).join(" ") || "Input"}: ${item.msg}`).join("; ") : detail?.issues ? `${detail.message} ${detail.issues.join(" ")}` : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return response.json();
}
