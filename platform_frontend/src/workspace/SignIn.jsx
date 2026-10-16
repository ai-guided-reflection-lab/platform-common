import React, { useEffect, useState } from "react";
import { SESSION_KEY } from "../api";

export default function SignIn() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [demo, setDemo] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    fetch("/api/platform/demo/config")
      .then((response) => response.ok ? response.json() : {})
      .then((config) => { if (active) setDemo(Boolean(config.enabled)); })
      .catch(() => {})
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(demo ? "/api/platform/demo/enter" : "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(demo ? { username: identifier, password } : { identifier, password }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Sign in could not be completed.",
        );
      localStorage.setItem(
        SESSION_KEY,
        JSON.stringify({
          ...data,
          expires_at: Date.now() + data.expires_in_seconds * 1000,
        }),
      );
      window.location.assign(
        data.user?.onboarding_complete ? "/platform/" : "/?manage=1",
      );
    } catch (error) {
      setError(error.message);
      setBusy(false);
    }
  }
  return (
    <main className="workspace-sign-in">
      <section className="studio-step">
        <p className="p-eyebrow">{demo ? "DEMO WORKSPACE" : "YOUR UNIVERSITY WORKSPACE"}</p>
        <h1>Welcome to CourseLab</h1>
        <p>{demo ? "Choose any username and password. The same combination reopens your profile; a different combination creates a new one. Switch between Student and Professor inside." : "Sign in to access your courses and assignments."}</p>
        <form onSubmit={submit}>
          <label>
            {demo ? "Demo username" : "Email or username"}
            <input
              autoComplete="username"
              required
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <button disabled={busy || loading}>{busy ? "Opening…" : demo ? "Enter demo" : "Sign in"}</button>
        </form>
        {!demo && <p>
          <a href="/?manage=1">
            Create an account, connect GitHub, or finish account setup
          </a>
        </p>}
      </section>
    </main>
  );
}
