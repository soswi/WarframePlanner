const SAFE_SCHEME = /^(https?:|mailto:)/i;

/**
 * A deliberately small Markdown subset, written in-house so the executable
 * stays dependency-free.
 *
 * Security model: the source is HTML-escaped before any rule runs, and rules
 * only ever emit tags they construct themselves. Raw HTML in the input is
 * therefore inert, and link targets are scheme-checked.
 *
 * Supported: headings, bullet and ordered lists, blockquotes, fenced and
 * inline code, horizontal rules, bold, italic, strikethrough, links.
 *
 * Extending: push onto `inlineRules` for new span-level syntax, or add a
 * branch in `renderBlocks` for new block-level syntax.
 */
export class MarkdownRenderer {
  constructor() {
    this.inlineRules = [
      { pattern: /\*\*([^*]+)\*\*/g, replace: "<strong>$1</strong>" },
      { pattern: /(^|[^*])\*([^*\n]+)\*/g, replace: "$1<em>$2</em>" },
      { pattern: /(^|[^_])_([^_\n]+)_/g, replace: "$1<em>$2</em>" },
      { pattern: /~~([^~]+)~~/g, replace: "<del>$1</del>" },
    ];
    this.codeStore = [];
  }

  static escape(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  render(source) {
    if (!source) return "";
    this.codeStore = [];
    let text = MarkdownRenderer.escape(source).replace(/\r\n?/g, "\n");
    text = this.stashCode(text);
    const html = this.renderBlocks(text);
    return this.restoreCode(html);
  }

  /** Pull code out first so no inline rule can rewrite its contents. */
  stashCode(text) {
    text = text.replace(/```([\s\S]*?)```/g, (_, body) =>
      this.park(`<pre class="md-pre"><code>${body.replace(/^\n/, "")}</code></pre>`, true));
    return text.replace(/`([^`\n]+)`/g, (_, body) =>
      this.park(`<code class="md-code">${body}</code>`, false));
  }

  park(html, isBlock) {
    this.codeStore.push(html);
    const token = `\u0000MD${this.codeStore.length - 1}\u0000`;
    return isBlock ? `\n${token}\n` : token;
  }

  restoreCode(html) {
    return html.replace(/\u0000MD(\d+)\u0000/g, (_, index) => this.codeStore[Number(index)]);
  }

  renderBlocks(text) {
    const lines = text.split("\n");
    const out = [];
    let paragraph = [];
    let list = null;

    const flushParagraph = () => {
      if (!paragraph.length) return;
      out.push(`<p>${this.renderInline(paragraph.join("<br>"))}</p>`);
      paragraph = [];
    };

    const flushList = () => {
      if (!list) return;
      const items = list.items.map((item) => `<li>${this.renderInline(item)}</li>`).join("");
      out.push(`<${list.tag}>${items}</${list.tag}>`);
      list = null;
    };

    const flushAll = () => { flushParagraph(); flushList(); };

    for (const raw of lines) {
      const line = raw.trimEnd();

      if (/^\u0000MD\d+\u0000$/.test(line.trim())) {
        flushAll();
        out.push(line.trim());
        continue;
      }
      if (!line.trim()) { flushAll(); continue; }

      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushAll();
        const level = heading[1].length + 2;
        out.push(`<h${level} class="md-h">${this.renderInline(heading[2])}</h${level}>`);
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
        flushAll();
        out.push('<hr class="md-hr">');
        continue;
      }

      const quote = line.match(/^&gt;\s?(.*)$/);
      if (quote) {
        flushAll();
        out.push(`<blockquote class="md-quote">${this.renderInline(quote[1])}</blockquote>`);
        continue;
      }

      const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (bullet || ordered) {
        flushParagraph();
        const tag = bullet ? "ul" : "ol";
        if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
        list.items.push((bullet || ordered)[1]);
        continue;
      }

      flushList();
      paragraph.push(line);
    }

    flushAll();
    return out.join("");
  }

  renderInline(text) {
    let out = text;
    out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, href) => {
      if (!SAFE_SCHEME.test(href)) return match;
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    for (const rule of this.inlineRules) {
      out = out.replace(rule.pattern, rule.replace);
    }
    return out;
  }

  /** Plain-text projection, used when a preview must stay unstyled. */
  toPlainText(source) {
    if (!source) return "";
    return String(source)
      .replace(/```[\s\S]*?```/g, " [code] ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/^\s*[-*+]\s+/gm, "• ")
      .replace(/^\s*#{1,4}\s+/gm, "")
      .replace(/^\s*&gt;\s?/gm, "")
      .replace(/[*_~]/g, "")
      .trim();
  }
}
