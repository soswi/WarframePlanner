import { escapeHtml } from "../core/html.js";

export class DotSelect {
  constructor(context) {
    this.ctx = context;
    this.store = context.store;
    this.menu = null;
    this.dismiss = null;
  }

  values(kind) {
    return [""].concat(this.store.valuesFor(kind));
  }

  html(task, field, kind) {
    const current = task[field] || "";
    const color = this.store.colorFor(kind, current);
    const style = color ? ` style="--dot-color:${color}"` : "";
    const tip = current
      ? ` data-tooltip="${escapeHtml(current)}" data-tooltip-always`
        + ` data-tooltip-tint="${color || ""}"`
      : "";
    return `<button type="button" class="dot-select" data-role="dot-select"
                    data-field="${field}" data-kind="${kind}" data-id="${task.id}"
                    data-value="${escapeHtml(current)}"
                    aria-label="${escapeHtml(field)}"${style}${tip}>
      <span class="dot${current ? "" : " is-unset"}"></span>
    </button>`;
  }

  /** Repaint in place, ahead of the deferred write. */
  paint(host, kind, value, direction) {
    const color = this.store.colorFor(kind, value);
    host.style.setProperty("--dot-color", color || "");
    host.dataset.value = value;

    const dot = host.querySelector(".dot");
    dot.classList.toggle("is-unset", !value);
    if (value) {
      host.dataset.tooltip = value;
      host.dataset.tooltipAlways = "";
      host.dataset.tooltipTint = color || "";
    } else {
      delete host.dataset.tooltip;
    }

    if (!direction) return;
    const animation = direction > 0 ? "reel-up" : "reel-down";
    dot.classList.remove("reel-up", "reel-down");
    // Forces a reflow so the same animation restarts on a fast second step.
    void dot.offsetWidth;
    dot.classList.add(animation);
  }

  bind(root) {
    root.querySelectorAll('[data-role="dot-select"]').forEach((host) => {
      const id = Number(host.dataset.id);
      const field = host.dataset.field;
      const kind = host.dataset.kind;

      host.addEventListener("click", (event) => {
        event.stopPropagation();
        this.openMenu(host, id, field, kind);
      });

      host.addEventListener("wheel", (event) => {
        event.preventDefault();
        const values = this.values(kind);
        const step = event.deltaY > 0 ? 1 : -1;
        const next = values.indexOf(host.dataset.value || "") + step;
        if (next < 0 || next >= values.length) return;
        this.paint(host, kind, values[next], step);
        this.ctx.commitDelayed(id, { [field]: values[next] });
      }, { passive: false });
    });
  }

  openMenu(host, id, field, kind) {
    this.closeMenu();

    const menu = document.createElement("div");
    menu.className = "dot-menu";
    menu.innerHTML = this.values(kind).map((value) =>
      `<button type="button" data-value="${escapeHtml(value)}"
               aria-selected="${value === host.dataset.value}"
       >${escapeHtml(value || "None")}</button>`).join("");

    const box = host.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.left = `${box.left}px`;
    menu.style.top = `${box.bottom + 4}px`;
    document.body.appendChild(menu);

    const menuBox = menu.getBoundingClientRect();
    if (menuBox.bottom > window.innerHeight - 8) {
      menu.style.top = `${Math.max(8, box.top - menuBox.height - 4)}px`;
    }

    menu.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const value = button.dataset.value;
        this.paint(host, kind, value, 0);
        this.closeMenu();
        this.ctx.commitDelayed(id, { [field]: value });
      });
    });

    this.menu = menu;
    this.dismiss = () => this.closeMenu();
    document.addEventListener("click", this.dismiss, { once: true });
    window.addEventListener("scroll", this.dismiss, { once: true, capture: true });
  }

  closeMenu() {
    if (!this.menu) return;
    this.menu.remove();
    this.menu = null;
    if (this.dismiss) {
      document.removeEventListener("click", this.dismiss);
      window.removeEventListener("scroll", this.dismiss, true);
      this.dismiss = null;
    }
  }
}
