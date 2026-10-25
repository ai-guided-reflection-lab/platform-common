import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import CreateActivity from "./CreateActivity";
import { resetCourseContext } from "./courseContext";
import { api } from "./api";
vi.mock("./api", async (original) => ({ ...(await original()), api: vi.fn() }));
const course = {
  course_id: "course-1",
  course_code: "SE101",
  title: "Software Engineering",
  membership_role: "instructor",
};
let courseFiles;
beforeEach(() => {
  resetCourseContext();
  courseFiles = [
    {
      file_id: "f1",
      document_id: "d1",
      filename: "Requirements.pdf",
      file_size: 2048,
    },
  ];
  api.mockReset();
  api.mockImplementation(async (path, options) => {
    if (path.startsWith("/platform/context")) return course;
    if (path === "/platform/courses/course-1/documents")
      return { files: courseFiles };
    if (
      path === "/platform/courses/course-1/documents/upload" &&
      options?.method === "POST"
    ) {
      courseFiles = [
        ...courseFiles,
        {
          file_id: "f2",
          document_id: "d2",
          filename: "New lesson.pdf",
          file_size: 1024,
        },
      ];
      return { files: [{ file_id: "f2", document_id: "d2" }] };
    }
    if (path === "/courses/course-1/documents") return { files: courseFiles };
    if (path === "/courses/course-1/learning-objectives")
      return { objectives: [] };
    if (path === "/courses/course-1/documents/f1/keyword-suggestions")
      return { keywords: ["design patterns"], message: "Generated." };
    if (path === "/courses/course-1/documents/f2/keyword-suggestions")
      return { keywords: ["new lesson topic"], message: "Generated." };
    if (
      path.startsWith("/courses/course-1/documents/") &&
      options?.method === "DELETE"
    ) {
      const fileId = path.split("/").at(-1);
      courseFiles = courseFiles.filter((file) => file.file_id !== fileId);
      return { deleted: true };
    }
    if (path === "/platform/assignments/a1/prepare-sdl")
      return { learning_plan: { title: "Prepared lesson", objectives: [] } };
    if (path === "/platform/assignments/a1/keywords/confirm")
      return {
        ready: true,
        course_id: "course-1",
        keywords: ["design"],
        document_ids: ["d1"],
        passage_count: 3,
      };
    if (path === "/platform/assignments")
      return { ...options.body, id: "a1", status: "draft" };
    throw Error(path);
  });
});
async function open() {
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <CreateActivity />
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      expect.stringContaining("/platform/context"),
    ),
  );
  expect(
    screen.getByRole("heading", { name: "Assignment Configuration" }),
  ).toBeInTheDocument();
  await user.type(
    await screen.findByLabelText("Assignment title"),
    "Compare design choices",
  );
  return user;
}

