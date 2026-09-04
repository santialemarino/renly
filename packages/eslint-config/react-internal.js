import pluginReact from 'eslint-plugin-react';
import pluginReactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

import { config as baseConfig } from './base.js';

/**
 * A custom ESLint configuration for internal React libraries.
 *
 * @type {import("eslint").Linter.Config[]}
 * */
export const config = [
  ...baseConfig,
  pluginReact.configs.flat.recommended,
  {
    languageOptions: {
      ...pluginReact.configs.flat.recommended.languageOptions,
      globals: {
        ...globals.serviceworker,
        ...globals.browser,
      },
    },
  },
  {
    plugins: {
      'react-hooks': pluginReactHooks,
    },
    settings: { react: { version: 'detect' } },
    rules: {
      ...pluginReactHooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      /*
       * `react/prop-types` is a legacy-PropTypes rule and this is a TypeScript codebase: every
       * component's props are typed at the definition. The plugin cannot always see through them —
       * an inline render prop handed to a library (react-day-picker's `components`) reads as an
       * untyped component — so it reports false positives that no amount of typing removes, on code
       * whose types tsc is already checking.
       */
      'react/prop-types': 'off',
    },
  },
];
