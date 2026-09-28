
/**
 * A Layout owns everything between the toolbar and the bottom of the page:
 * it decides how tasks are arranged and how they are edited.
 *
 * To add one (board, timeline, cards), subclass Layout, implement mount() and
 * render(), and register it. Only `table` exists today; the switcher in the
 * toolbar appears as soon as a second layout is registered.
 *
 * The context passed in gives a layout everything it needs without reaching
 * into the app: { store, api, toast, commit(id, changes), selection }.
 */

export class Layout {
  static key = "";
  static label = "";

  constructor(context) {
    this.ctx = context;
    this.root = null;
  }

  /** Called once when the layout becomes active. Build the DOM here. */
  mount(root) {
    this.root = root;
  }

  /** Called on every state change. Must be cheap and idempotent. */
  render() {}

  /** Called when switching away. Release listeners and timers here. */
  unmount() {
    if (this.root) this.root.innerHTML = "";
    this.root = null;
  }

  get store() { return this.ctx.store; }
  get selection() { return this.ctx.selection; }
}
