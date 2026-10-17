import React, { useEffect, useState } from "react";
import { App } from "./main";
import { configureStudentTransport } from "./api";

const KEY = "adaptive-lab-session-v1";
export async function labRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");
  const token = localStorage.getItem(KEY);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api${path}`, { ...options, headers });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem(KEY);
      window.dispatchEvent(new Event("lab-session-ended"));
    }
    throw new Error(typeof data.detail === "string" ? data.detail : "The request could not be completed.");
  }
  return data;
}

configureStudentTransport(labRequest);

export default function LabApp() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [listVersion, setListVersion] = useState(0);
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const end = () => setUser(null);
    window.addEventListener("lab-session-ended", end);
    if (localStorage.getItem(KEY)) {
      labRequest("/lab/session").then(setUser).catch(e => setError(e.message)).finally(() => setLoading(false));
    } else setLoading(false);
    return () => window.removeEventListener("lab-session-ended", end);
  }, []);
  async function join(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await labRequest("/lab/sessions", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      localStorage.setItem(KEY, result.token); setUser(result.user);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function unlock(event) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    try {
      const result = await labRequest("/lab/redeem", {method:"POST",body:JSON.stringify({code})});
      setCode(""); setSuccess(`${result.title} added to your assignments.`); setListVersion(v => v + 1);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  if (loading) return <div className="shell"><main><p>Loading your session…</p></main></div>;
  if (user) return <App key={listVersion} loadUsers={async () => [user]} labMode assignmentAccess={<section className="panel"><h2>Add an assignment</h2><form onSubmit={unlock}><label htmlFor="assignment-code">Assignment code</label><input id="assignment-code" value={code} onChange={e => setCode(e.target.value)} maxLength={40} required autoComplete="off" /><button disabled={busy || !code.trim()}>{busy ? "Adding…" : "Add assignment"}</button></form>{error && <div className="notice error" role="alert">{error}</div>}{success && <p role="status">{success}</p>}</section>} />;
  return <div className="shell"><main><section className="welcome"><div><p className="eyebrow">Adaptive Learning</p><h1>Welcome to the lab.</h1><p>Enter your name to explore the assignments. Your progress is saved in this browser.</p></div></section><form onSubmit={join}><label htmlFor="participant-name">Your name</label><input id="participant-name" value={name} onChange={e => setName(e.target.value)} maxLength={80} autoComplete="name" required /><button disabled={busy || !name.trim()}>{busy ? "Joining…" : "View assignments"}</button></form>{error && <div className="notice error" role="alert">{error}</div>}</main></div>;
}
