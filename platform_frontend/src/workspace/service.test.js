import { beforeEach, expect, it, vi } from "vitest";
import {
  activityView,
  assignmentBody,
  loadWorkspace,
  saveActivity,
  uploadDocuments,
} from "./service";
import { api } from "../api";
vi.mock("../api", () => ({
  api: vi.fn(),
  session: () => ({ access_token: "signed-session" }),
}));
beforeEach(() => vi.clearAllMocks());
const draft = {
  title: "Explain design tradeoffs",
  instructions: "Defend your reasoning",
  prompt: "What tradeoff matters?",
  minimumMessages: 3,
  due: "2026-10-20",
  files: [{ id: "file-1", document_id: "doc-1" }],
};
it("maps every chat configuration without sending UI fields or file blobs", () => {
  expect(
    assignmentBody("course-1", { ...draft, tool: "socratic" }).config,
  ).toEqual({
    document_ids: ["doc-1"],
    prompt: draft.prompt,
    minimum_messages: 3,
  });
  expect(assignmentBody("course-1", { ...draft, tool: "dialectic" }).tool).toBe(
    "debate",
  );
  const reflection = {
    module_type: "milestone_based",
    milestone_prompt: "Reflect",
    historical_data: "name,challenge,solution",
  };
  expect(
    assignmentBody("course-1", { ...draft, tool: "reflections", reflection })
      .config,
  ).toEqual({ ...reflection, document_ids: ["doc-1"] });
  expect(
    assignmentBody("course-1", {
      ...draft,
      tool: "sdl",
      learningPlan: { title: "Reviewed lesson" },
    }).config.learning_plan.title,
  ).toBe("Reviewed lesson");
  expect(assignmentBody("course-1", { ...draft, tool: "sdl" }).due_at).toMatch(
    /Z$/,
  );
});
it("publishes only after saving and keeps the saved server identity", async () => {
  api
    .mockResolvedValueOnce({ id: "assignment-1" })
    .mockResolvedValueOnce({ status: "published" });
  await saveActivity("course-1", { ...draft, tool: "dialectic" }, "published");
  expect(api.mock.calls[0][0]).toBe("/platform/assignments");
  expect(api.mock.calls[1]).toEqual([
    "/platform/assignments/assignment-1/publish",
    { method: "POST" },
  ]);
});
it("does not publish when saving fails", async () => {
  api.mockRejectedValueOnce(new Error("Permission denied"));
  await expect(
    saveActivity("course-1", { ...draft, tool: "dialectic" }, "published"),
  ).rejects.toThrow("Permission denied");
  expect(api).toHaveBeenCalledTimes(1);
});
it("uploads actual files to the common pipeline and retains chunk document identities", async () => {
  api.mockResolvedValue({
    files: [
      {
        file_id: "file-1",
        document_id: "doc-1",
        filename: "Reading.txt",
        file_size: 30,
      },
    ],
  });
  const file = new File(["A course reading"], "Reading.txt", {
    type: "text/plain",
  });
  const files = await uploadDocuments([file], "course-1");
  expect(api.mock.calls[0][0]).toBe(
    "/platform/courses/course-1/documents/upload",
  );
  expect(api.mock.calls[0][1].body.getAll("files")).toEqual([file]);
  expect(files[0]).toMatchObject({
    id: "file-1",
    document_id: "doc-1",
    name: "Reading.txt",
    size: 30,
  });
});
it("loads courses, assignments, students, and files from authenticated APIs", async () => {
  api.mockImplementation(async (path) => {
    if (path === "/platform/courses")
      return {
        courses: [
          {
            course_id: "course-1",
            course_code: "ITSC 3155",
            title: "Engineering",
            join_code: "ABCD1234",
          },
        ],
      };
    if (path === "/platform/assignments")
      return [
        {
          id: "assignment-1",
          course_id: "course-1",
          tool: "socratic",
          config: { document_ids: ["doc-1"] },
          due_at: "2026-10-20T16:00:00Z",
        },
      ];
    if (path.endsWith("/documents"))
      return {
        files: [
          {
            file_id: "file-1",
            document_id: "doc-1",
            filename: "Reading.txt",
            file_size: 20,
          },
        ],
      };
    return [{ display_name: "A Student", membership_id: "membership-1" }];
  });
  const [course] = await loadWorkspace(true);
  expect(course).toMatchObject({
    id: "course-1",
    joinCode: "ABCD1234",
    students: [{ name: "A Student" }],
  });
  expect(course.activities[0]).toMatchObject({
    files: [{ document_id: "doc-1" }],
    due: "2026-10-20",
  });
});
it("loads every existing chat config back into an editable draft", () => {
  const activity = activityView(
    {
      id: "a",
      tool: "self-directed-learning",
      config: { document_ids: ["d"], learning_plan: { title: "Saved plan" } },
    },
    [{ document_id: "d" }],
  );
  expect(activity).toMatchObject({
    id: "a",
    tool: "sdl",
    learningPlan: { title: "Saved plan" },
    files: [{ document_id: "d" }],
  });
});
