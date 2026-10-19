import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to a locally exposed registry; in Docker, nginx does the same.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
});