test.each(["socratic", "debate"])("recommended %s settings remain editable and save only after instructor action", async activity => {
  const user = await open();
  await user.click(await screen.findByRole("checkbox", { name: /Requirements.pdf/ }));
  const originalApi = api.getMockImplementation();
  const config = activity === "socratic"
    ? { keywords: ["processes", "threads"], prompt: "Explain process isolation.", minimum_messages: 4 }
    : { scenario: "Defend processes or threads for a server using course evidence.", opening_prompt: "Which design would you choose?", minimum_messages: 4 };
  api.mockImplementation((path, options) => path === "/platform/copilot/propose"
    ? Promise.resolve({ proposal: { tool: activity, title: "Processes and threads", instructions: "Explain resource sharing.",
      objectives: ["Distinguish processes from threads"], rationale: "Diagnoses misconceptions.", config },
      evidence: [{ document_id: "d1", title: "OS.pdf", excerpt: "Threads share an address space." }], warnings: [] })
    : originalApi(path, options));
  fireEvent.change(screen.getByLabelText("Learning outcome"), { target: { value: "Distinguish processes from threads using OS materials." } });
  await user.click(screen.getByRole("button", { name: "Prepare proposal" }));
  await user.click(await screen.findByRole("button", { name: "Apply proposal" }));
  expect(screen.getByLabelText("Assignment title")).toHaveValue("Processes and threads");
  expect(screen.getByLabelText("Description")).toHaveValue("Explain resource sharing.\n\nLearning objectives:\n- Distinguish processes from threads");
  const prompt = screen.getByLabelText(activity === "socratic" ? "Opening question or prompt" : "Opening prompt");
  expect(prompt).toHaveValue(activity === "socratic" ? config.prompt : config.opening_prompt);
  expect(screen.getByLabelText("Messages required before completion")).toHaveValue(4);
  fireEvent.pointerDown(screen.getByText(/Diagnoses misconceptions/));
  expect(prompt).toBeInTheDocument();
  expect(api.mock.calls.filter(([path, options]) => path.startsWith("/platform/assignments") && options?.method)).toEqual([]);
  fireEvent.change(prompt, { target: { value: "Edited prompt" } });
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  expect(api).toHaveBeenCalledWith("/platform/assignments", expect.objectContaining({ body: expect.objectContaining({
    tool: activity, config: expect.objectContaining({ document_ids: ["d1"],
      [activity === "socratic" ? "prompt" : "opening_prompt"]: "Edited prompt" }),
  }) }));
});
test("five choices replace Student Agent; settings follow Next and review invalidates after edits", async () => {
  const user = await open();
  for (const name of [
    "Socratic Chat",
    "Reflections",
    "Self Directed Learning",
    "Debate",
    "AIducate",
  ])
    expect(
      screen.getByRole("button", { name: new RegExp(name) }),
    ).toBeInTheDocument();
  expect(screen.queryByText("Student Agent Bot")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Socratic Chat/ }));
  expect(
    screen.getByRole("heading", { name: "Socratic Chat settings" }),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText("Opening question or prompt"),
  ).toBeEnabled();
  expect(
    screen.getByLabelText("Messages required before completion"),
  ).toBeEnabled();
  const optional = await screen.findByRole("region", {
    name: "Optional keywords",
  });
  expect(
    screen.queryByRole("heading", { name: "Course documents" }),
  ).not.toBeInTheDocument();
  expect(
    within(optional).getByRole("button", { name: "Keywords Generation" }),
  ).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Review activity" }));
  expect(
    screen.getByRole("button", { name: "Publish activity" }),
  ).toBeEnabled();
  await user.type(screen.getByLabelText("Description"), "Updated instructions");
  expect(
    screen.queryByRole("heading", { name: "Review and publish" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("combobox", { name: "Course" }),
  ).not.toBeInTheDocument();
});
test("selected materials and description persist when a new chat is saved as a draft", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.type(
    screen.getByLabelText("Description"),
    "Consider opposing views.",
  );
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  await user.type(
    screen.getByLabelText("Debate topic or scenario"),
    "Should software teams use AI?",
  );
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/platform/assignments",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          instructions: "Consider opposing views.",
          tool: "debate",
          config: expect.objectContaining({
            document_ids: ["d1"],
            scenario: "Should software teams use AI?",
          }),
        }),
      }),
    ),
  );
});
test("clear all removes selected documents", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  expect(
    screen.getByRole("heading", { name: "Selected documents (1)" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Clear all" }));
  expect(
    screen.getByRole("heading", { name: "Selected documents (0)" }),
  ).toBeInTheDocument();
});

test("Reflections copilot applies locally, invalidates review, and preserves milestone CSV", async () => {
  const user = await open();
  expect(
    screen.getByRole("heading", { name: "Assignment Copilot" }),
  ).toBeInTheDocument();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(screen.getByRole("button", { name: /Reflections/ }));
  expect(
    screen.getByRole("heading", { name: "Assignment Copilot" }),
  ).toBeInTheDocument();
  await user.selectOptions(
    screen.getByLabelText("Reflection type"),
    "milestone_based",
  );
  const csv = "name,challenge,solution\nStudent,Hard task,Tried testing";
  const file = new File([csv], "history.csv", { type: "text/csv" });
  file.text = vi.fn().mockResolvedValue(csv);
  await user.upload(screen.getByLabelText("Historical responses (CSV)"), file);
  await user.type(
    screen.getByLabelText("Milestone prompt"),
    "Original milestone prompt",
  );
  await user.click(screen.getByRole("button", { name: "Review activity" }));
  expect(
    screen.getByRole("heading", { name: "Review and publish" }),
  ).toBeInTheDocument();
  const originalApi = api.getMockImplementation();
  api.mockImplementation((path, options) =>
    path === "/platform/copilot/propose"
      ? Promise.resolve({
          proposal: {
            tool: "reflections",
            objectives: ["Explain verification"],
            title: "Proposed milestone",
            instructions: "Reflect on the challenge and solution.",
            rationale: "Encourages applied reflection.",
            config: {
              module_type: "milestone_based",
              milestone_prompt: "Explain how you verified your solution.",
              historical_data: "",
              document_ids: ["untrusted"],
            },
          },
          evidence: [
            {
              document_id: "d1",
              title: "Requirements.pdf",
              excerpt: "Requirements should be verifiable.",
            },
          ],
        })
      : originalApi(path, options),
  );
  fireEvent.change(screen.getByLabelText("Reflection goal"), {
    target: { value: "Reflect on testability after the project." },
  });
  await user.click(screen.getByRole("button", { name: "Prepare proposal" }));
  await screen.findByRole("button", { name: "Apply proposal" });
  expect(screen.getByLabelText("Assignment title")).toHaveValue(
    "Compare design choices",
  );
  expect(screen.getByLabelText("Milestone prompt")).toHaveValue(
    "Original milestone prompt",
  );
  const prepare = api.mock.calls.find(
    ([path]) => path === "/platform/copilot/propose",
  );
  expect(JSON.stringify(prepare)).not.toContain("historical_data");
  expect(JSON.stringify(prepare)).not.toContain(csv);
  await user.click(screen.getByRole("button", { name: "Apply proposal" }));
  expect(screen.getByLabelText("Assignment title")).toHaveValue(
    "Proposed milestone",
  );
  expect(screen.getByLabelText("Description")).toHaveValue(
    "Reflect on the challenge and solution.\n\nLearning objectives:\n- Explain verification",
  );
  expect(screen.getByLabelText("Milestone prompt")).toHaveValue(
    "Explain how you verified your solution.",
  );
  expect(
    screen.queryByRole("heading", { name: "Review and publish" }),
  ).not.toBeInTheDocument();
  expect(
    api.mock.calls.filter(
      ([path, options]) =>
        path.startsWith("/platform/assignments") && options?.method,
    ),
  ).toEqual([]);
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  const saved = api.mock.calls.find(
    ([path, options]) =>
      path === "/platform/assignments" && options?.method === "POST",
  );
  expect(saved[1].body.config.historical_data).toBe(csv);
  expect(saved[1].body.config.document_ids).toEqual(["d1"]);
});

test("copilot failure leaves the manual Reflections controls usable", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(screen.getByRole("button", { name: /Reflections/ }));
  const originalApi = api.getMockImplementation();
  api.mockImplementation((path, options) =>
    path === "/platform/copilot/propose"
      ? Promise.reject(Error("Local model unavailable"))
      : originalApi(path, options),
  );
  fireEvent.change(screen.getByLabelText("Reflection goal"), {
    target: { value: "Reflect on testability in practice." },
  });
  await user.click(screen.getByRole("button", { name: "Prepare proposal" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Local model unavailable",
  );
  const topics = screen.getByLabelText(/Sub-topics to explore/);
  expect(topics).toBeEnabled();
  fireEvent.change(topics, { target: { value: "Manually configured topic" } });
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  expect(api).toHaveBeenCalledWith(
    "/platform/assignments",
    expect.objectContaining({
      body: expect.objectContaining({
        config: expect.objectContaining({
          sub_topics: ["Manually configured topic"],
        }),
      }),
    }),
  );
});

test("topic proposal populates editable pedagogical controls without saving", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(screen.getByRole("button", { name: /Reflections/ }));
  const originalApi = api.getMockImplementation();
  api.mockImplementation((path, options) =>
    path === "/platform/copilot/propose"
      ? Promise.resolve({
          proposal: {
            tool: "reflections",
            objectives: ["Explain verification"],
            title: "Verify requirements",
            instructions: "Explain your verification method.",
            rationale: "Connects concepts to practice.",
            config: {
              module_type: "topic_based",
              required_topics: ["Testability"],
              sub_topics: ["Explain verification"],
              expected_depth: "applied",
              probing_style: "socratic",
              must_include_application: true,
              custom_notes: "Ask for an example.",
            },
          },
          evidence: [
            {
              document_id: "d1",
              title: "Requirements.pdf",
              excerpt: "Requirements are verifiable.",
            },
          ],
        })
      : originalApi(path, options),
  );
  fireEvent.change(screen.getByLabelText("Reflection goal"), {
    target: { value: "Reflect on testability in practice." },
  });
  await user.click(screen.getByRole("button", { name: "Prepare proposal" }));
  await user.click(
    await screen.findByRole("button", { name: "Apply proposal" }),
  );
  expect(screen.getByLabelText(/Learning topics/)).toHaveValue("Testability");
  expect(screen.getByLabelText(/Sub-topics to explore/)).toHaveValue(
    "Explain verification",
  );
  expect(screen.getByLabelText("Expected depth")).toHaveValue("applied");
  expect(screen.getByLabelText("Probing style")).toHaveValue("socratic");
  expect(
    screen.getByLabelText("Require a practical application"),
  ).toBeChecked();
  expect(screen.getByLabelText("Professor notes")).toHaveValue(
    "Ask for an example.",
  );
  expect(
    api.mock.calls.some(([path]) => path.startsWith("/platform/assignments")),
  ).toBe(false);
});

test("a PDF upload appears in the course library and is selected", async () => {
  const user = await open();
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["%PDF-1.4"], "New lesson.pdf", { type: "application/pdf" }),
  );
  expect(
    await screen.findByRole("checkbox", { name: /New lesson.pdf/ }),
  ).toBeChecked();
  expect(
    screen.getByText("Documents uploaded and ready to select."),
  ).toBeInTheDocument();
});

