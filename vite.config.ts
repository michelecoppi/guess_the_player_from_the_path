import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [tailwindcss()],
  base: "/app/v2/",
  build: {
    outDir: "webapp/dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "webapp/src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/app/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
