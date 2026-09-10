"use strict";

const { ThemeRegistry, BUILTIN_THEMES } = window.PlannerThemes;
const { TableLayout, BoardLayout, LayoutRegistry, SelectionModel, escapeHtml } =
  window.PlannerLayouts;
const { TooltipController } = window.PlannerTooltip;
const { MarkdownRenderer } = window.PlannerMarkdown;

/** Thin fetch wrapper. Every mutating call returns the full snapshot. */
class Api {
  async request(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = (await response.json()).detail || detail;
      } catch (_) { /* response carried no JSON body */ }
      throw new Error(detail);
    }
    return response.json();
  }

  json(url, method, body) {
    return this.request(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  state() { return this.request("/api/state"); }
  createTask() { return this.request("/api/tasks?at_top=true", { method: "POST" }); }
  updateTask(id, changes) { return this.json(`/api/tasks/${id}`, "PATCH", { changes }); }
  deleteTasks(ids) { return this.json("/api/tasks/delete", "POST", { ids }); }
  duplicateTasks(ids) { return this.json("/api/tasks/duplicate", "POST", { ids }); }
  shutdown() { return this.request("/api/shutdown", { method: "POST" }); }
  saveDefinitions(kind, entries) { return this.json("/api/definitions", "PUT", { kind, entries }); }
  saveSettings(settings) { return this.json("/api/settings", "PUT", { settings }); }

  importFile(file, merge) {
    const form = new FormData();
    form.append("file", file);
    return this.request(`/api/import?merge=${merge}`, { method: "POST", body: form });
  }
}

/** Snapshot holder with change notification. Layouts read from it, never write. */
class Store {
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

class Toast {
  constructor(element) {
    this.element = element;
    this.timer = null;
  }

  show(message, isError = false) {
    this.element.textContent = message;
    this.element.classList.toggle("error", isError);
    this.element.hidden = false;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.element.hidden = true; }, isError ? 6000 : 2200);
  }
}

