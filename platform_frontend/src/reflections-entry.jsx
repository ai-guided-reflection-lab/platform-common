import React from "react";
import { createRoot } from "react-dom/client";
import ReflectionAssignment from "./ReflectionAssignment";
import "../../reflections-app/frontend/src/index.css";

const assignmentId = new URLSearchParams(window.location.search).get("assignment");
createRoot(document.getElementById("root")).render(
  <ReflectionAssignment assignmentId={assignmentId} />,
);
