import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { input: { app: "index.html", gamePreview: "game-preview.html" } },
  },
  server: {
    port: 5188,
    strictPort: true,
    watch: { ignored: ["**/.venv/**", "**/.data/**", "**/backoffice/**"] },
    fs: { deny: ["**/.env*", "**/.git/**", "**/.data/**", "**/.venv/**", "**/design/**", "**/*.{crt,pem,key}"] },
    proxy: {
      "/admin": { target: "http://127.0.0.1:3001", changeOrigin: false },
      "/static": { target: "http://127.0.0.1:3001", changeOrigin: false },
      "/game-assets": { target: "http://127.0.0.1:3001", changeOrigin: false },
      "/api": {
        target: "http://127.0.0.1:3001",
        changeOrigin: false,
        xfwd: false,
      },
    },
  },
  preview: { proxy: { "/api": "http://127.0.0.1:3001" } },
});