test("an embedding failure is shown next to the upload control", async () => {
  const user = await open();
  await screen.findByRole("checkbox", { name: /Requirements.pdf/ });
  api.mockImplementationOnce(async () => {
    throw new Error("Document search has no configured embedding provider.");
  });
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["%PDF-1.4"], "New lesson.pdf", { type: "application/pdf" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "embedding provider",
  );
});

test("a completed request is not reported as success when the PDF is absent from the refreshed library", async () => {
  const user = await open();
  await screen.findByRole("checkbox", { name: /Requirements.pdf/ });
  const originalApi = api.getMockImplementation();
  api.mockImplementation((path, options) =>
    path === "/platform/courses/course-1/documents/upload" &&
    options?.method === "POST"
      ? Promise.resolve({ files: [{ file_id: "missing", document_id: "d2" }] })
      : originalApi(path, options),
  );
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["%PDF-1.4"], "New lesson.pdf", { type: "application/pdf" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "not in this course's library",
  );
  expect(
    screen.queryByText("Documents uploaded and ready to select."),
  ).not.toBeInTheDocument();
});

test("instructors can delete uploaded documents from course materials", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(
    screen.getByRole("button", { name: "Delete Requirements.pdf" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("checkbox", { name: /Requirements.pdf/ }),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole("heading", { name: "Selected documents (0)" }),
  ).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/courses/course-1/documents/f1", {
    method: "DELETE",
  });
});

