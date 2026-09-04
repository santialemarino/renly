import js from '@eslint/js';
import eslintConfigPrettier from 'eslint-config-prettier';
import onlyWarn from 'eslint-plugin-only-warn';
import turboPlugin from 'eslint-plugin-turbo';
import tseslint from 'typescript-eslint';

/*
 * The `eslint-plugin-react` rules that every React config here turns off, in one place because both
 * of them (`react-internal` and `next`) spread the same plugin preset and would otherwise each carry
 * their own copy — two things that can come to disagree about the same question.
 *
 * `react-in-jsx-scope` is obsolete under the automatic JSX runtime. `prop-types` is a
 * legacy-PropTypes rule and this is a TypeScript codebase: every component's props are typed at the
 * definition, and tsc already checks them. The plugin cannot always see through that — an inline
 * render prop handed to a library (react-day-picker's `components`) reads to it as an untyped
 * component — so it reports false positives that no amount of typing removes.
 */
export const reactTypeScriptRules = {
  'react/react-in-jsx-scope': 'off',
  'react/prop-types': 'off',
};

/**
 * A shared ESLint configuration for the repository.
 *
 * @type {import("eslint").Linter.Config[]}
 * */
export const config = [
  js.configs.recommended,
  eslintConfigPrettier,
  ...tseslint.configs.recommended,
  {
    plugins: {
      turbo: turboPlugin,
    },
    rules: {
      'turbo/no-undeclared-env-vars': 'warn',
    },
  },
  {
    plugins: {
      onlyWarn,
    },
  },
  {
    ignores: ['dist/**'],
  },
];
