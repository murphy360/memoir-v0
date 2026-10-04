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
  reactHooks.configs["recommended-latest"],
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
