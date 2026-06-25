import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";
import unusedImports from "eslint-plugin-unused-imports";

export default tseslint.config(
  // 全局忽略：构建产物、本地环境、缓存、Python 源码（不归 ESLint 管）
  {
    ignores: ["dist/**", ".kbprep/**", ".worktrees/**", "coverage/**", ".coverage", "node_modules/**", "python/**"],
  },
  {
    files: ["src/**/*.ts", "src/**/*.mjs", "scripts/**/*.mjs"],
    extends: tseslint.configs.recommended,
    plugins: { "unused-imports": unusedImports },
    rules: {
      // 交给 eslint-plugin-unused-imports：能自动删除未使用 import，并正确识别类型导入
      "@typescript-eslint/no-unused-vars": "off",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": [
        "error",
        { varsIgnorePattern: "^_", argsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
  // 关闭与 Prettier 冲突的格式化规则（必须放最后）
  prettier,
);
