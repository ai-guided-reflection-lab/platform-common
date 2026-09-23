import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/platform/",
  resolve: { dedupe: ["react", "react-dom"] },
  build: { rollupOptions: { input: { main: "index.html", reflections: "reflections.html" } } },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.js"] },
});
