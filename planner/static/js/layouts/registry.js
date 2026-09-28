export class LayoutRegistry {
  constructor(fallbackKey = "table") {
    this.classes = new Map();
    this.fallbackKey = fallbackKey;
    this.active = null;
  }

  register(LayoutClass) {
    this.classes.set(LayoutClass.key, LayoutClass);
    return this;
  }

  list() {
    return Array.from(this.classes.values()).map((C) => ({ key: C.key, label: C.label }));
  }

  /** Swap the active layout, unmounting the previous one first. */
  activate(key, root, context) {
    const LayoutClass = this.classes.get(key) || this.classes.get(this.fallbackKey);
    if (!LayoutClass) return null;
    if (this.active && this.active.constructor === LayoutClass) return this.active;
    if (this.active) this.active.unmount();
    this.active = new LayoutClass(context);
    this.active.mount(root);
    return this.active;
  }
}