class DefinitionsModal {
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
      <input type="color" value="${color}">
      <input type="text" value="${escapeHtml(value)}" placeholder="value">
      <button type="button" class="def-remove" title="Remove">&times;</button>
    </div>`;
  }

  bindRemovals(group) {
    group.querySelectorAll(".def-remove").forEach((button) => {
      button.onclick = () => button.closest(".def-row").remove();
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

  async save() {
    if (!this.body.querySelector(".def-group")) { this.close(); return; }
    try {
      let snapshot = null;
      for (const kind of this.kinds) {
        const group = this.body.querySelector(`.def-group[data-kind="${kind}"]`);
        const entries = Array.from(group.querySelectorAll(".def-row")).map((row) => ({
          value: row.querySelector('input[type="text"]').value.trim(),
          color: row.querySelector('input[type="color"]').value,
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

class PlannerApp {
  constructor() {
    this.api = new Api();
    this.store = new Store();
    this.toast = new Toast(document.getElementById("toast"));
    this.modal = new DefinitionsModal(this.store, this.api, this.toast);

    this.themes = new ThemeRegistry("zariman");
    BUILTIN_THEMES.forEach((theme) => this.themes.register(theme));

    this.layouts = new LayoutRegistry("table");
    this.layouts.register(TableLayout);
    this.layouts.register(BoardLayout);

    this.markdown = new MarkdownRenderer();
    this.tooltip = new TooltipController({
      formatters: { markdown: (text) => this.markdown.render(text) },
    }).attach();
    this.selection = new SelectionModel(() => this.refreshSelectionUi());
    this.layoutRoot = document.getElementById("layoutRoot");
    this.layout = null;

    this.store.subscribe(() => this.onStateChanged());
    this.bindToolbar();
  }

  /** Context handed to every layout instance. */
  layoutContext() {
    return {
      store: this.store,
      api: this.api,
      toast: this.toast,
      selection: this.selection,
      tooltip: this.tooltip,
      markdown: this.markdown,
      commit: (id, changes) => this.commit(id, changes),
      persist: (settings) => this.persist(settings),
      focusTask: (id) => this.focusTask(id),
    };
  }

  bindToolbar() {
    document.getElementById("btnAdd").addEventListener("click", async () => {
      try {
        this.store.apply(await this.api.createTask());
        this.toast.show("Task added.");
      } catch (error) {
        this.toast.show(error.message, true);
      }
    });

    document.getElementById("btnDuplicate").addEventListener("click", async () => {
      const ids = this.selection.toArray();
      if (!ids.length) return;
      try {
        this.store.apply(await this.api.duplicateTasks(ids));
        this.selection.clear();
        this.toast.show(`Duplicated ${ids.length}.`);
      } catch (error) {
        this.toast.show(error.message, true);
      }
    });

    document.getElementById("btnDelete").addEventListener("click", async () => {
      const ids = this.selection.toArray();
      if (!ids.length) return;
      if (!confirm(`Delete tasks: ${ids.join(", ")}?`)) return;
      try {
        this.store.apply(await this.api.deleteTasks(ids));
        this.selection.clear();
        this.toast.show(`Deleted ${ids.length}.`);
      } catch (error) {
        this.toast.show(error.message, true);
      }
    });

    document.getElementById("btnQuit").addEventListener("click", () => this.quit());

    document.getElementById("btnDefs").addEventListener("click", () => this.modal.open());
    document.getElementById("btnExport").addEventListener("click", () => {
      window.location.href = "/api/export";
    });

    const fileInput = document.getElementById("fileInput");
    document.getElementById("btnImport").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const merge = confirm(
        "OK = merge: a task with a matching id or name is updated in place, "
        + "anything else is added.\n\n"
        + "Cancel = replace: everything currently here is discarded and the "
        + "file becomes the whole planner."
      );
      try {
        this.store.apply(await this.api.importFile(file, merge));
        this.toast.show("Import complete.");
      } catch (error) {
        this.toast.show(error.message, true);
      }
      fileInput.value = "";
    });

    const search = document.getElementById("search");
    search.addEventListener("input", () => {
      if (this.layout && this.layout.setFilter) this.layout.setFilter(search.value.trim());
    });

    document.getElementById("themePicker").addEventListener("change", (event) => {
      this.applyTheme(event.target.value);
      this.persist({ theme: event.target.value });
    });


  }

  async persist(settings) {
    try {
      this.store.apply(await this.api.saveSettings(settings));
    } catch (error) {
      this.toast.show(error.message, true);
    }
  }

  async commit(id, changes) {
    try {
      this.store.apply(await this.api.updateTask(id, changes));
    } catch (error) {
      this.toast.show(error.message, true);
      if (this.layout) this.layout.render();
    }
  }

  /** Stop the server process, not just this tab. */
  async quit() {
    if (!confirm("Shut down Warframe Planner?\n\n"
                 + "This stops the background process, not just this tab. "
                 + "Your data is already saved.")) return;
    try {
      await this.api.shutdown();
    } catch (error) {
      // A dropped connection is the expected outcome: the server may finish
      // unwinding before the response reaches us.
    }
    document.getElementById("curtain").hidden = false;
  }

  /** Hand a task over to the table layout and highlight it there. */
  focusTask(id) {
    const search = document.getElementById("search");
    if (search.value) {
      search.value = "";
      if (this.layout && this.layout.setFilter) this.layout.setFilter("");
    }
    this.activateLayout("table");
    this.persist({ layout: "table" });
    if (this.layout && this.layout.focusTask) this.layout.focusTask(id);
  }

  applyTheme(key) {
    this.themes.apply(key);
    const picker = document.getElementById("themePicker");
    if (picker.value !== key) picker.value = key;
  }

  activateLayout(key) {
    this.layout = this.layouts.activate(key, this.layoutRoot, this.layoutContext());
    this.activeLayoutKey = this.layout ? this.layout.constructor.key : key;
    this.renderTabs();
    const search = document.getElementById("search");
    if (this.layout && this.layout.setFilter) this.layout.setFilter(search.value.trim());
    if (this.layout) this.layout.render();
  }

  renderPickers() {
    const themePicker = document.getElementById("themePicker");
    themePicker.innerHTML = this.themes.list().map((theme) =>
      `<option value="${theme.key}">${escapeHtml(theme.label)}</option>`).join("");
    themePicker.value = this.themes.activeKey || "zariman";

    this.renderTabs();
  }

  /** Browser-style tab strip sitting between the toolbar and the layout. */
  renderTabs() {
    const strip = document.getElementById("layoutTabs");
    const available = this.layouts.list();
    // Nothing to switch between while a single layout is registered.
    strip.hidden = available.length < 2;

    strip.innerHTML = available.map((layout) => `
      <button class="tab" role="tab" data-key="${layout.key}"
              aria-selected="${layout.key === this.activeLayoutKey}"
        >${escapeHtml(layout.label)}</button>`).join("");

    strip.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        if (tab.dataset.key === this.activeLayoutKey) return;
        this.activateLayout(tab.dataset.key);
        this.persist({ layout: tab.dataset.key });
      });
    });
  }

  refreshSelectionUi() {
    const empty = this.selection.size === 0;
    document.getElementById("btnDelete").disabled = empty;
    document.getElementById("btnDuplicate").disabled = empty;
  }

  onStateChanged() {
    this.renderKpis();
    if (this.layout) this.layout.render();
    this.refreshSelectionUi();
  }

  renderKpis() {
    const stats = this.store.stats;
    const cards = [{ label: "Total tasks", value: stats.total, color: null }];

    this.store.valuesFor("status").forEach((status) => {
      cards.push({
        label: status,
        value: stats.counts[status] || 0,
        color: this.store.colorFor("status", status),
      });
    });

    cards.push({
      label: "Completion rate",
      value: `${(stats.completion_rate * 100).toFixed(1)}%`,
      color: "var(--ok)",
    });

    document.getElementById("kpiRow").innerHTML = cards.map((card) => {
      const accent = card.color ? ` style="--kpi-accent:${card.color}"` : "";
      const value = card.color ? ` style="color:${card.color}"` : "";
      return `
      <div class="kpi"${accent}>
        <div class="label">${escapeHtml(String(card.label))}</div>
        <div class="value"${value}>${card.value}</div>
      </div>`;
    }).join("");

    document.getElementById("progressFill").style.width = `${stats.completion_rate * 100}%`;
  }

  async start() {
    try {
      const snapshot = await this.api.state();
      this.themes.load(snapshot.themes);
      this.store.apply(snapshot);
      this.applyTheme(snapshot.settings.theme || "zariman");
      this.activeLayoutKey = snapshot.settings.layout || "table";
      this.renderPickers();
      this.activateLayout(this.activeLayoutKey);
    } catch (error) {
      this.toast.show(`Could not reach the backend: ${error.message}`, true);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => new PlannerApp().start());
