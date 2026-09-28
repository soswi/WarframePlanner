export class Store {
  constructor() {
    this.tasks = [];
    this.definitions = {};
    this.settings = {};
    this.recurrence = [];
    this.layouts = [];
    this.themes = [];
    this.stats = { total: 0, counts: {}, done: 0, completion_rate: 0 };
    this.listeners = [];
  }

  subscribe(listener) { this.listeners.push(listener); }

  apply(snapshot) {
    Object.assign(this, snapshot);
    this.listeners.forEach((listener) => listener(this));
  }

  colorFor(kind, value) {
    const entry = (this.definitions[kind] || []).find((item) => item.value === value);
    return entry ? entry.color : null;
  }

  valuesFor(kind) {
    return (this.definitions[kind] || []).map((item) => item.value);
  }

  doneStatus() { return this.settings.done_status || "Done"; }

  /** Status pinned to the front of every list, or "" when disabled. */
  highlightStatus() { return (this.settings.highlight_status || "").trim(); }

  /** Colour to accent a pinned task with, taken from the status definition. */
  highlightColor() { return this.colorFor("status", this.highlightStatus()); }
}
