"use strict";

// Wrapped in an IIFE: these files load as classic scripts and share one global
// lexical scope. Registers itself onto the existing PlannerLayouts namespace.
(function () {

  const { Layout, escapeHtml } = window.PlannerLayouts;

  const UNGROUPED = "\u0000none";
  const EMPTY_BUCKET = "\u0000empty";

  /**
   * Card board. Shows only what the brief asked for — title, description and an
   * editable status — plus a jump button that hands the task over to the table.
   *
   * Grouping is generic: any definition-backed field (status, priority,
   * category) or recurrence can become the column axis, and dropping a card on
   * a column writes that field. Grouping by nothing degrades to a flat grid,
   * where dragging is meaningless and therefore disabled.
   */
  class BoardLayout extends Layout {
    static key = "board";
    static label = "Board";

    // field -> definition kind backing its values, or null for code-defined lists.
    static GROUPABLE = {
      status: "status",
      priority: "priority",
      category: "category",
      recurrence: null,
    };

    constructor(context) {
      super(context);
      this.markdown = context.markdown;
      this.filter = "";
      this.groupBy = "status";
      this.cardSize = "comfortable";
      this.dragging = null;
    }

    mount(root) {
      super.mount(root);

      const settings = this.store.settings || {};
      this.groupBy = settings.board_group_by || "status";
      this.cardSize = settings.board_card_size || "comfortable";

      root.innerHTML = `
        <div class="board" data-size="${escapeHtml(this.cardSize)}">
          <div class="board-controls">
            <label class="board-control">Group by
              <select class="picker" data-role="group-by">
                ${Object.keys(BoardLayout.GROUPABLE).map((field) =>
                  `<option value="${field}">${this.fieldLabel(field)}</option>`).join("")}
                <option value="${UNGROUPED}">Nothing</option>
              </select>
            </label>
            <label class="board-control">Card size
              <select class="picker" data-role="card-size">
                <option value="compact">Compact</option>
                <option value="comfortable">Comfortable</option>
                <option value="roomy">Roomy</option>
              </select>
            </label>
            <span class="board-hint" data-role="hint"></span>
          </div>
          <div class="board-columns" data-role="columns"></div>
          <p class="empty" data-role="empty" hidden>No tasks yet. Use “Add task”.</p>
        </div>`;

      this.board = root.querySelector(".board");
      this.columnsHost = root.querySelector('[data-role="columns"]');
      this.emptyState = root.querySelector('[data-role="empty"]');
      this.hint = root.querySelector('[data-role="hint"]');

      const groupPicker = root.querySelector('[data-role="group-by"]');
      groupPicker.value = this.groupBy;
      groupPicker.addEventListener("change", () => {
        this.groupBy = groupPicker.value;
        this.ctx.persist({ board_group_by: this.groupBy });
        this.render();
      });

      const sizePicker = root.querySelector('[data-role="card-size"]');
      sizePicker.value = this.cardSize;
      sizePicker.addEventListener("change", () => {
        this.cardSize = sizePicker.value;
        this.board.dataset.size = this.cardSize;
        this.ctx.persist({ board_card_size: this.cardSize });
      });
    }

    setFilter(value) {
      this.filter = value;
      this.render();
    }

    fieldLabel(field) {
      return field.charAt(0).toUpperCase() + field.slice(1);
    }

    visibleTasks() {
      if (!this.filter) return this.store.tasks.slice();
      const needle = this.filter.toLowerCase();
      return this.store.tasks.filter((task) =>
        ["activity", "category", "description", "status", "priority", "recurrence"]
          .some((key) => String(task[key] || "").toLowerCase().includes(needle))
        || String(task.id).includes(needle));
    }

    /** Column descriptors come from the definitions, so empty columns still show. */
    buildColumns(tasks) {
      if (this.groupBy === UNGROUPED) {
        return [{ key: UNGROUPED, label: "All tasks", color: null, tasks }];
      }

      const kind = BoardLayout.GROUPABLE[this.groupBy];
      const values = kind
        ? this.store.valuesFor(kind)
        : this.store.recurrence.map((rule) => rule.key);

      const buckets = new Map(values.map((value) => [value, []]));
      const spillover = new Map();
      const unset = [];

      for (const task of tasks) {
        const value = task[this.groupBy];
        if (!value) {
          unset.push(task);
        } else if (buckets.has(value)) {
          buckets.get(value).push(task);
        } else {
          // A value left over from a definition the user has since removed.
          if (!spillover.has(value)) spillover.set(value, []);
          spillover.get(value).push(task);
        }
      }

      const columns = values.map((value) => ({
        key: value,
        label: value,
        color: kind ? this.store.colorFor(kind, value) : null,
        tasks: buckets.get(value),
      }));

      for (const [value, list] of spillover) {
        columns.push({ key: value, label: `${value} (undefined)`, color: null, tasks: list });
      }
      if (unset.length) {
        columns.push({ key: EMPTY_BUCKET, label: "Unset", color: null, tasks: unset });
      }
      return columns;
    }

    statusSelect(task) {
      const options = ['<option value="">—</option>'].concat(
        this.store.valuesFor("status").map((value) =>
          `<option value="${escapeHtml(value)}"${value === task.status ? " selected" : ""}
           >${escapeHtml(value)}</option>`));
      const color = this.store.colorFor("status", task.status);
      const style = color ? ` style="color:${color};border-color:${color}"` : "";
      return `<select class="card-status" data-role="status" data-id="${task.id}"${style}
              >${options.join("")}</select>`;
    }

    cardHtml(task) {
      const title = task.activity || `Task ${task.id}`;
      const description = task.description
        ? `<div class="card-desc markdown" data-tooltip="${escapeHtml(task.description)}"
                data-tooltip-format="markdown">${this.markdown.render(task.description)}</div>`
        : '<div class="card-desc empty-desc">No description</div>';

      const blockers = (task.blocked_by || []).length + (task.missing_dependencies || []).length;
      const badge = blockers
        ? `<span class="card-badge" data-tooltip="Blocked by ${blockers} dependency(ies)"
                 data-tooltip-always>${blockers}\u00a0blocked</span>`
        : "";

      return `
        <article class="card" draggable="${this.canDrag()}" data-id="${task.id}">
          <header class="card-head">
            <span class="card-id">${task.id}</span>
            ${badge}
            <button class="card-jump" data-role="jump" data-id="${task.id}"
                    data-tooltip="Open this task in the table" data-tooltip-always
                    title="Open in table">&#8599;</button>
          </header>
          <h3 class="card-title" data-tooltip="${escapeHtml(title)}">${escapeHtml(title)}</h3>
          ${description}
          <footer class="card-foot">${this.statusSelect(task)}</footer>
        </article>`;
    }

    canDrag() {
      return this.groupBy !== UNGROUPED;
    }

    render() {
      if (!this.columnsHost) return;
      if (this.ctx.tooltip) this.ctx.tooltip.hide();

      const tasks = this.visibleTasks();
      const columns = this.buildColumns(tasks);

      this.columnsHost.dataset.mode = this.groupBy === UNGROUPED ? "grid" : "columns";
      this.columnsHost.innerHTML = columns.map((column) => `
        <section class="board-column" data-key="${escapeHtml(column.key)}">
          <header class="column-head">
            <span class="column-dot" style="background:${column.color || "var(--text-faint)"}"></span>
            <span class="column-title">${escapeHtml(column.label)}</span>
            <span class="column-count">${column.tasks.length}</span>
          </header>
          <div class="column-body" data-role="drop" data-key="${escapeHtml(column.key)}">
            ${column.tasks.map((task) => this.cardHtml(task)).join("")
              || '<p class="column-empty">Empty</p>'}
          </div>
        </section>`).join("");

      this.emptyState.hidden = tasks.length > 0;
      this.hint.textContent = this.canDrag()
        ? `Drag a card between columns to change its ${this.groupBy}.`
        : "";

      this.bindCards();
    }

    bindCards() {
      this.columnsHost.querySelectorAll('[data-role="status"]').forEach((select) => {
        select.addEventListener("change", () =>
          this.ctx.commit(Number(select.dataset.id), { status: select.value }));
      });

      this.columnsHost.querySelectorAll('[data-role="jump"]').forEach((button) => {
        button.addEventListener("click", () => this.ctx.focusTask(Number(button.dataset.id)));
      });

      if (!this.canDrag()) return;

      this.columnsHost.querySelectorAll(".card").forEach((card) => {
        card.addEventListener("dragstart", (event) => {
          this.dragging = Number(card.dataset.id);
          card.classList.add("dragging");
          event.dataTransfer.effectAllowed = "move";
          // Firefox refuses to start a drag without payload.
          event.dataTransfer.setData("text/plain", card.dataset.id);
        });
        card.addEventListener("dragend", () => {
          this.dragging = null;
          card.classList.remove("dragging");
          this.columnsHost.querySelectorAll(".column-body")
            .forEach((body) => body.classList.remove("drop-target"));
        });
      });

      this.columnsHost.querySelectorAll('[data-role="drop"]').forEach((body) => {
        body.addEventListener("dragover", (event) => {
          if (this.dragging === null) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          body.classList.add("drop-target");
        });
        body.addEventListener("dragleave", () => body.classList.remove("drop-target"));
        body.addEventListener("drop", (event) => {
          event.preventDefault();
          body.classList.remove("drop-target");
          if (this.dragging === null) return;

          const target = body.dataset.key;
          const value = target === EMPTY_BUCKET ? "" : target;
          const task = this.store.tasks.find((t) => t.id === this.dragging);
          const id = this.dragging;
          this.dragging = null;
          if (!task || task[this.groupBy] === value) return;
          this.ctx.commit(id, { [this.groupBy]: value });
        });
      });
    }
  }

  window.PlannerLayouts.BoardLayout = BoardLayout;

})();
