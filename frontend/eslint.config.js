import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

// Flat-config ESLint for the SPA. Type-unaware recommended rules (fast, no project parse) plus the
// two classic React Hooks rules: rules-of-hooks catches real bugs (error); exhaustive-deps is a
// warning because a few effects intentionally use [] deps with refs (the modals / updater) and
// shouldn't block the gate. (The plugin's newer compiler-style rules are deliberately not enabled.)
export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  // Build/config files legitimately use vitest's triple-slash type reference.
  {
    files: ["*.config.ts"],
    rules: { "@typescript-eslint/triple-slash-reference": "off" },
  },
);
