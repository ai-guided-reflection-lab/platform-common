import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const html = readFileSync(resolve(process.cwd(), "../Socratic-Chat/frontend/pipeline-logs.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const trace = {
  trace_id: "refresh-regression",
  started_at: "2026-09-25T12:00:00+00:00",
  conversation_id: "conversation",
  events: [{ stage: 12, event: "response_returned", elapsed_ms: 20, fields: { sources: 2 } }],
};
const response = (data, status = 200) => ({ ok: status === 200, status, json: async () => data });
const settle = () => vi.advanceTimersByTimeAsync(0);
let visibilityListeners = [];
function closePage() {
  vi.clearAllTimers();
  visibilityListeners.forEach((listener) => document.removeEventListener("visibilitychange", listener));
  visibilityListeners = [];
}
function openPage() {
  closePage();
  document.body.innerHTML = html.match(/<body>([\s\S]*?)<script>/)[1];
  const listen = vi.spyOn(document, "addEventListener");
  // A fresh script scope mirrors a hard navigation, not a button refresh.
  window.eval(`(() => { ${script} })()`);
  visibilityListeners = listen.mock.calls.filter(([name]) => name === "visibilitychange").map(([, listener]) => listener);
  listen.mockRestore();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ traces: [trace] })));
  vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  window.SOCRATIC_CONFIG = { API_BASE_URL: "" };
  localStorage.setItem("my_rag_chatbot_user", JSON.stringify({ access_token: "test-session" }));
});
afterEach(() => {
  closePage();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

test("fresh page loads and hard reloads fetch stored traces with auth and no cache", async () => {
  for (let reload = 0; reload < 2; reload++) {
    openPage();
    await settle();
    expect(document.querySelector("#status").textContent).toContain("1 trace(s)");
    expect(document.querySelector("#traceDetail").textContent).toContain("response_returned");
  }
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch).toHaveBeenLastCalledWith("/api/debug/pipeline/traces?limit=50", {
    method: "GET", cache: "no-store", headers: { Authorization: "Bearer test-session" },
  });
});

test("delete uses the same authentication and remains empty after a fresh page load", async () => {
  openPage();
  await settle();
  fetch.mockResolvedValue(response({ traces: [], deleted: 1 }));
  document.querySelector("#delete").click();
  await settle();
  expect(fetch).toHaveBeenLastCalledWith("/api/debug/pipeline/traces", {
    method: "DELETE", cache: "no-store", headers: { Authorization: "Bearer test-session" },
  });
  expect(document.querySelector("#status").textContent).toContain("deleted");
  openPage();
  await settle();
  expect(document.querySelector("#status").textContent).toContain("0 trace(s)");
});

test("failed deletion is visible and does not erase displayed traces", async () => {
  openPage();
  await settle();
  fetch.mockResolvedValue(response({}, 503));
  document.querySelector("#delete").click();
  await settle();
  expect(document.querySelector("#status").textContent).toContain("Delete failed (503)");
  expect(document.querySelector("#traceDetail").textContent).toContain("response_returned");
  expect(document.querySelector("#delete").disabled).toBe(false);
});

test("a pending refresh cannot restore deleted traces", async () => {
  let complete;
  fetch.mockReturnValueOnce(new Promise((resolve) => { complete = resolve; }));
  openPage();
  fetch.mockResolvedValue(response({ deleted: 1 }));
  document.querySelector("#delete").click();
  await settle();
  complete(response({ traces: [trace] }));
  await settle();
  expect(document.querySelector("#status").textContent).toContain("deleted");
  expect(document.querySelector("#traceList").textContent).not.toContain(trace.trace_id);
});

test.each([401, 503])("HTTP %s is not presented as zero traces", async (status) => {
  fetch.mockResolvedValue(response({}, status));
  openPage();
  await settle();
  expect(document.querySelector("#status .warning")).not.toBeNull();
  expect(document.querySelector("#status").textContent).not.toContain("0 trace(s)");
});

test("malformed response is not presented as zero traces", async () => {
  fetch.mockResolvedValue(response({}));
  openPage();
  await settle();
  expect(document.querySelector("#status").textContent).toContain("Invalid diagnostics response");
});

test("newly generated traces appear without reload and preserve selection", async () => {
  openPage();
  await settle();
  const newer = { ...trace, trace_id: "newer-request" };
  fetch.mockResolvedValue(response({ traces: [newer, trace] }));
  await vi.advanceTimersByTimeAsync(5000);
  expect(document.querySelector("#status").textContent).toContain("2 trace(s)");
  expect(document.querySelector(".is-active").dataset.trace).toBe(trace.trace_id);
  expect(document.querySelector("#traceDetail").textContent).toContain(trace.trace_id);
});

test("polling and repeated refresh clicks do not overlap pending reads", async () => {
  let complete;
  fetch.mockReturnValueOnce(new Promise((resolve) => { complete = resolve; }));
  openPage();
  document.querySelector("#refresh").click();
  await vi.advanceTimersByTimeAsync(15000);
  expect(fetch).toHaveBeenCalledTimes(1);
  complete(response({ traces: [trace] }));
  await settle();
  await vi.advanceTimersByTimeAsync(5000);
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("an initially empty page discovers a completed chat without a hard refresh", async () => {
  fetch.mockResolvedValueOnce(response({ traces: [] }));
  openPage();
  await settle();
  expect(document.querySelector("#status").textContent).toContain("0 trace(s)");
  await vi.advanceTimersByTimeAsync(5000);
  expect(document.querySelector("#status").textContent).toContain("1 trace(s)");
  expect(document.querySelector("#traceDetail").textContent).toContain("response_returned");
});

test("hidden tabs stop polling and refresh immediately when visible again", async () => {
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  openPage();
  await settle();
  hidden.mockReturnValue(true);
  document.dispatchEvent(new Event("visibilitychange"));
  await vi.advanceTimersByTimeAsync(15000);
  expect(fetch).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(false);
  document.dispatchEvent(new Event("visibilitychange"));
  await settle();
  expect(fetch).toHaveBeenCalledTimes(2);
});
