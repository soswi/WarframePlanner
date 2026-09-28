import { escapeHtml } from "../core/html.js";
import { Dropdown } from "../ui/dropdown.js";

export class DefinitionsModal {
  constructor(store, api, toast) {
    this.store = store;
    this.api = api;
    this.toast = toast;
    this.backdrop = document.getElementById("defsModal");
    this.body = document.getElementById("defsBody");
    this.settingsRow = document.getElementById("settingsRow");
    this.kinds = ["status", "priority", "category"];

    document.getElementById("btnCloseDefs").addEventListener("click", () => this.close());
    document.getElementById("btnSaveDefs").addEventListener("click", () => this.save());
    document.getElementById("btnResetDefs").addEventListener("click", () => this.reset());
    this.backdrop.addEventListener("click", (event) => {
      if (event.target === this.backdrop) this.close();
    });
  }

  open() {
    this.body.innerHTML = this.kinds.map((kind) => `
      <div class="def-group" data-kind="${kind}">
        <h3>${kind} <span class="def-hint">drag to reorder</span></h3>
        <div class="def-list">
          ${(this.store.definitions[kind] || []).map((d) => this.rowHtml(d.value, d.color)).join("")}
        </div>
        <button class="add-def" type="button">+ add value</button>
      </div>`).join("");

    this.body.querySelectorAll(".def-group").forEach((group) => {
      group.querySelector(".add-def").addEventListener("click", () => {
        group.querySelector(".def-list").insertAdjacentHTML("beforeend", this.rowHtml("", "#94a3b8"));
        this.bindRemovals(group);
        this.bindReordering(group);
      });
      this.bindRemovals(group);
      this.bindReordering(group);
    });

    const statuses = this.store.valuesFor("status");
    const statusSelect = (key, label) => `
      <label>${label}
        <select data-setting="${key}">
          ${statuses.map((value) =>
            `<option${value === this.store.settings[key] ? " selected" : ""}>${escapeHtml(value)}</option>`).join("")}
        </select>
      </label>`;

    const gateOn = this.store.settings.enforce_dependency_gate !== "false";
    const pinned = this.store.settings.highlight_status || "";
    const pinnedSelect = `
      <label>Pinned status
        <select data-setting="highlight_status">
          <option value=""${pinned ? "" : " selected"}>None</option>
          ${statuses.map((value) =>
            `<option${value === pinned ? " selected" : ""}>${escapeHtml(value)}</option>`).join("")}
        </select>
      </label>`;

    this.settingsRow.innerHTML =
      statusSelect("done_status", "Completion status")
      + statusSelect("reset_status", "Status after reset")
      + pinnedSelect
      + `<label>Dependency gate
           <select data-setting="enforce_dependency_gate">
             <option value="true"${gateOn ? " selected" : ""}>Block completion</option>
             <option value="false"${gateOn ? "" : " selected"}>Allow anyway</option>
           </select>
         </label>`;

    this.backdrop.hidden = false;
    Dropdown.enhanceAll(this.backdrop);
  }

  rowHtml(value, color) {
    // Only the handle is draggable, so the text and colour inputs keep their
    // normal click-and-select behaviour.
    return `<div class="def-row">
      <span class="def-grip" draggable="true" title="Drag to reorder" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/>
          <circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/>
          <circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/>
        </svg>
      </span>
      <span class="color-field">
        <input type="color" value="${color}">
        <input type="text" class="hex" value="${escapeHtml(color)}" spellcheck="false"
               maxlength="7" aria-label="Hex colour">
      </span>
      <input type="text" class="def-value" value="${escapeHtml(value)}" placeholder="value">
      <button type="button" class="def-remove" title="Remove">&times;</button>
    </div>`;
  }

  bindRemovals(group) {
    group.querySelectorAll(".def-remove").forEach((button) => {
      button.onclick = () => button.closest(".def-row").remove();
    });
    this.bindColorFields(group);
  }

