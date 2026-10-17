import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../adaptive-learning-app/student-app/src/main";
import { configureStudentTransport } from "../../adaptive-learning-app/student-app/src/api";
import { studentTransport, loadSignedInStudent } from "./self-directed-api";

configureStudentTransport(studentTransport);
const assignmentId = new URLSearchParams(window.location.search).get("assignment");
createRoot(document.getElementById("root")).render(<App loadUsers={loadSignedInStudent} initialAssignmentId={assignmentId} />);
