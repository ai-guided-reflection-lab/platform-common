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
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null;
  return response.json();
}
