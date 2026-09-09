import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Артефакты Playwright. HTML-отчёт — это ~500 КБ инлайн-JS в одном
    // файле: без этих правил `npm run lint` даёт сотни ошибок в сгенерированном
    // коде и заглушает реальные предупреждения по исходникам.
    "playwright-report/**",
    "test-results/**",
    "blob-report/**",
  ]),
  {
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react/no-unescaped-entities": "warn",
      "@next/next/no-html-link-for-pages": "warn",
      "@typescript-eslint/no-unused-vars": "warn",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
]);

export default eslintConfig;