test("Socratic settings can approve and prepare keywords", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(screen.getByRole("button", { name: /Socratic Chat/ }));
  await user.type(
    await screen.findByRole("textbox", { name: "New keyword" }),
    "design",
  );
  await user.click(
    screen.getByRole("button", { name: "Add optional keyword" }),
  );
  await user.click(
    screen.getByRole("button", { name: "Approve keyword design" }),
  );
  await user.click(screen.getByRole("button", { name: "Confirm keywords" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/platform/assignments/a1/keywords/confirm",
      { method: "POST" },
    ),
  );
  expect(
    await screen.findByText(
      "Keywords confirmed. Course materials are prepared; publish when ready.",
    ),
  ).toBeInTheDocument();
});

test("Keywords Generation uses the assignment's selected documents", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(screen.getByRole("button", { name: /Socratic Chat/ }));
  await user.click(
    await screen.findByRole("button", { name: "Keywords Generation" }),
  );
  expect(
    await screen.findByRole("button", {
      name: "Approve keyword design patterns",
    }),
  ).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith(
    "/courses/course-1/documents/f1/keyword-suggestions",
    { method: "POST" },
  );
});

test("uploading an indexed document activates keyword generation immediately", async () => {
  courseFiles = [];
  const user = await open();
  await user.click(screen.getByRole("button", { name: /Socratic Chat/ }));
  const generate = await screen.findByRole("button", {
    name: "Keywords Generation",
  });
  expect(generate).toBeDisabled();
  fireEvent.change(document.querySelector('input[type="file"][multiple]'), {
    target: {
      files: [
        new File(["lesson"], "New lesson.pdf", {
          type: "application/pdf",
        }),
      ],
    },
  });
  await waitFor(() => expect(generate).toBeEnabled());
  await user.click(generate);
  expect(
    await screen.findByRole("button", {
      name: "Approve keyword new lesson topic",
    }),
  ).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith(
    "/courses/course-1/documents/f2/keyword-suggestions",
    { method: "POST" },
  );
});

