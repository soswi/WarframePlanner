"use strict";

// Wrapped in an IIFE: these files load as classic scripts and share one global
// lexical scope, so top-level class declarations would collide with the
// destructuring imports in app.js. Only window.PlannerLayouts escapes.
(function () {

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
  class Layout {
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

  class SelectionModel {
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

  class TableLayout extends Layout {
    static key = "table";
    static label = "Table";

    constructor(context) {
      super(context);
      this.markdown = context.markdown;
      this.sortKey = null;
      this.sortDirection = 1;
      this.filter = "";
      this.expanded = new Set();
      this.columns = this.buildColumns();
    }

    /** Column descriptors keep render() short and make adding a column a one-liner. */
    buildColumns() {
      return [
        { key: "id", title: "Task ID", sortable: true, cell: (t) => `<div class="task-id">${t.id}</div>` },
        { key: "activity", title: "Activity", sortable: true, cell: (t) => this.textCell(t, "activity", "Task name") },
        { key: "category", title: "Category", sortable: true, cell: (t) => this.selectCell(t, "category", "category") },
        { key: "description", title: "Description", sortable: false, className: "desc-cell", cell: (t) => this.descriptionCell(t) },
        { key: "priority", title: "Priority", sortable: true, cell: (t) => this.selectCell(t, "priority", "priority") },
        { key: "status", title: "Status", sortable: true, cell: (t) => this.selectCell(t, "status", "status") },
        { key: "dependencies", title: "Dependencies", sortable: false, className: "dep-cell", cell: (t) => this.dependencyCell(t) },
        { key: "prereq_status", title: "Prereq Status", sortable: true, cell: (t) => this.prereqCell(t) },
        { key: "last_updated", title: "Last Updated", sortable: true, cell: (t) => `<div class="date-cell">${t.last_updated || "—"}</div>` },
        { key: "recurrence", title: "Recurrence", sortable: true, cell: (t) => this.recurrenceCell(t) },
      ];
    }

    mount(root) {
      super.mount(root);
      root.innerHTML = `
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th class="col-check"><input type="checkbox" data-role="check-all"></th>
              ${this.columns.map((column) => `
                <th class="${column.sortable ? "sortable" : ""}" data-sort="${column.key}">${column.title}</th>
              `).join("")}
            </tr></thead>
            <tbody data-role="body"></tbody>
          </table>
          <p class="empty" data-role="empty" hidden>No tasks yet. Use “Add task”.</p>
        </div>`;

      this.tbody = root.querySelector('[data-role="body"]');
      this.emptyState = root.querySelector('[data-role="empty"]');
      this.checkAll = root.querySelector('[data-role="check-all"]');

      this.checkAll.addEventListener("change", () => {
        this.selection.replace(this.checkAll.checked ? this.visibleTasks().map((t) => t.id) : []);
        this.render();
      });

      root.querySelectorAll("th.sortable").forEach((th) => {
        th.addEventListener("click", () => this.sortBy(th.dataset.sort));
      });
    }

    setFilter(value) {
      this.filter = value;
      this.render();
    }

    /** Scroll a row into view and flash it. Used when arriving from the board. */
    focusTask(id) {
      this.pendingFocus = id;
      this.render();
    }

    applyPendingFocus() {
      if (this.pendingFocus === undefined || this.pendingFocus === null) return;
      const id = this.pendingFocus;
      this.pendingFocus = null;
      const row = this.tbody.querySelector(`tr[data-id="${id}"]`);
      if (!row) return;
      row.scrollIntoView({ block: "center", behavior: "smooth" });
      row.classList.add("flash");
      setTimeout(() => row.classList.remove("flash"), 1600);
    }

    sortBy(key) {
      if (this.sortKey === key) {
        this.sortDirection = -this.sortDirection;
      } else {
        this.sortKey = key;
        this.sortDirection = 1;
      }
      this.root.querySelectorAll("th.sortable").forEach((th) => {
        th.classList.remove("sorted-asc", "sorted-desc");
        if (th.dataset.sort === key) {
          th.classList.add(this.sortDirection === 1 ? "sorted-asc" : "sorted-desc");
        }
      });
      this.render();
    }

    visibleTasks() {
      let rows = this.store.tasks.slice();

      if (this.filter) {
        const needle = this.filter.toLowerCase();
        rows = rows.filter((task) =>
          ["activity", "category", "description", "status", "priority", "recurrence"]
            .some((key) => String(task[key] || "").toLowerCase().includes(needle))
          || String(task.id).includes(needle));
      }

      if (this.sortKey) {
        const key = this.sortKey;
        rows.sort((a, b) => {
          const left = a[key] ?? "";
          const right = b[key] ?? "";
          if (typeof left === "number" && typeof right === "number") {
            return (left - right) * this.sortDirection;
          }
          return String(left).localeCompare(String(right)) * this.sortDirection;
        });
      }
      return rows;
    }

    // ------------------------------------------------------------ cell builders

    textCell(task, field, placeholder) {
      const value = task[field] || "";
      return `<input class="cell-input" data-field="${field}" data-id="${task.id}"
                     data-tooltip="${escapeHtml(value)}"
                     value="${escapeHtml(value)}" placeholder="${placeholder}">`;
    }

    selectCell(task, field, kind) {
      const current = task[field] || "";
      const options = ['<option value="">—</option>'].concat(
        this.store.valuesFor(kind).map((value) =>
          `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`));
      const color = this.store.colorFor(kind, current);
      const style = color ? ` style="color:${color};font-weight:600"` : "";
      return `<select class="cell-select" data-field="${field}" data-id="${task.id}"
                      data-tooltip="${escapeHtml(current)}"${style}>${options.join("")}</select>`;
    }

    descriptionCell(task) {
      const expanded = this.expanded.has(task.id) ? " expanded" : "";
      const source = task.description || "";
      // Rendered Markdown in the cell, raw Markdown in the tooltip payload; the
      // tooltip re-renders it through the same renderer.
      const body = source
        ? this.markdown.render(source)
        : '<span class="placeholder">Click to add a description</span>';
      return `<div class="desc-text markdown${expanded}" data-role="desc" data-id="${task.id}"
                    data-tooltip="${escapeHtml(source)}" data-tooltip-format="markdown"
                    >${body}</div>`;
    }

    dependencyCell(task) {
      const index = new Map(this.store.tasks.map((t) => [t.id, t]));
      const chips = task.dependencies.map((depId) => {
        const dep = index.get(depId);
        const satisfied = dep && dep.status === this.store.doneStatus();
        const state = dep ? (satisfied ? "ok" : "open") : "missing";
        const hint = dep
          ? `${dep.id} · ${dep.activity || "(unnamed)"} — ${dep.status || "no status"}`
          : `${depId} — this task no longer exists`;
        return `<span class="dep-chip ${state}" data-tooltip="${escapeHtml(hint)}"
                      data-tooltip-always>${depId}<button
                   type="button" data-role="dep-remove" data-id="${task.id}" data-dep="${depId}"
                   title="Remove">&times;</button></span>`;
      }).join("");

      const candidates = this.store.tasks
        .filter((other) => other.id !== task.id && !task.dependencies.includes(other.id))
        .map((other) => {
          const label = `${other.id}${other.activity ? " · " + other.activity : ""}`;
          return `<option value="${other.id}">${escapeHtml(label)}</option>`;
        }).join("");

      const adder = candidates
        ? `<select class="dep-add" data-role="dep-add" data-id="${task.id}">
             <option value="">+</option>${candidates}
           </select>`
        : "";

      return `<div class="dep-list">${chips}${adder}</div>`;
    }

    prereqCell(task) {
      const state = task.prereq_status;
      const tone = { Ready: "ok", Blocked: "warn", "Invalid ID": "danger", "Self-reference": "danger" }[state] || "muted";
      const index = new Map(this.store.tasks.map((t) => [t.id, t]));
      const blockers = (task.blocked_by || []).map((id) => {
        const dep = index.get(id);
        return `${id} · ${dep ? (dep.activity || "(unnamed)") : "?"} — ${dep ? (dep.status || "no status") : "?"}`;
      });
      const missing = (task.missing_dependencies || []).map((id) => `${id} — missing`);
      const detail = blockers.concat(missing);
      const hint = detail.length ? `Waiting on:\n${detail.join("\n")}` : "";
      const attrs = hint ? ` data-tooltip="${escapeHtml(hint)}" data-tooltip-always` : "";
      return `<span class="chip tone-${tone}"${attrs}>${escapeHtml(state || "—")}</span>`;
    }

    recurrenceCell(task) {
      const options = this.store.recurrence.map((rule) =>
        `<option value="${escapeHtml(rule.key)}"${rule.key === task.recurrence ? " selected" : ""}
         >${escapeHtml(rule.key)}</option>`).join("");
      return `<select class="cell-select" data-field="recurrence" data-id="${task.id}">${options}</select>`;
    }

    // ------------------------------------------------------------------ render

    render() {
      if (!this.tbody) return;
      if (this.ctx.tooltip) this.ctx.tooltip.hide();
      const rows = this.visibleTasks();

      this.tbody.innerHTML = rows.map((task) => `
        <tr class="${this.selection.has(task.id) ? "selected" : ""}" data-id="${task.id}">
          <td><input type="checkbox" data-role="select" data-id="${task.id}"
                     ${this.selection.has(task.id) ? "checked" : ""}></td>
          ${this.columns.map((column) =>
            `<td class="${column.className || ""}">${column.cell(task)}</td>`).join("")}
        </tr>`).join("");

      this.emptyState.hidden = rows.length > 0;
      this.checkAll.checked = rows.length > 0 && rows.every((t) => this.selection.has(t.id));
      this.bindRows();
      this.applyPendingFocus();
    }

    bindRows() {
      this.tbody.querySelectorAll('[data-role="select"]').forEach((box) => {
        box.addEventListener("change", () => {
          this.selection.toggle(Number(box.dataset.id), box.checked);
          box.closest("tr").classList.toggle("selected", box.checked);
        });
      });

      this.tbody.querySelectorAll(".cell-input").forEach((input) => {
        input.addEventListener("change", () =>
          this.ctx.commit(Number(input.dataset.id), { [input.dataset.field]: input.value }));
      });

      this.tbody.querySelectorAll(".cell-select").forEach((select) => {
        select.addEventListener("change", () =>
          this.ctx.commit(Number(select.dataset.id), { [select.dataset.field]: select.value }));
      });

      this.tbody.querySelectorAll('[data-role="dep-add"]').forEach((select) => {
        select.addEventListener("change", () => {
          if (!select.value) return;
          const taskId = Number(select.dataset.id);
          const task = this.store.tasks.find((t) => t.id === taskId);
          this.ctx.commit(taskId, {
            dependencies: task.dependencies.concat(Number(select.value)),
          });
        });
      });

      this.tbody.querySelectorAll('[data-role="dep-remove"]').forEach((button) => {
        button.addEventListener("click", () => {
          const taskId = Number(button.dataset.id);
          const depId = Number(button.dataset.dep);
          const task = this.store.tasks.find((t) => t.id === taskId);
          this.ctx.commit(taskId, {
            dependencies: task.dependencies.filter((d) => d !== depId),
          });
        });
      });

      this.tbody.querySelectorAll('[data-role="desc"]').forEach((node) => {
        node.addEventListener("click", () => this.editDescription(node));
      });
    }

    editDescription(node) {
      const id = Number(node.dataset.id);
      const task = this.store.tasks.find((t) => t.id === id);
      const editor = document.createElement("textarea");
      editor.className = "desc-editor";
      editor.value = task.description || "";
      node.replaceWith(editor);
      editor.focus();

      editor.addEventListener("blur", () => {
        if (editor.value !== (task.description || "")) {
          this.ctx.commit(id, { description: editor.value });
        } else {
          this.render();
        }
      }, { once: true });

      editor.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          editor.value = task.description || "";
          editor.blur();
        }
      });
    }
  }

  class LayoutRegistry {
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

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.PlannerLayouts = { Layout, TableLayout, LayoutRegistry, SelectionModel, escapeHtml };

})();
