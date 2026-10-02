import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [tailwindcss()],
  base: "/app/",
  build: {
    outDir: "webapp/dist",
    emptyOutDir: true,
    // Maps are generated (to decode production stack traces locally, #180) but the bundles do
    // not reference them and they are never served or shipped (#181).
    sourcemap: "hidden",
    // Each flag is ~600 bytes, under Vite's inline limit: inlined, all 105 would sit in the main
    // bundle (+64 kB gzip) for the 5-10 a career shows. As files they load only when shown.
    assetsInlineLimit: (file: string) => (file.includes("/assets/flags/") ? false : undefined),
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
