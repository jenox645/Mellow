// Theme slots: the parts of the window a theme may replace with its own component
// (a top navigation instead of the sidebar, another status bar, its own splash...).
// App logic stays shared: a slot's component gets exactly the props Classic's gets.
export const SLOT_NAMES = ['Sidebar', 'TopBar', 'StatusBar', 'LoadingScreen', 'PageFrame'];

// Pages a theme may draw its own way. The page's logic stays shared: a view gets what the
// page's hook returns (useFeedPage, useVaultPage) and calls its handlers, never the API.
export const PAGE_NAMES = ['feed', 'vault'];

// The components for `theme`: its own where it registered one, Classic's for the rest;
// `pages` holds the page views the same way
export function resolveSlots(defaults, registry, theme) {
  const own = (registry && registry[theme]) || {};
  const slots = {};
  for (const name of SLOT_NAMES) slots[name] = own[name] || defaults[name];
  const ownPages = own.pages || {}, defaultPages = defaults.pages || {};
  slots.pages = {};
  for (const name of PAGE_NAMES) slots.pages[name] = ownPages[name] || defaultPages[name];
  return slots;
}

// What's wrong with a registry: unknown themes, slot or page names (a typo would silently fall back)
export function registryProblems(registry, themeIds) {
  const problems = [];
  for (const [theme, own] of Object.entries(registry || {})) {
    if (!themeIds.includes(theme)) problems.push(`unknown theme "${theme}"`);
    for (const name of Object.keys(own || {})) {
      if (name === 'pages') {
        for (const page of Object.keys(own.pages || {})) {
          if (!PAGE_NAMES.includes(page)) problems.push(`${theme}: unknown page "${page}"`);
        }
      } else if (!SLOT_NAMES.includes(name)) problems.push(`${theme}: unknown slot "${name}"`);
    }
  }
  return problems;
}
