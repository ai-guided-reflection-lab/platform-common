import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./main";
import { SESSION_KEY } from "./api";

const course = "8b71218d-71f3-436e-a4a6-1b279c4fda79";
const assignment = {
  id: "assignment-1",
  course_id: course,
  course_code: "SE101",
  tool: "socratic",
  title: "Discuss requirements",
  instructions: "Connect your ideas.",
  due_at: null,
  status: "published",
  progress: "not_started",
  student_config: { minimum_messages: 1 },
};
const attempt = {
  id: "attempt-1",
  status: "in_progress",
  engine_state: {},
  messages: [
    { role: "assistant", content: "What makes a requirement useful?" },
  ],
};

function mockApi(role = "instructor", override = {}) {
  localStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      access_token: "test-session",
      expires_at: Date.now() + 3600000,
    }),
  );
  const responses = {
    "/api/auth/me": {
      user: {
        username: "Alex",
        display_name: "Alex Rivera",
        authority_level: role === "instructor" ? 1 : 2,
        onboarding_complete: true,
      },
    },
    "/api/platform/assignments": [assignment],
    "/api/courses": {
      courses: [
        {
          course_id: course,
          course_code: "SE101",
          title: "Software Engineering",
          membership_role: "instructor",
        },
      ],
    },
    [`/api/instructor/enrolled-students?course_id=${course}`]: [
      {
        user_id: "student-1",
        display_name: "Jordan",
        email: "jordan@example.test",
      },
    ],
    [`/api/courses/${course}/documents`]: { files: [] },
    "/api/platform/topic-templates": [],
    "/api/platform/adaptive-plans": [],
    "/api/platform/assignments/assignment-1": assignment,
    "/api/platform/assignments/assignment-1/attempt": null,
    "/api/platform/assignments/assignment-1/start": attempt,
    ...override,
  };
  const fetch = vi.fn(async (url, options = {}) => {
    const entry =
      responses[`${options.method || "GET"} ${url}`] ?? responses[url];
    if (entry === undefined) throw new Error("Unexpected API call: " + url);
    const data = typeof entry === "function" ? entry(options) : entry;
    return {
      ok: !data?.error,
      status: data?.error ? 422 : 200,
      json: async () => (data?.error ? { detail: data.error } : data),
    };
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function open(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

test("professor selects each explicit tool dashboard", async () => {
  mockApi();
  open("/professor");
  const user = userEvent.setup();
  expect(
    await screen.findByRole("heading", { name: "Choose how you’ll teach." }),
  ).toBeInTheDocument();
  const reflection = screen.getByRole("link", { name: /RF Reflections/ });
  expect(
    screen.getByRole("link", { name: /SC Socratic Chat/ }),
  ).toHaveAttribute("href", "/professor/tools/socratic");
  expect(
    screen.getByRole("link", { name: /SA Student Agent Bot/ }),
  ).toHaveAttribute("href", "/professor/tools/student-agent");
  await user.click(reflection);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Reflections" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New assignment" })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Course"), course);
  await user.click(screen.getByRole("button", { name: "New assignment" }));
  expect(
    await screen.findByRole("heading", { name: "Reflections settings" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Reflection type")).toHaveValue("topic_based");
});

test("student sees mixed assignments and opens the assigned tool without selecting configuration", async () => {
  mockApi("student", {
    "/api/platform/assignments": [
      assignment,
      {
        ...assignment,
        id: "reflection-1",
        tool: "reflections",
        title: "Reflect on the sprint",
        progress: "in_progress",
      },
      {
        ...assignment,
        id: "tutor-1",
        tool: "student-agent",
        title: "Practice a use case",
        progress: "completed",
      },
    ],
  });
  open("/student");
  const user = userEvent.setup();
  expect(
    await screen.findByRole("heading", { name: "Your next steps, all here." }),
  ).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Resume" })).toHaveAttribute(
    "href",
    "/student/assignments/reflection-1",
  );
  expect(screen.getByRole("link", { name: "View result" })).toHaveAttribute(
    "href",
    "/student/assignments/tutor-1",
  );
  await user.click(screen.getByRole("link", { name: "Open assignment" }));
  await user.click(
    await screen.findByRole("button", { name: "Start assignment" }),
  );
  expect(
    await screen.findByText("What makes a requirement useful?"),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Student ID")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Reflection type")).not.toBeInTheDocument();
});

test("student sees adaptive objectives and required task status", async () => {
  const learningPlan = {
    title: "Object-Oriented Programming",
    objectives: [
      { id: "OBJ-1", description: "Explain classes and objects." },
      { id: "OBJ-2", description: "Create a class with methods." },
    ],
    required_task: { title: "Implement a BankAccount class" },
  };
  const adaptiveAssignment = {
    ...assignment,
    tool: "student-agent",
    student_config: {
      topic_name: learningPlan.title,
      learning_plan: learningPlan,
      resources: [],
    },
  };
  const adaptiveAttempt = {
    ...attempt,
    required_task_status: "in_progress",
    engine_state: {
      adaptive: true,
      current_objective_id: "OBJ-2",
      required_task_status: "in_progress",
      objective_progress: [
        { objective_id: "OBJ-1", status: "demonstrated" },
        { objective_id: "OBJ-2", status: "developing" },
      ],
    },
  };
  mockApi("student", {
    "/api/platform/assignments/assignment-1": adaptiveAssignment,
    "/api/platform/assignments/assignment-1/attempt": adaptiveAttempt,
  });
  open("/student/assignments/assignment-1");

  expect(await screen.findByText("Implement a BankAccount class")).toBeInTheDocument();
  expect(screen.getByText(/Current objective:/)).toBeInTheDocument();
  expect(screen.getAllByText("Create a class with methods.").length).toBeGreaterThan(0);
  expect(screen.getByText("demonstrated")).toBeInTheDocument();
  expect(screen.getByText("developing")).toBeInTheDocument();
  expect(screen.getAllByText(/in progress/i).length).toBeGreaterThan(0);
});

test("failed publish retains a saved draft and shows an actionable error", async () => {
  const saved = {
    ...assignment,
    status: "draft",
    audience: "course",
    recipient_ids: [],
    config: { document_ids: [], prompt: "", minimum_messages: 1 },
  };
  const fetch = mockApi("instructor", {
    "POST /api/platform/assignments": saved,
    "/api/platform/assignments/assignment-1": saved,
    "/api/platform/assignments/assignment-1/publish": {
      error: "Upload course materials first.",
    },
  });
  open(`/professor/tools/socratic/assignments/new?course=${course}`);
  const user = userEvent.setup();
  await user.type(
    await screen.findByLabelText("Title"),
    "Discuss requirements",
  );
  await user.click(screen.getByRole("button", { name: "Publish assignment" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Upload course materials first.",
  );
  expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
  expect(
    fetch.mock.calls.filter(
      ([url, opt]) =>
        url === "/api/platform/assignments" && opt.method === "POST",
    ),
  ).toHaveLength(1);
});

test("retrying a failed student message reuses its idempotency key", async () => {
  let count = 0;
  const fetch = mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "/api/platform/assignments/assignment-1/messages": () =>
      ++count === 1
        ? { error: "Engine unavailable. Retry shortly." }
        : {
            ...attempt,
            messages: [
              ...attempt.messages,
              { role: "user", content: "My answer" },
              { role: "assistant", content: "Good example" },
            ],
          },
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Your message"), "My answer");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Engine unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Good example")).toBeInTheDocument();
  const requests = fetch.mock.calls
    .filter(([url]) => url.endsWith("/messages"))
    .map(([, opts]) => JSON.parse(opts.body));
  expect(requests[0].request_id).toBe(requests[1].request_id);
});

test("student cannot enter professor configuration routes", async () => {
  mockApi("student");
  open("/professor/tools/reflections");
  expect(
    await screen.findByRole("heading", { name: "Your next steps, all here." }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "New assignment" }),
  ).not.toBeInTheDocument();
});
