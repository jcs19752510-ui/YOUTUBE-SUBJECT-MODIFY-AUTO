import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'error',
      // CSP(인라인 스타일 금지)와 XSS 방어: 보안 설계 SEC-D09, SEC-D17, F-05
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML 금지(F-05).',
        },
        {
          selector: "JSXAttribute[name.name='style']",
          message: '인라인 style 속성 금지(CSP). CSS 클래스를 쓰세요.',
        },
        {
          selector: "MemberExpression[property.name='innerHTML']",
          message: 'innerHTML 금지(F-05).',
        },
      ],
      'no-restricted-globals': ['error', 'localStorage', 'sessionStorage'],
    },
  },
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    rules: { 'no-restricted-globals': 'off' },
  },
  {
    files: ['dev/**/*.mjs', 'vite.config.ts', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },
);
