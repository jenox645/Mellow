// Which theme replaces which part of the window (gui/lib/slots.js). A theme that brings its own
// components keeps them in gui/themes/<id>/ and adds one line to THEME_SLOTS, e.g.
//   import { TacticalSidebar } from './tactical/chrome.jsx';
//   tactical: { Sidebar: TacticalSidebar },
// A theme can draw a page its own way too: `pages: { feed: TacticalFeedView }` (any of
// PAGE_NAMES in lib/slots.js). The view gets what the page's hook returns (useFeedPage in
// pages/feed-logic.js, useQueuePage in pages/queue-logic.js, and so on for vault, analytics,
// signal and config); Classic's views (ClassicFeedView, ClassicQueueView…) show how.
import { Sidebar, TopBar, StatusBar } from '../components/chrome.jsx';
import { LoadingScreen } from '../components/loading.jsx';
import { ClassicFeedView } from '../pages/feed.jsx';
import { ClassicQueueView } from '../pages/queue.jsx';
import { ClassicVaultView } from '../pages/vault.jsx';
import { ClassicAnalyticsView } from '../pages/analytics.jsx';
import { ClassicSignalView } from '../pages/signal.jsx';
import { ClassicConfigView } from '../pages/config.jsx';
import { THEMES } from '../lib/constants.js';
import { resolveSlots, registryProblems } from '../lib/slots.js';
import { TacticalSidebar, TacticalTopBar, TacticalStatusBar, TacticalPageFrame } from './tactical/chrome.jsx';
import { TacticalLoadingScreen } from './tactical/splash.jsx';

// Classic's frame around the current page: nothing (a theme can add a header, rails, a backdrop)
function PageFrame({ children }) {
  return children;
}

export const DEFAULT_SLOTS = {
  Sidebar, TopBar, StatusBar, LoadingScreen, PageFrame,
  pages: {
    feed: ClassicFeedView, queue: ClassicQueueView, vault: ClassicVaultView, analytics: ClassicAnalyticsView,
    signal: ClassicSignalView, config: ClassicConfigView,
  },
};

export const THEME_SLOTS = {
  tactical: {
    Sidebar: TacticalSidebar, TopBar: TacticalTopBar, StatusBar: TacticalStatusBar,
    LoadingScreen: TacticalLoadingScreen, PageFrame: TacticalPageFrame,
  },
};

const problems = registryProblems(THEME_SLOTS, THEMES.map(t => t.id));
if (problems.length) console.error('Theme slots: ' + problems.join('; '));

export const themeSlots = theme => resolveSlots(DEFAULT_SLOTS, THEME_SLOTS, theme);
