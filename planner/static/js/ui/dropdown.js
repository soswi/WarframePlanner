/**
 * Replaces a native <select> with a themed trigger and menu.
 *
 * The <select> stays in the DOM as the single source of truth: the trigger
 * writes to it and dispatches a normal `change` event, so every existing
 * listener keeps working and no call site has to be rewritten. A native
 * option list cannot be themed — it is drawn by the operating system — which
 * is the whole reason for the swap.
 *
 * An option may carry data-color; the trigger label then takes that colour,
 * so a status or category reads at a glance without waiting for a round trip.
 */
export class Dropdown {
  static enhanceAll(root) {
    if (!root) return;
    root.querySelectorAll("select:not([data-enhanced])").forEach((select) => {
      new Dropdown(select);
    });
  }

  constructor(select) {
    this.select = select;
    select.dataset.enhanced = "true";

    this.trigger = document.createElement("button");
    this.trigger.type = "button";
    this.trigger.className = `dd-trigger ${select.className}`.trim();
    this.trigger.innerHTML = '<span class="dd-label"></span><span class="dd-caret"></span>';
    if (select.title) this.trigger.title = select.title;
    select.parentNode.insertBefore(this.trigger, select);
    select.classList.add("dd-native");

    this.label = this.trigger.querySelector(".dd-label");
    this.menu = null;

    this.trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      this.toggle();
    });

    this.trigger.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.step(event.deltaY > 0 ? 1 : -1);
    }, { passive: false });

    this.trigger.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") { event.preventDefault(); this.step(1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); this.step(-1); }
      else if (event.key === "Escape") this.close();
    });

    // Anything that writes to the select directly still repaints the trigger.
    select.addEventListener("change", () => this.sync(0));

    this.sync(0);
  }

  get options() {
    return Array.from(this.select.options);
  }

  step(direction) {
    const next = this.select.selectedIndex + direction;
    if (next < 0 || next >= this.select.options.length) return;
    this.select.selectedIndex = next;
    this.sync(direction);
    this.select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** Repaint the trigger from the current selection, optionally rolling it. */
  sync(direction) {
    const option = this.select.options[this.select.selectedIndex];
    const text = option ? option.textContent.trim() : "";
    const color = option ? option.dataset.color : "";

    this.label.textContent = text;
    this.label.style.color = color || "";
    this.label.style.fontWeight = color ? "600" : "";
    this.trigger.style.borderColor = color
      ? `color-mix(in srgb, ${color} 55%, var(--border))`
      : "";

    if (!direction) return;
    // Only the label rolls. Animating the whole control would drag the caret
    // and the border along with it.
    const animation = direction > 0 ? "reel-up" : "reel-down";
    this.label.classList.remove("reel-up", "reel-down");
    // Forces a reflow so the same animation restarts on a fast second step.
    void this.label.offsetWidth;
    this.label.classList.add(animation);
  }

  toggle() {
    if (this.menu) this.close(); else this.open();
  }

  open() {
    Dropdown.closeOpen();

    this.menu = document.createElement("div");
    this.menu.className = "dd-menu";
    this.menu.innerHTML = this.options.map((option, index) => `
      <button type="button" data-index="${index}"
              aria-selected="${index === this.select.selectedIndex}"
      >${option.textContent.trim() || "—"}</button>`).join("");

    const box = this.trigger.getBoundingClientRect();
    this.menu.style.position = "fixed";
    this.menu.style.left = `${box.left}px`;
    this.menu.style.top = `${box.bottom + 4}px`;
    this.menu.style.minWidth = `${box.width}px`;
    document.body.appendChild(this.menu);

    // Flip above the trigger when there is no room below.
    const menuBox = this.menu.getBoundingClientRect();
    if (menuBox.bottom > window.innerHeight - 8) {
      this.menu.style.top = `${Math.max(8, box.top - menuBox.height - 4)}px`;
    }

    this.menu.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        this.select.selectedIndex = Number(button.dataset.index);
        this.sync(0);
        this.close();
        this.select.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });

    Dropdown.open = this;
    Dropdown.dismiss = () => Dropdown.closeOpen();
    document.addEventListener("click", Dropdown.dismiss);
    window.addEventListener("scroll", Dropdown.dismiss, true);
    window.addEventListener("resize", Dropdown.dismiss);
  }

  close() {
    if (this.menu) {
      this.menu.remove();
      this.menu = null;
    }
    if (Dropdown.open === this) Dropdown.clearListeners();
  }

  static closeOpen() {
    if (Dropdown.open) Dropdown.open.close();
  }

  static clearListeners() {
    document.removeEventListener("click", Dropdown.dismiss);
    window.removeEventListener("scroll", Dropdown.dismiss, true);
    window.removeEventListener("resize", Dropdown.dismiss);
    Dropdown.open = null;
    Dropdown.dismiss = null;
  }
}

Dropdown.open = null;
Dropdown.dismiss = null;
