// API contracts and engine field mapping live here, away from presentation.
import { api, session } from "../api";

export const toolId = (value) =>
  ({ sdl: "self-directed-learning", dialectic: "debate" })[value] || value;
export const uiTool = (value) =>
  ({ "self-directed-learning": "sdl", debate: "dialectic" })[value] || value;
export const fileView = (f) => ({
  ...f,
  id: f.file_id || f.id,
  name: f.filename || f.name,
  size: f.file_size ?? f.size,
  storageKey: f.file_id || f.id,
});
const localDate = (iso) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.valueOf())) return "";
  const part = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${part(date.getMonth() + 1)}-${part(date.getDate())}`;
};
export function activityView(a, documents = []) {
  const config = a.config || {};
  return {
    ...a,
    tool: uiTool(a.tool),
    due: localDate(a.due_at),
    files: documents.filter((f) =>
      (config.document_ids || []).includes(f.document_id),
    ),
    prompt:
      config.prompt ||
      config.scenario ||
      config.milestone_prompt ||
      (config.sub_topics || config.required_topics || []).join("\n"),
    reflectionType: config.module_type || "topic_based",
    style: config.probing_style === "socratic" ? "challenging" : "supportive",
    minimumMessages: config.minimum_messages || 3,
    reflection: config,
    learningPlan: config.learning_plan,
    students: a.students || [],
    reviewed: false,
  };
}
export function assignmentBody(courseId, draft) {
  const tool = toolId(draft.tool);
  const document_ids = draft.files.map((f) => f.document_id).filter(Boolean);
  let config;
  if (tool === "socratic")
    config = {
      document_ids,
      prompt: draft.prompt,
      minimum_messages: draft.minimumMessages,
    };
  else if (tool === "debate")
    config = {
      scenario:
        draft.prompt?.trim() ||
        `${draft.title}\n${draft.instructions || "Discuss this topic and defend your position."}`,
      opening_prompt: "",
      minimum_messages: draft.minimumMessages || 3,
    };
  else if (tool === "reflections") {
    config = { ...draft.reflection, document_ids };
    if (draft.reflectionType) {
      const topics = (draft.prompt || "")
        .split(/\n/)
        .map((value) => value.trim())
        .filter(Boolean);
      config = {
        ...config,
        module_type: draft.reflectionType,
        probing_style:
          draft.style === "challenging" ? "socratic" : "supportive",
        ...(draft.reflectionType === "milestone_based"
          ? { milestone_prompt: draft.prompt || "" }
          : { required_topics: topics, sub_topics: topics }),
      };
    }
  } else
    config = {
      document_ids,
      prompt: draft.prompt,
      learning_plan: draft.learningPlan || {},
    };
  return {
    course_id: courseId,
    title: draft.title,
    instructions: draft.instructions,
    tool,
    due_at: draft.due
      ? new Date(
          draft.due.length === 10 ? draft.due + "T23:59:00" : draft.due,
        ).toISOString()
      : null,
    audience: "course",
    config,
  };
}
export async function loadWorkspace(professor) {
  const [{ courses }, assignments] = await Promise.all([
    api("/platform/courses"),
    api("/platform/assignments"),
  ]);
  return Promise.all(
    courses.map(async (c) => {
      const id = c.course_id;
      const [{ files }, students] = await Promise.all([
        api(`/platform/courses/${id}/documents`),
        professor
          ? api(`/instructor/enrolled-students?course_id=${id}`)
          : Promise.resolve([]),
      ]);
      const documents = files.map(fileView);
      return {
        ...c,
        id,
        code: c.course_code,
        joinCode: c.join_code,
        joined: !professor,
        documents,
        students: students.map((s) => ({
          ...s,
          name: s.display_name || s.username,
        })),
        activities: assignments
          .filter((a) => a.course_id === id)
          .map((a) => activityView(a, documents)),
      };
    }),
  );
}
export async function saveActivity(
  courseId,
  draft,
  status,
  onSaved = () => {},
) {
  const saved = await api(
    `/platform/assignments${draft.id ? `/${draft.id}` : ""}`,
    {
      method: draft.id ? "PUT" : "POST",
      body: assignmentBody(courseId, draft),
    },
  );
  onSaved(saved);
  if (status === "published")
    await api(`/platform/assignments/${saved.id}/publish`, { method: "POST" });
  return saved;
}
export async function uploadDocuments(files, courseId) {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  const result = await api(`/platform/courses/${courseId}/documents/upload`, {
    method: "POST",
    body,
  });
  return result.files.map(fileView);
}
export async function downloadDocument(file) {
  const response = await fetch(
    `/api/platform/courses/${file.courseId}/documents/${file.id}/download`,
    { headers: { Authorization: `Bearer ${session()?.access_token || ""}` } },
  );
  if (!response.ok)
    throw new Error("The document could not be downloaded. Please retry.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
