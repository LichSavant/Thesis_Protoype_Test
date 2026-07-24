import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const rootDirectory = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: false,
    copyPublicDir: false,
    lib: {
      entry: resolve(rootDirectory, "src/content.ts"),
      name: "SentinelGmailContent",
      formats: ["iife"],
      fileName: () => "content.js"
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: "content.js"
      }
    }
  }
});
