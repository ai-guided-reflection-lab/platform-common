import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./main";

const root = createRoot(document.getElementById("root"));
if (import.meta.env.VITE_LAB_MODE === "true") {
  import("./LabApp").then(({ default: LabApp }) => root.render(<LabApp />));
} else root.render(<App />);
