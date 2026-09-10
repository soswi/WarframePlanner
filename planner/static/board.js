"use strict";

// Wrapped in an IIFE: these files load as classic scripts and share one global
// lexical scope. Registers itself onto the existing PlannerLayouts namespace.
(function () {

  const { Layout, escapeHtml } = window.PlannerLayouts;
  const { Dropdown } = window.PlannerDropdown;

  const UNGROUPED = "\u0000none";
  const EMPTY_BUCKET = "\u0000empty";

  // Height of one implicit grid row. Groups span a whole number of these, which
  // is how a masonry-style pack is built out of an ordinary CSS grid: the
  // smaller the unit, the tighter the fit and the more rows the browser tracks.
  const ROW_UNIT_PX = 8;

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
      this.onResize = () => this.scheduleLayout();
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

      window.addEventListener("resize", this.onResize);

      Dropdown.enhanceAll(root.querySelector(".board-controls"));

      const sizePicker = root.querySelector('[data-role="card-size"]');
      sizePicker.value = this.cardSize;
      sizePicker.addEventListener("change", () => {
        this.cardSize = sizePicker.value;
        this.board.dataset.size = this.cardSize;
        this.ctx.persist({ board_card_size: this.cardSize });
        this.layoutGroups();
      });
    }

    unmount() {
      window.removeEventListener("resize", this.onResize);
      super.unmount();
    }

    scheduleLayout() {
      cancelAnimationFrame(this.layoutHandle);
      this.layoutHandle = requestAnimationFrame(() => this.layoutGroups());
    }

    /**
     * Size every group block on the shared grid.
     *
     * Flexbox could not do this: a flex line is as tall as its tallest item, so
     * a short group could never sit beside or underneath a taller neighbour.
     * A grid places each group wherever it fits, but only once the group
     * declares how many columns and rows it occupies — and the row count
     * depends on rendered height, which is why it is measured here rather than
     * expressed in CSS.
     */
    layoutGroups() {
      const host = this.columnsHost;
      if (!host || host.dataset.mode !== "groups") return;

      const hostStyle = window.getComputedStyle(host);
      const columnGap = parseFloat(hostStyle.columnGap) || 0;
      const rowGap = parseFloat(hostStyle.rowGap) || 0;
      const cardWidth =
        parseFloat(window.getComputedStyle(this.board).getPropertyValue("--card-w")) || 260;

      // How many card-width tracks actually fit right now. A group never spans
      // more than this, so a wide group folds onto more rows instead of
      // overflowing to the right.
      const available = Math.max(
        1, Math.floor((host.clientWidth + columnGap) / (cardWidth + columnGap)));

      host.querySelectorAll(".board-group").forEach((group) => {
        const count = Number(group.dataset.count) || 0;
        const side = Math.max(1, Math.ceil(Math.sqrt(count)));
        const span = Math.min(side, available);

        if (count) {
          // repeat() will not take its count from a custom property, so the
          // template is written out here with a literal.
          group.querySelector(".group-cards").style.gridTemplateColumns =
            `repeat(${span}, minmax(0, var(--card-w, 260px)))`;
        }

        group.style.gridColumn = `span ${span}`;
        // Cleared before measuring, or the previous span would be measured.
        group.style.gridRow = "";
        const height = group.getBoundingClientRect().height;
        const rows = Math.max(1, Math.ceil((height + rowGap) / (ROW_UNIT_PX + rowGap)));
        group.style.gridRow = `span ${rows}`;
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
      // store.tasks already arrives pinned-first, so pushing in order keeps
      // pinned cards at the front of whichever group they land in.
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

      // Empty groups sink to the end, keeping their relative order. They are
      // still rendered: an empty group is the drop target for moving the first
      // card into it.
      return columns
        .filter((column) => column.tasks.length)
        .concat(columns.filter((column) => !column.tasks.length));
    }

    statusSelect(task) {
      const options = ['<option value="">—</option>'].concat(
        this.store.valuesFor("status").map((value) => {
          const color = this.store.colorFor("status", value);
          return `<option value="${escapeHtml(value)}"${value === task.status ? " selected" : ""}
                          ${color ? `data-color="${color}"` : ""}>${escapeHtml(value)}</option>`;
        }));
      return `<select class="card-status" data-role="status" data-id="${task.id}"
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

      const accent = task.highlighted && this.store.highlightColor()
        ? ` style="--status-accent:${this.store.highlightColor()}"`
        : "";
      return `
        <article class="card${task.highlighted ? " is-pinned" : ""}"
                 draggable="${this.canDrag()}" data-id="${task.id}"${accent}>
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

    /**
     * Create a task that already belongs to this group.
     *
     * The API assigns the id, so the new task is found by diffing the snapshot
     * against the ids held before the call.
     */
    async addToGroup(key) {
      const before = new Set(this.store.tasks.map((task) => task.id));
      try {
        const snapshot = await this.ctx.api.createTask();
        const created = snapshot.tasks.find((task) => !before.has(task.id));
        const value = key === EMPTY_BUCKET ? "" : key;

        if (created && this.groupBy !== UNGROUPED && value) {
          // commit() applies the snapshot it gets back.
          this.ctx.commit(created.id, { [this.groupBy]: value });
        } else {
          this.store.apply(snapshot);
        }
      } catch (error) {
        this.ctx.toast.show(error.message, true);
      }
    }

    render() {
      if (!this.columnsHost) return;
      if (this.ctx.tooltip) this.ctx.tooltip.hide();

      const tasks = this.visibleTasks();
      const columns = this.buildColumns(tasks);

      const grouped = this.groupBy !== UNGROUPED;
      this.columnsHost.dataset.mode = grouped ? "groups" : "flat";

      this.columnsHost.innerHTML = columns.map((column) => {
        // Square-ish block: side length is the ceiling of the square root, so
        // 3 cards lay out 2x2, 5 lay out 3x3, 10 lay out 4x4. Any short final
        // row stays left-aligned, leaving the gaps on the right.
        // Column and row spans are applied by layoutGroups() once the block has
        // been measured; the markup only carries the card count it needs.
        return `
        <section class="board-group" data-key="${escapeHtml(column.key)}"
                 data-count="${column.tasks.length}">
          <header class="column-head">
            <span class="column-dot" style="background:${column.color || "var(--text-faint)"}"></span>
            <span class="column-title">${escapeHtml(column.label)}</span>
            <span class="column-count">${column.tasks.length}</span>
          </header>
          <div class="group-cards${column.tasks.length ? "" : " is-empty"}"
               data-role="drop" data-key="${escapeHtml(column.key)}">
            ${column.tasks.map((task) => this.cardHtml(task)).join("")
              || `<button class="column-add" type="button" data-role="add-here"
                          data-key="${escapeHtml(column.key)}">
                    <span class="plus">+</span>Add
                  </button>`}
          </div>
        </section>`;
      }).join("");

      this.emptyState.hidden = tasks.length > 0;
      this.hint.textContent = this.canDrag()
        ? `Drag a card between columns to change its ${this.groupBy}.`
        : "";

      this.bindCards();
      Dropdown.enhanceAll(this.columnsHost);
      this.layoutGroups();
    }

    bindCards() {
      this.columnsHost.querySelectorAll('[data-role="status"]').forEach((select) => {
        const id = Number(select.dataset.id);
        // Wheel stepping lives in the dropdown component and arrives here as a
        // normal change event. The write is deferred, so the card does not jump
        // between groups mid-scroll.
        select.addEventListener("change", () => this.ctx.commitDelayed(id, { status: select.value }));
      });

      this.columnsHost.querySelectorAll('[data-role="jump"]').forEach((button) => {
        button.addEventListener("click", () => this.ctx.focusTask(Number(button.dataset.id)));
      });

      this.columnsHost.querySelectorAll('[data-role="add-here"]').forEach((button) => {
        button.addEventListener("click", () => this.addToGroup(button.dataset.key));
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
          this.columnsHost.querySelectorAll(".group-cards")
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
