import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import dts from "vite-plugin-dts";

/**
 * Emit the stylesheet as a standalone asset.
 *
 * `src/index.ts` deliberately does not import the CSS — that would make every
 * consumer pay for it whether or not they use the styled components. Emitting
 * it here keeps it opt-in behind the `opencad-viewport/styles.css` export.
 */
function emitStylesheet(): Plugin {
  return {
    name: "opencad-emit-stylesheet",
    buildStart() {
      this.emitFile({
        type: "asset",
        fileName: "opencad-viewport.css",
        source: readFileSync(resolve(__dirname, "src/styles.css"), "utf8"),
      });
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    dts({ include: ["src"], exclude: ["src/**/*.test.ts", "src/**/*.test.tsx"] }),
    emitStylesheet(),
  ],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      formats: ["es"],
      fileName: () => "index.js",
    },
    rollupOptions: {
      // Peers stay external so consumers resolve a single copy — bundling
      // react or three causes duplicate-instance bugs (invalid hook calls,
      // failing `instanceof` checks). Regular dependencies are external too;
      // the package manager installs them from our dependency list.
      external: [
        "axios",
        "react",
        "react/jsx-runtime",
        "react-dom",
        "react-dom/client",
        "three",
        /^three\//,
        "@react-three/fiber",
        "@react-three/drei",
      ],
    },
    sourcemap: true,
    emptyOutDir: true,
  },
});
