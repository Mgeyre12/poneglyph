import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    watch: {
      // macOS fsevents on ~/Desktop emits spurious change events
      // (Spotlight + backup indexing) that force Vite into HMR
      // reload storms. Polling is slower to detect real edits
      // (500ms lag) but ignores the noise entirely.
      usePolling: true,
      interval: 500,
      ignored: ["**/node_modules/**", "**/dist/**", "**/.git/**"],
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
}));
