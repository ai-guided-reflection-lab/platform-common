import { api, session, logout } from "./api";

export async function loadSignedInStudent() {
  const { user } = await api("/auth/me");
  if (user.authority_level <= 1)
    throw new Error("Open this workspace with your student account.");
  if (!user.onboarding_complete)
    throw new Error("Complete your account setup before opening a lesson.");
  return [
    {
      id: String(user.user_id || user.id || user.username),
      display_name: user.display_name || user.username,
      role: "student",
    },
  ];
}

export function studentTransport(path, options = {}) {
  if (!/^\/student\/assignments(?:\/|$)/.test(path))
    throw new Error(
      "This student action is not available through the platform.",
    );
  const body =
    typeof options.body === "string" ? JSON.parse(options.body) : options.body;
  if (
    options.responseType === "blob" &&
    /^\/student\/assignments\/[^/]+\/materials\/[^/]+$/.test(path)
  ) {
    return downloadMaterial(path);
  }
  return api(
    path.replace(
      /^\/student\/assignments/,
      "/platform/self-directed/assignments",
    ),
    { ...options, body },
  );
}

async function downloadMaterial(path) {
  const response = await fetch(
    "/api" +
      path.replace(
        /^\/student\/assignments/,
        "/platform/self-directed/assignments",
      ),
    {
      headers: { Authorization: `Bearer ${session()?.access_token || ""}` },
    },
  );
  if (response.status === 401) {
    logout();
    throw new Error("Your session expired. Please sign in again.");
  }
  if (!response.ok)
    throw new Error(
      "This course material could not be downloaded. Please try again.",
    );
  return response.blob();
}
