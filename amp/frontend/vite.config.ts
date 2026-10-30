import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server runs on 1420; the backend runs on 8000.
// In production (Tauri), the frontend is served from tauri://localhost.
const host = process.env.TAURI_DEV_HOST || "localhost";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host,
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "esnext",
    minify: !process.env.TAURI_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});