  /** Keep the swatch and the typed hex in step, in both directions. */
  bindColorFields(group) {
    group.querySelectorAll(".color-field").forEach((field) => {
      const swatch = field.querySelector('input[type="color"]');
      const hex = field.querySelector(".hex");

      swatch.oninput = () => {
        hex.value = swatch.value;
        hex.classList.remove("invalid");
      };

      hex.oninput = () => {
        const value = hex.value.trim();
        const valid = /^#[0-9a-fA-F]{6}$/.test(value);
        hex.classList.toggle("invalid", Boolean(value) && !valid);
        if (valid) swatch.value = value;
      };

      // Anything unparseable falls back to the swatch rather than being saved.
      hex.onblur = () => {
        if (!/^#[0-9a-fA-F]{6}$/.test(hex.value.trim())) hex.value = swatch.value;
        hex.classList.remove("invalid");
      };
    });
  }

  /**
   * Vertical drag-to-reorder within one definition list.
   *
   * Rows are moved in the DOM as the pointer passes each midpoint, so the list
   * previews the result while dragging. Order is read back from the DOM on
   * save, which is why no separate model needs updating here.
   */
  bindReordering(group) {
    const list = group.querySelector(".def-list");

    group.querySelectorAll(".def-grip").forEach((grip) => {
      const row = grip.closest(".def-row");

      grip.addEventListener("dragstart", (event) => {
        this.draggedRow = row;
        row.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        // Firefox will not start a drag without a payload.
        event.dataTransfer.setData("text/plain", "");
      });

      grip.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        this.draggedRow = null;
      });
    });

    list.addEventListener("dragover", (event) => {
      const row = this.draggedRow;
      if (!row || !list.contains(row)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";

      const after = this.rowAfterPointer(list, event.clientY);
      if (after === row) return;
      if (after === null) {
        list.appendChild(row);
      } else {
        list.insertBefore(row, after);
      }
    });

    list.addEventListener("drop", (event) => event.preventDefault());
  }

  /** First row whose midpoint sits below the pointer, or null past the end. */
  rowAfterPointer(list, y) {
    const others = Array.from(list.querySelectorAll(".def-row:not(.dragging)"));
    for (const candidate of others) {
      const box = candidate.getBoundingClientRect();
      if (y < box.top + box.height / 2) return candidate;
    }
    return null;
  }

  close() { this.backdrop.hidden = true; }

  /**
   * Restore the shipped palette. Unsaved edits in the dialog are discarded, and
   * the dialog is rebuilt so it shows what was actually stored.
   */
  async reset() {
    if (!confirm("Reset every status, priority and category to the defaults?\n\n"
                 + "Custom values and colours are removed. Tasks keep their own "
                 + "values, so any that no longer match a definition will show "
                 + "without colour.")) return;
    try {
      this.store.apply(await this.api.resetDefinitions());
      this.open();
      this.toast.show("Definitions reset to defaults.");
    } catch (error) {
      this.toast.show(error.message, true);
    }
  }

  async save() {
    if (!this.body.querySelector(".def-group")) { this.close(); return; }
    try {
      let snapshot = null;
      for (const kind of this.kinds) {
        const group = this.body.querySelector(`.def-group[data-kind="${kind}"]`);
        const entries = Array.from(group.querySelectorAll(".def-row")).map((row) => ({
          // Must be .def-value, not input[type="text"]: the hex field is also a
          // text input and comes first in the row.
          value: row.querySelector(".def-value").value.trim(),
          color: row.querySelector(".hex").value.trim().toLowerCase(),
        })).filter((entry) => entry.value);
        snapshot = await this.api.saveDefinitions(kind, entries);
      }

      const settings = {};
      this.settingsRow.querySelectorAll("select").forEach((select) => {
        settings[select.dataset.setting] = select.value;
      });
      snapshot = await this.api.saveSettings(settings);

      this.store.apply(snapshot);
      this.close();
      this.toast.show("Definitions saved.");
    } catch (error) {
      this.toast.show(error.message, true);
    }
  }
}
