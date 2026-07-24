import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const rootDirectory = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: "./src/test-setup.ts" },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: resolve(rootDirectory, "popup.html"),
        background: resolve(rootDirectory, "src/background.ts")
      },
      output: { entryFileNames: (chunk) => chunk.name === "background" ? "background.js" : "assets/[name]-[hash].js" }
    }
  }
});
