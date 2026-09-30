// ESLint flat config (v9+) — spec rules preserved from .eslintrc.json

// Minimal stand-in for eslint-plugin-react's jsx-uses-vars: marks components
// referenced in JSX as used so no-unused-vars doesn't false-positive on them.
const jsxUsesVars = {
  rules: {
    'jsx-uses-vars': {
      create(context) {
        return {
          JSXOpeningElement(node) {
            let name = node.name;
            while (name.type === 'JSXMemberExpression') name = name.object;
            if (name.type === 'JSXIdentifier') {
              context.sourceCode.markVariableAsUsed(name.name, node);
            }
          },
        };
      },
    },
  },
};

export default [
  {
    files: ['gui/**/*.jsx', 'gui/**/*.js'],
    plugins: { 'jsx-vars': jsxUsesVars },
    languageOptions: {
      ecmaVersion: 2021,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        EventSource: 'readonly',
        FileReader: 'readonly',
        ResizeObserver: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        confirm: 'readonly',
        React: 'readonly',
        ReactDOM: 'readonly',
        URLSearchParams: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        FormData: 'readonly',
        navigator: 'readonly',
        globalThis: 'readonly',
        Notification: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      'no-unused-vars': ['warn', { args: 'none' }],
      'no-undef': 'error',
      'jsx-vars/jsx-uses-vars': 'error',
    },
  },
];
