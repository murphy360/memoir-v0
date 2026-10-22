// From murphy360/standards templates/eslint.config.mjs, plus Next.js's own rules. The complexity
// limits come from node-lint, not here. Change a rule only with a reason written beside it.
import js from "@eslint/js";
import nextPlugin from "@next/eslint-plugin-next";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: [".next/", "node_modules/", "next-env.d.ts", ".standards/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  // v7's recommended set adds the React Compiler rules (set-state-in-effect and others), which flag
  // effects this app relies on. Keep the two classic rules until the effects are reworked.
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
      // Photos and audio come from the API with their own URLs; next/image adds nothing here.
      "@next/next/no-img-element": "off",
    },
  },
);
