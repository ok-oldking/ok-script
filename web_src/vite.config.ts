import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  root: __dirname,
  base: command === "build" ? "/static/" : "/",
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../ok/ui/web/static"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunk-[name].js",
        assetFileNames: "[name][extname]",
        manualChunks(id) {
          if (id.includes("node_modules/@fluentui")) return "fluent";
          if (id.includes("node_modules/react")) return "react";
          return undefined;
        }
      }
    }
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        ws: true
      }
    }
  }
}));
