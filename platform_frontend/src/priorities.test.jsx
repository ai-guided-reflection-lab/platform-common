import React from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./main";
import { SESSION_KEY } from "./api";
import PriorityPlanner from "./PriorityPlanner";
import {
  DEFAULT_SITUATION,
  STORAGE_KEY,
  lifeCareerShare,
  loadState,
  rankTasks,
} from "./priorities";

const DAY = 86400000;
const now = new Date("2026-03-10T09:00:00Z").getTime();

const task = (over = {}) => ({
  id: "t",
  title: "Task",
  area: "life_career",
  impact: 3,
  effortMinutes: 30,
  energy: "steady",
  dueAt: null,
  completedAt: null,
  createdAt: "2026-03-01T09:00:00Z",
  ...over,
});

describe("ranking engine", () => {
  test("an overdue high-impact task outranks a distant low-impact one", () => {
    const ranked = rankTasks(
      [
        task({
          id: "later",
          title: "Later",
          impact: 2,
          dueAt: new Date(now + 20 * DAY),
        }),
        task({
          id: "overdue",
          title: "Overdue",
          impact: 5,
          dueAt: new Date(now - DAY),
        }),
      ],
      DEFAULT_SITUATION,
      now,
    );
    expect(ranked.map((entry) => entry.task.id)).toEqual(["overdue", "later"]);
    expect(ranked[0].rank).toBe(1);
    expect(ranked[0].reasons).toContain("Overdue — clear it first");
  });

  test("a shrinking time window promotes the task that still fits", () => {
    const tasks = [
      task({ id: "long", title: "Long", effortMinutes: 180, impact: 5 }),
      task({ id: "short", title: "Short", effortMinutes: 20, impact: 4 }),
    ];
    const roomy = rankTasks(
      tasks,
      { ...DEFAULT_SITUATION, minutesAvailable: 240 },
      now,
    );
    const tight = rankTasks(
      tasks,
      { ...DEFAULT_SITUATION, minutesAvailable: 30 },
      now,
    );
    expect(roomy[0].task.id).toBe("long");
    expect(tight[0].task.id).toBe("short");
    expect(tight.find((entry) => entry.task.id === "long").reasons).toContain(
      "Needs 180 min — longer than today allows",
    );
  });

  test("low energy demotes work that demands high energy", () => {
    const tasks = [
      task({ id: "deep", title: "Deep", energy: "high" }),
      task({ id: "easy", title: "Easy", energy: "low" }),
    ];
    const ranked = rankTasks(
      tasks,
      { ...DEFAULT_SITUATION, energy: "low", focus: "light" },
      now,
    );
    expect(ranked[0].task.id).toBe("easy");
  });

  test("balance favours exploration only while life & career stays above 80%", () => {
    const history = Array.from({ length: 10 }, (_, i) =>
      task({
        id: `done-${i}`,
        area: "life_career",
        completedAt: new Date(now - i * DAY).toISOString(),
      }),
    );
    const candidates = [
      task({ id: "career", area: "life_career" }),
      task({ id: "explore", area: "exploration" }),
    ];
    expect(lifeCareerShare(history)).toBe(1);
    expect(
      rankTasks([...history, ...candidates], DEFAULT_SITUATION, now)[0].task.id,
    ).toBe("explore");
    const skewed = [
      ...history.slice(0, 2),
      ...Array.from({ length: 8 }, (_, i) =>
        task({
          id: `x-${i}`,
          area: "exploration",
          completedAt: new Date(now - (i + 3) * DAY).toISOString(),
        }),
      ),
      ...candidates,
    ];
    expect(rankTasks(skewed, DEFAULT_SITUATION, now)[0].task.id).toBe("career");
  });

  test("only the top ten open tasks are sequenced", () => {
    const many = Array.from({ length: 14 }, (_, i) =>
      task({ id: `t-${i}`, impact: 3 }),
    );
    expect(rankTasks(many, DEFAULT_SITUATION, now)).toHaveLength(10);
  });

  test("corrupt storage falls back to an empty plan", () => {
    const storage = { getItem: () => "{oops", setItem: () => {} };
    expect(loadState(storage)).toEqual({
      tasks: [],
      situation: { ...DEFAULT_SITUATION },
    });
  });
});

