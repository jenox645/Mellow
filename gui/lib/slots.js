// Theme slots: the parts of the window a theme may replace with its own component
// (a top navigation instead of the sidebar, another status bar, its own splash...).
// App logic stays shared: a slot's component gets exactly the props Classic's gets.
export const SLOT_NAMES = ['Sidebar', 'TopBar', 'StatusBar', 'LoadingScreen', 'PageFrame'];

// The components for `theme`: its own where it registered one, Classic's for the rest
export function resolveSlots(defaults, registry, theme) {
  const own = (registry && registry[theme]) || {};
  const slots = {};
  for (const name of SLOT_NAMES) slots[name] = own[name] || defaults[name];
  return slots;
}

// What's wrong with a registry: unknown themes or slot names (a typo would silently fall back)
export function registryProblems(registry, themeIds) {
  const problems = [];
  for (const [theme, own] of Object.entries(registry || {})) {
    if (!themeIds.includes(theme)) problems.push(`unknown theme "${theme}"`);
    for (const name of Object.keys(own || {})) {
      if (!SLOT_NAMES.includes(name)) problems.push(`${theme}: unknown slot "${name}"`);
    }
  }
  return problems;
}
