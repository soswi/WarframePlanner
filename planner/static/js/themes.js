/**
 * Themes are code-defined palettes. Users pick one; they cannot author new ones.
 * The backend ships the token map in /api/state, so adding a theme server-side
 * requires no change here. This registry also holds a local fallback so the page
 * still renders if the backend list is unavailable.
 */
export class Theme {
  constructor({ key, label, description, tokens }) {
    this.key = key;
    this.label = label || key;
    this.description = description || "";
    this.tokens = tokens || {};
  }

  /** Write the palette onto :root as CSS custom properties. */
  apply(root = document.documentElement) {
    Object.entries(this.tokens).forEach(([name, value]) => {
      root.style.setProperty(`--${name}`, value);
    });
    root.dataset.theme = this.key;
  }
}

export class ThemeRegistry {
  constructor(fallbackKey = "zariman") {
    this.themes = new Map();
    this.fallbackKey = fallbackKey;
    this.activeKey = null;
  }

  register(theme) {
    this.themes.set(theme.key, theme);
    return this;
  }

  /** Replace the catalogue with the descriptors returned by the backend. */
  load(descriptors) {
    if (!Array.isArray(descriptors) || descriptors.length === 0) return this;
    this.themes.clear();
    descriptors.forEach((descriptor) => this.register(new Theme(descriptor)));
    return this;
  }

  get(key) {
    return this.themes.get(key) || this.themes.get(this.fallbackKey) || null;
  }

  list() {
    return Array.from(this.themes.values());
  }

  apply(key, root = document.documentElement) {
    const theme = this.get(key);
    if (!theme) return null;
    theme.apply(root);
    this.activeKey = theme.key;
    return theme;
  }
}

// Local fallback used only before /api/state arrives; the backend is the
// source of truth for the full catalogue.
export const BUILTIN_THEMES = [
  new Theme({
    key: "zariman",
    label: "Zariman",
    tokens: {
      "bg": "#1a1a19", "surface": "#232322", "surface-2": "#2b2b29",
      "surface-3": "#353532", "border": "#3e3e3a", "text": "#f0efe9",
      "text-dim": "#a8a79e", "text-faint": "#79786f", "accent": "#4fb3a3",
      "accent-ink": "#07231f", "danger": "#df7c6d", "ok": "#63b98f",
      "warn": "#d3a65c", "row-alt": "#1f1f1e", "row-hover": "#2b2b29",
      "row-selected": "#2c3a37", "head-bg": "#1f1f1e",
    },
  }),
];