describe("planner workspace", () => {
  beforeEach(() => localStorage.clear());

  const openPlanner = () =>
    render(
      <MemoryRouter initialEntries={["/priorities"]}>
        <PriorityPlanner />
      </MemoryRouter>,
    );

  async function addTask(user, { title, impact = "4", effort = "30" }) {
    await user.clear(screen.getByLabelText("Task"));
    await user.type(screen.getByLabelText("Task"), title);
    await user.clear(screen.getByLabelText("Impact (1–5)"));
    await user.type(screen.getByLabelText("Impact (1–5)"), impact);
    await user.clear(screen.getByLabelText("Effort (minutes)"));
    await user.type(screen.getByLabelText("Effort (minutes)"), effort);
    await user.click(screen.getByRole("button", { name: "Add task" }));
  }

  test("tasks are captured, ranked with reasons, and persisted in the browser", async () => {
    openPlanner();
    const user = userEvent.setup();
    expect(
      await screen.findByRole("heading", { name: "Daily Priorities" }),
    ).toBeInTheDocument();
    await addTask(user, {
      title: "Long research detour",
      effort: "180",
      impact: "5",
    });
    await addTask(user, {
      title: "Send the application",
      effort: "20",
      impact: "4",
    });
    const ranking = screen.getByRole("list", { name: /Top 10 right now/i });
    expect(
      within(ranking).getAllByRole("heading", { level: 3 })[0],
    ).toHaveTextContent("Long research detour");
    expect(
      within(ranking).getAllByText(/Fits your 180 min window/)[0],
    ).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).tasks).toHaveLength(2);
  });

  test("changing the situation re-ranks the top list immediately", async () => {
    openPlanner();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Daily Priorities" });
    await addTask(user, {
      title: "Long research detour",
      effort: "180",
      impact: "5",
    });
    await addTask(user, {
      title: "Send the application",
      effort: "20",
      impact: "4",
    });
    const minutes = screen.getByLabelText("Time available (minutes)");
    await user.clear(minutes);
    await user.type(minutes, "30");
    const ranking = screen.getByRole("list", { name: /Top 10 right now/i });
    expect(
      within(ranking).getAllByRole("heading", { level: 3 })[0],
    ).toHaveTextContent("Send the application");
  });

  test("completing and deleting a task updates the ranking and balance", async () => {
    openPlanner();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Daily Priorities" });
    await addTask(user, { title: "Send the application", effort: "20" });
    const all = screen.getByRole("heading", {
      name: "All tasks",
    }).parentElement;
    await user.click(within(all).getByRole("button", { name: "Complete" }));
    expect(within(all).getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Nothing ranked yet")).toBeInTheDocument();
    await user.click(within(all).getByRole("button", { name: "Delete" }));
    expect(screen.getByText("No tasks captured yet")).toBeInTheDocument();
  });

  test("an edited task keeps its identity and new settings", async () => {
    openPlanner();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Daily Priorities" });
    await addTask(user, { title: "Draft resume", effort: "45" });
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const form = screen
      .getByRole("button", { name: "Save task" })
      .closest("form");
    const title = within(form).getByLabelText("Task");
    await user.clear(title);
    await user.type(title, "Draft resume v2");
    await user.selectOptions(
      within(form).getByLabelText("Area"),
      "exploration",
    );
    await user.click(within(form).getByRole("button", { name: "Save task" }));
    const ranking = screen.getByRole("list", { name: /Top 10 right now/i });
    expect(within(ranking).getByText("Draft resume v2")).toBeInTheDocument();
    expect(within(ranking).getByText(/Exploration/)).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).tasks).toHaveLength(1);
  });

  test("a storage failure is surfaced instead of silently losing the plan", async () => {
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("quota");
      });
    openPlanner();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "blocked local storage",
    );
    setItem.mockRestore();
  });
});

test.each([
  ["professor", 1, "/professor"],
  ["student", 2, "/student"],
])(
  "the %s dashboard offers the planner as a personal tool card",
  async (_role, authority_level, path) => {
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ access_token: "t", expires_at: Date.now() + 3600000 }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const data = url.endsWith("/auth/me")
          ? {
              user: {
                username: "Alex",
                display_name: "Alex",
                authority_level,
                onboarding_complete: true,
              },
            }
          : [];
        return { ok: true, status: 200, json: async () => data };
      }),
    );
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    const card = await screen.findByRole("link", {
      name: /DP Daily Priorities/,
    });
    expect(card).toHaveAttribute("href", "/priorities");
    await user.click(card);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Daily Priorities",
      }),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  },
);
