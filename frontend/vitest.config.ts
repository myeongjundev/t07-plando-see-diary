import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Kept out of vite.config.ts so the build config stays about the build. The
// dev-server proxy there is irrelevant here -- these tests never reach a
// network, they replace fetch.
export default defineConfig({
  plugins: [react()],
  test: {
    // Testing Library registers its own afterEach cleanup only when the test
    // globals exist. Without it every render stays in the document and the next
    // test finds two of everything.
    globals: true,
    environment: "jsdom",
    // https, because the cookie the client reads is a `__Host-` one and jsdom
    // enforces the prefix: over http it refuses to store it, exactly as a
    // browser would, and the CSRF test would be asserting against nothing.
    environmentOptions: { jsdom: { url: "https://localhost/" } },
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
