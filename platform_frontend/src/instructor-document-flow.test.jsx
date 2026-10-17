import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuickAssignmentForm, DocumentLessonReview } from "../../adaptive-learning-app/instructor-app/src/main.jsx";
import plan from "../../adaptive-learning-app/backend/lessons/requirements.json";

const student = { id: "student-alex", display_name: "Alex", email: "alex@example.test" };
const item = {
  id: "document-lesson", title: plan.title, instructions: "Learn through examples.",
  learning_plan: plan, students: [student], configuration_issues: ["Review and approve the lesson content, questions, answer keys, and practice rubrics before publishing."],
  documents: [{ id: "doc", filename: "course.pdf", chunk_count: 14 }],
};
const response = body => ({ ok: true, status: 200, json: async () => body });

describe("document-first instructor flow", () => {
  it("starts from a URL and uses the existing draft and indexing flow", async () => {
    const user = userEvent.setup();
    const saved = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({ text: "Approved course material extracted from the article with sufficient detail.", filename: "Article" }))
      .mockResolvedValueOnce(response(plan))
      .mockResolvedValueOnce(response(item))
      .mockResolvedValueOnce(response({ id: "url-doc", chunk_count: 3 }));
    render(<QuickAssignmentForm students={[student]} onCancel={vi.fn()} onSaved={saved} />);
    await user.click(screen.getByRole("button", { name: "Use a URL" }));
    await user.type(screen.getByLabelText("Course source URL"), "https://university.edu/article");
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Review" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(item));
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      "/api/instructor/documents/url-preview", "/api/instructor/document-draft",
      "/api/instructor/assignments", "/api/instructor/assignments/document-lesson/documents/url",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).filename).toBe("Article");
  });

  it("edits quiz, content and concepts while preserving linked practice", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(item));
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Edit content, concepts & quiz" }));
    const question = screen.getAllByLabelText("Question", { exact: true })[0];
    await user.clear(question);
    await user.type(question, "An instructor-corrected quiz question?");
    const concept = screen.getAllByLabelText("Relevant concept", { exact: true })[0];
    await user.clear(concept);
    await user.type(concept, "Corrected concept");
    const material = screen.getByLabelText("Approved teaching material");
    await user.clear(material);
    await user.type(material, "The instructor's revised and approved teaching content.");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Edit content, concepts & quiz" });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(body.learning_plan.content_approved).toBe(false);
    expect(body.learning_plan.approved_material).toContain("instructor's revised");
    expect(body.learning_plan.diagnostic_quiz[0].question).toBe("An instructor-corrected quiz question?");
    expect(body.learning_plan.diagnostic_quiz[0].concept).toBe("Corrected concept");
    const original = plan.diagnostic_quiz[0];
    const asset = body.learning_plan.learning_assets.find(asset => asset.objective_id === original.objective_id);
    expect(asset.foundational.some(activity => activity.concept === "Corrected concept")).toBe(true);
    expect(asset.standard.some(activity => activity.concept === original.concept)).toBe(false);
  });

  it("removes a document after a failed review and allows selecting the same file again", async () => {
    const user = userEvent.setup();
    const preview = { text: "A complete course document with enough material to prepare a lesson.", truncated: false };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({ detail: "The AI provider returned 413." }) })
      .mockResolvedValueOnce(response(preview));
    const saved = vi.fn();
    render(<QuickAssignmentForm students={[student]} onCancel={vi.fn()} onSaved={saved} />);
    const input = screen.getByLabelText(/Course document/);
    const file = new File(["course"], "course.pdf", { type: "application/pdf" });
    await user.upload(input, file);
    await waitFor(() => expect(screen.getByRole("button", { name: "Review" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Review" }));
    await screen.findByText("The AI provider returned 413.");
    await user.click(screen.getByRole("button", { name: "Remove document" }));
    expect(input.files).toHaveLength(0);
    expect(screen.queryByText("The AI provider returned 413.")).not.toBeInTheDocument();
    expect(screen.queryByText(/course.pdf · ready/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Remove document" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(saved).not.toHaveBeenCalled();
    await user.upload(input, file);
    await waitFor(() => expect(screen.getByRole("button", { name: "Review" })).toBeEnabled());
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("requires only a document before Review", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ text: "A complete course document with enough material to prepare a lesson.", truncated: false }));
    render(<QuickAssignmentForm students={[student]} onCancel={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review" })).toBeDisabled();
    await user.upload(screen.getByLabelText(/Course document/), new File(["course"], "course.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Review" })).toBeEnabled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/instructor/documents/preview");
  });

  it("shows the complete review and publishes only when the bottom button is clicked", async () => {
    const user = userEvent.setup();
    const published = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(item));
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={published} />);
    expect(screen.getByText("14 indexed chunks")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Diagnostic quiz" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Final reflection" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Article or PDF URL" })).toHaveValue("");
    expect(screen.getByRole("button", { name: "Add URL resource" })).toBeDisabled();
    const publish = screen.getByRole("button", { name: "Publish" });
    expect(screen.getAllByRole("button").at(-1)).toBe(publish);
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(publish);
    await waitFor(() => expect(published).toHaveBeenCalledOnce());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).learning_plan.content_approved).toBe(true);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/instructor/assignments/document-lesson/publish");
  });

  it("prepares an ingested draft when Review is clicked", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(item));
    render(<DocumentLessonReview item={{ ...item, configuration_issues: ["Prepare exactly five questions."] }} onBack={vi.fn()} onPublished={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review" }));
    await screen.findByRole("button", { name: "Publish" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/instructor/assignments/document-lesson/prepare-review");
  });

  it("indexes a URL only after an explicit instructor submit", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(item));
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={vi.fn()} />);
    await user.type(screen.getByRole("textbox", { name: "Article or PDF URL" }), "https://university.edu/article");
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Add URL resource" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/instructor/assignments/document-lesson/documents/url");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ url: "https://university.edu/article" });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/instructor/assignments/document-lesson");
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Article or PDF URL" })).toHaveValue(""));
  });

  it.each([
    ["course.pdf", "application/pdf"],
    ["lecture.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    ["lecture.ppt", "application/vnd.ms-powerpoint"],
    ["course.txt", "text/plain"],
    ["course.md", "text/markdown"],
  ])("accepts %s using the existing document preview endpoint", async (filename, mime) => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ text: "Slide 1: Complete course material with sufficient detail for the lesson preview.", truncated: false }));
    render(<QuickAssignmentForm students={[student]} onCancel={vi.fn()} onSaved={vi.fn()} />);
    await user.upload(screen.getByLabelText(/Course document/), new File(["course material"], filename, { type: mime }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Review" })).toBeEnabled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/instructor/documents/preview");
    expect(fetchMock.mock.calls[0][1].body.get("file").name).toBe(filename);
  });

  it("keeps the URL and shows useful errors when indexing fails", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "Private and internal network URLs are not supported." }) });
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={vi.fn()} />);
    await user.type(screen.getByRole("textbox", { name: "Article or PDF URL" }), "http://localhost/article");
    await user.click(screen.getByRole("button", { name: "Add URL resource" }));
    expect(await screen.findByText("Private and internal network URLs are not supported.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Article or PDF URL" })).toHaveValue("http://localhost/article");
    expect(screen.getByRole("button", { name: "Add URL resource" })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("blocks repeated submits while a URL resource is indexing", async () => {
    const user = userEvent.setup();
    let finish;
    const pending = new Promise(resolve => { finish = resolve; });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => pending).mockResolvedValue(response(item));
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={vi.fn()} />);
    await user.type(screen.getByRole("textbox", { name: "Article or PDF URL" }), "https://university.edu/article");
    await user.dblClick(screen.getByRole("button", { name: "Add URL resource" }));
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(screen.getByRole("textbox", { name: "Article or PDF URL" })).toBeDisabled();
    finish(response({ id: "new-resource", chunk_count: 3 }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Article or PDF URL" })).toHaveValue(""));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("adds a draft PPTX through the existing upload endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(item));
    render(<DocumentLessonReview item={item} onBack={vi.fn()} onPublished={vi.fn()} />);
    await user.upload(screen.getByLabelText(/Add course document/), new File(["slides"], "lecture.pptx"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/instructor/assignments/document-lesson/documents");
    expect(fetchMock.mock.calls[0][1].body.get("file").name).toBe("lecture.pptx");
  });
});