test("SDL review prepares a lesson before showing publish", async () => {
  const user = await open();
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.pdf/ }),
  );
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  await user.type(
    screen.getByLabelText("Starting point"),
    "Write a requirement",
  );
  await user.type(
    screen.getByLabelText("Ending point"),
    "Verify a requirement",
  );
  await user.click(screen.getByRole("button", { name: "Review activity" }));
  expect(await screen.findByText("Prepared lesson")).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/platform/assignments/a1/prepare-sdl", {
    method: "POST",
  });
  expect(
    screen.getByRole("button", { name: "Publish activity" }),
  ).toBeEnabled();
});
test("Debate can proceed to publish while AIducate stays a draft", async () => {
  const user = await open();
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  await user.click(screen.getByRole("button", { name: "Review activity" }));
  expect(
    screen.getByRole("button", { name: "Publish activity" }),
  ).toBeEnabled();
  await user.click(screen.getByRole("button", { name: /AIducate/ }));
  await user.click(screen.getByRole("button", { name: "Review activity" }));
  expect(
    screen.getByRole("button", { name: "Publish activity" }),
  ).toBeEnabled();
});

test("SDL selection immediately exposes learning boundaries without a course picker", async () => {
  const user = await open();
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  expect(screen.getByLabelText("Starting point")).toBeInTheDocument();
  expect(screen.getByLabelText("Ending point")).toBeInTheDocument();
  expect(screen.queryByLabelText("Course")).not.toBeInTheDocument();
});

test("draft chat choices remain available and preserve settings while switching", async () => {
  const user = await open();
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  await user.type(
    screen.getByLabelText("Debate topic or scenario"),
    "Should teams prioritize maintainability?",
  );
  for (const name of ["Save draft", "Review activity", "Publish activity"])
    expect(
      screen.getByRole("button", { name, exact: true }),
    ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  expect(screen.getByLabelText("Starting point")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Debate/ })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  expect(screen.getByLabelText("Debate topic or scenario")).toHaveValue(
    "Should teams prioritize maintainability?",
  );
});

test("clicking blank space clears selection while preserving entered chat settings", async () => {
  const user = await open();
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  await user.type(
    screen.getByLabelText("Debate topic or scenario"),
    "Should we optimize early?",
  );
  expect(
    screen.getByRole("heading", { name: "Debate settings" }),
  ).toBeInTheDocument();
  await user.click(document.body);
  expect(
    screen.queryByRole("heading", { name: "Debate settings" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Assignment title")).toHaveValue(
    "Compare design choices",
  );
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  expect(screen.getByLabelText("Debate topic or scenario")).toHaveValue(
    "Should we optimize early?",
  );
});

test("native due-date input is included in the saved draft", async () => {
  const user = await open();
  fireEvent.input(screen.getByLabelText("Due date"), {
    target: { value: "2026-11-20T17:30" },
  });
  await user.click(screen.getByRole("button", { name: /Debate/ }));
  await user.click(
    screen.getByRole("button", { name: "Save draft", exact: true }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/platform/assignments",
      expect.objectContaining({
        body: expect.objectContaining({
          due_at: new Date("2026-11-20T17:30").toISOString(),
        }),
      }),
    ),
  );
});

test("SDL review requires course materials and explains the missing selection", async () => {
  const user = await open();
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  const review = screen.getByRole("button", {
    name: "Review activity",
    exact: true,
  });
  expect(review).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Publish activity" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(
      "Select course materials to review or publish an SDL lesson.",
    ),
  ).toBeInTheDocument();
  expect(api.mock.calls.some(([path]) => path.includes("/prepare-sdl"))).toBe(
    false,
  );
});
test("Publish explains a missing activity choice without a disabled button", async () => {
  const user = await open();
  await user.click(
    screen.getByRole("button", { name: "Publish activity", exact: true }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Select an activity type.",
  );
});
