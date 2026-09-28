export class SelectionModel {
  constructor(onChange) {
    this.ids = new Set();
    this.onChange = onChange || (() => {});
  }

  toggle(id, on) {
    if (on) this.ids.add(id); else this.ids.delete(id);
    this.onChange(this);
  }

  replace(ids) {
    this.ids = new Set(ids);
    this.onChange(this);
  }

  clear() {
    this.ids.clear();
    this.onChange(this);
  }

  has(id) { return this.ids.has(id); }
  get size() { return this.ids.size; }
  toArray() { return Array.from(this.ids); }
}

/**
 * A colour dot that opens a themed menu, shared by the table and the board.
 *
 * Not a native <select>: an <option> cannot pair a coloured dot with text in
 * a different colour, and the popup itself is drawn by the operating system
 * and cannot be themed.
 */
