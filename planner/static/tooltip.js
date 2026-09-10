"use strict";

// Wrapped in an IIFE: these files load as classic scripts and share one global
// lexical scope, so top-level class declarations would collide with the
// destructuring imports in app.js. Only window.PlannerTooltip escapes.
(function () {

  const SHOW_DELAY_MS = 260;
  const EDGE_MARGIN = 10;
  const CURSOR_OFFSET = 14;

  /**
   * Measures rendered text width without touching the DOM, using the element's
   * own computed font. Used to decide whether a single-line value is clipped.
   */
  class TextMeasurer {
    constructor() {
      this.context = document.createElement("canvas").getContext("2d");
      this.cache = new Map();
    }

    width(text, font) {
      const key = `${font}\u0000${text}`;
      let cached = this.cache.get(key);
      if (cached === undefined) {
        this.context.font = font;
        cached = this.context.measureText(text).width;
        if (this.cache.size > 4000) this.cache.clear();
        this.cache.set(key, cached);
      }
      return cached;
    }
  }

  /**
   * One tooltip element reused for the whole page, driven by event delegation.
   *
   * Opt in from any markup with data-tooltip="full text". By default the tooltip
   * only appears when the value does not fit its cell; add data-tooltip-always
   * to show it regardless (useful for supplementary text that is never rendered
   * inline, such as the list of blocking dependencies).
   */
  class TooltipController {
    constructor({ formatters = {} } = {}) {
      this.element = null;
      this.target = null;
      this.timer = null;
      this.measurer = new TextMeasurer();
      this.pointer = { x: 0, y: 0 };
      // Map of data-tooltip-format value -> (text) => html string.
      this.formatters = formatters;
    }

    attach(root = document.body) {
      this.element = document.createElement("div");
      this.element.className = "tooltip-bubble";
      this.element.setAttribute("role", "tooltip");
      this.element.hidden = true;
      root.appendChild(this.element);

      document.addEventListener("mouseover", (event) => this.onMouseOver(event));
      document.addEventListener("mouseout", (event) => this.onMouseOut(event));
      document.addEventListener("mousemove", (event) => this.onMouseMove(event));
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") this.hide();
      });
      // Any scroll or resize invalidates the anchor position; cheapest fix is to close.
      window.addEventListener("scroll", () => this.hide(), true);
      window.addEventListener("resize", () => this.hide());
      return this;
    }

    onMouseOver(event) {
      const host = event.target.closest?.("[data-tooltip]");
      if (!host || host === this.target) return;
      const text = host.dataset.tooltip;
      if (!text) return;
      if (host.dataset.tooltipAlways === undefined && !this.isClipped(host, text)) return;

      this.target = host;
      const format = host.dataset.tooltipFormat;
      const tint = host.dataset.tooltipTint;
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.show(text, format, tint), SHOW_DELAY_MS);
    }

    onMouseOut(event) {
      const host = event.target.closest?.("[data-tooltip]");
      if (host && host === this.target) this.hide();
    }

    onMouseMove(event) {
      this.pointer = { x: event.clientX, y: event.clientY };
      if (!this.element.hidden) this.position();
      // The anchor can vanish under the cursor when a re-render replaces the row.
      if (this.target && !document.contains(this.target)) this.hide();
    }

    /** True when the element cannot display `text` in full at its current size. */
    isClipped(element, text) {
      const style = window.getComputedStyle(element);

      // Blocks clamped with max-height report scrollHeight honestly, unlike
      // -webkit-line-clamp, so trust it directly.
      if (style.maxHeight && style.maxHeight !== "none") {
        return element.scrollHeight > element.clientHeight + 1;
      }

      const clamp = parseInt(style.webkitLineClamp, 10);
      if (Number.isFinite(clamp) && clamp > 0) {
        if (element.scrollHeight > element.clientHeight + 1) return true;
        const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
        const font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        return this.neededLines(text, font, element.clientWidth - padding) > clamp;
      }
      if (element.tagName === "TEXTAREA") {
        return element.scrollHeight > element.clientHeight + 1;
      }

      const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      const border = parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
      // A <select> also spends room on its own dropdown indicator.
      const chrome = element.tagName === "SELECT" ? 22 : 2;
      const available = element.clientWidth - padding - border - chrome;
      if (available <= 0) return false;

      const font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      return this.measurer.width(text, font) > available;
    }

    /** How many lines `text` would occupy when wrapped at `width`. */
    neededLines(text, font, width) {
      if (!(width > 0)) return 1;
      let total = 0;
      for (const paragraph of String(text).split("\n")) {
        if (!paragraph.trim()) { total += 1; continue; }
        let used = 0;
        let count = 1;
        for (const word of paragraph.trim().split(/\s+/)) {
          const chunk = this.measurer.width(word + " ", font);
          if (used > 0 && used + chunk > width) {
            count += 1;
            used = chunk;
          } else {
            used += chunk;
          }
        }
        total += count;
      }
      return total;
    }

    show(text, format, tint) {
      this.element.classList.toggle("tinted", Boolean(tint));
      this.element.style.setProperty("--tooltip-accent", tint || "");
      const formatter = format && this.formatters[format];
      if (formatter) {
        this.element.innerHTML = formatter(text);
        this.element.classList.add("rich");
      } else {
        this.element.textContent = text;
        this.element.classList.remove("rich");
      }
      this.element.hidden = false;
      this.position();
      requestAnimationFrame(() => this.element.classList.add("visible"));
    }

    position() {
      const box = this.element.getBoundingClientRect();
      let left = this.pointer.x + CURSOR_OFFSET;
      let top = this.pointer.y + CURSOR_OFFSET;

      if (left + box.width > window.innerWidth - EDGE_MARGIN) {
        left = Math.max(EDGE_MARGIN, this.pointer.x - box.width - CURSOR_OFFSET);
      }
      if (top + box.height > window.innerHeight - EDGE_MARGIN) {
        top = Math.max(EDGE_MARGIN, this.pointer.y - box.height - CURSOR_OFFSET);
      }

      this.element.style.left = `${left}px`;
      this.element.style.top = `${top}px`;
    }

    hide() {
      clearTimeout(this.timer);
      this.target = null;
      if (!this.element) return;
      this.element.classList.remove("visible");
      this.element.hidden = true;
    }
  }

  window.PlannerTooltip = { TooltipController, TextMeasurer };

})();
