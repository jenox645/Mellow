// ESLint flat config (v9+) — spec rules preserved from .eslintrc.json
export default [
  {
    files: ['gui/**/*.jsx', 'gui/**/*.js'],
    languageOptions: {
      ecmaVersion: 2021,
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
        navigator: 'readonly',
        globalThis: 'readonly',
        MASCOT_DJ: 'readonly',
        MASCOT_VIBING: 'readonly',
        MASCOT_CHILLING: 'readonly',
        MASCOT_FRUSTRATED: 'readonly',
        MASCOT_TIRED: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      'no-unused-vars': 'warn',
      'no-undef': 'error',
    },
  },
];
