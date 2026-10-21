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
    if (path === "/courses/course-1/documents")
      return { files: courseFiles };
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
    screen.queryByLabelText("Opening question or prompt"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Messages required before completion"),
  ).not.toBeInTheDocument();
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

test("a PDF upload appears in the course library and is selected", async () => {
  const user = await open();
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["%PDF-1.4"], "New lesson.pdf", { type: "application/pdf" }),
  );
  expect(await screen.findByRole("checkbox", { name: /New lesson.pdf/ })).toBeChecked();
  expect(screen.getByText("Documents uploaded and ready to select.")).toBeInTheDocument();
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
  expect(await screen.findByRole("alert")).toHaveTextContent("embedding provider");
});

test("a completed request is not reported as success when the PDF is absent from the refreshed library", async () => {
  const user = await open();
  await screen.findByRole("checkbox", { name: /Requirements.pdf/ });
  const originalApi = api.getMockImplementation();
  api.mockImplementation((path, options) =>
    path === "/platform/courses/course-1/documents/upload" && options?.method === "POST"
      ? Promise.resolve({ files: [{ file_id: "missing", document_id: "d2" }] })
      : originalApi(path, options),
  );
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["%PDF-1.4"], "New lesson.pdf", { type: "application/pdf" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("not in this course's library");
  expect(screen.queryByText("Documents uploaded and ready to select.")).not.toBeInTheDocument();
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
  expect(api).toHaveBeenCalledWith(
    "/courses/course-1/documents/f1",
    { method: "DELETE" },
  );
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

test("SDL selection immediately exposes sub-questions without a course picker", async () => {
  const user = await open();
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  expect(screen.getByLabelText("Sub-questions")).toBeInTheDocument();
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
  expect(screen.getByLabelText("Sub-questions")).toBeInTheDocument();
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

test("Publish stays active and explains missing course materials", async () => {
  const user = await open();
  await user.click(
    screen.getByRole("button", { name: /Self Directed Learning/ }),
  );
  const publish = screen.getByRole("button", {
    name: "Publish activity",
    exact: true,
  });
  expect(publish).toBeEnabled();
  await user.click(publish);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Select at least one indexed course document",
  );
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
