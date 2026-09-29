const USER_KEY = "adaptive-student-user";

export const currentUser = () => localStorage.getItem(USER_KEY) || "student-alex";
export const setCurrentUser = (id) => localStorage.setItem(USER_KEY, id);

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Demo-User", currentUser());
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}
