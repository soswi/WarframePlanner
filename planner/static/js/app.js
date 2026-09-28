/**
 * Application entry point.
 *
 * Loaded as a module, so imports resolve explicitly and the load order no
 * longer depends on the sequence of script tags in index.html.
 */

import { Api } from "./core/api.js";
import { escapeHtml } from "./core/html.js";
import { Store } from "./core/store.js";
import { Toast } from "./core/toast.js";
import { BoardLayout } from "./layouts/board.js";
import { LayoutRegistry } from "./layouts/registry.js";
import { SelectionModel } from "./layouts/selection.js";
import { TableLayout } from "./layouts/table.js";
import { DefinitionsModal } from "./modals/definitions.js";
import { ThemeRegistry, BUILTIN_THEMES } from "./themes.js";
import { Dropdown } from "./ui/dropdown.js";
import { MarkdownRenderer } from "./ui/markdown.js";
import { TooltipController } from "./ui/tooltip.js";

// How long a status or priority edit waits before it is written and the list
// reorders around it.
const DEFERRED_COMMIT_DELAY_MS = 1000;

/** Thin fetch wrapper. Every mutating call returns the full snapshot. */

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
    this.pendingEdits = new Map();
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
      commitDelayed: (id, changes) => this.commitDelayed(id, changes),
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

  /**
   * Hold an edit for a moment before sending it.
   *
   * Status and priority changes reorder the list, and reordering under the
   * pointer the instant a value is picked is disorienting — especially when
   * stepping through values with the wheel. The pause also collapses a burst
   * of wheel steps into a single write. The cell repaints itself immediately,
   * so only the reordering waits.
   */
  commitDelayed(id, changes) {
    const key = `${id}:${Object.keys(changes).join(",")}`;
    clearTimeout(this.pendingEdits.get(key));
    this.pendingEdits.set(key, setTimeout(() => {
      this.pendingEdits.delete(key);
      this.commit(id, changes);
    }, DEFERRED_COMMIT_DELAY_MS));
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
    Dropdown.enhanceAll(document.querySelector(".toolbar"));

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
