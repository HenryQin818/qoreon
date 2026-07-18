    // Markdown rendering and interactive message-object viewer utilities.
    function truncateText(text, maxLen) {
      const t = String(text || "").trim();
      if (t.length <= maxLen) return t;
      return t.substring(0, maxLen) + "...";
    }

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function mdInline(raw) {
      let s = escapeHtml(raw || "");
      const stash = [];
      const stashPush = (html) => {
        stash.push(String(html || ""));
        return "\u0000" + (stash.length - 1) + "\u0000";
      };
      s = s.replace(/`([^`]+)`/g, (_, code) => {
        return stashPush("<code>" + code + "</code>");
      });
      s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => {
        const u = normalizeMarkdownLinkTarget(url);
        if (!u) return text;
        if (/^https?:\/\//i.test(u)) {
          return stashPush('<a href="' + escapeHtml(u) + '" target="_blank" rel="noopener noreferrer">' + text + "</a>");
        }
        const obj = classifyMessageObjectToken(u);
        if (!obj) return text;
        return stashPush(
          '<a href="' + escapeHtml(u) + '" data-msg-object-href="' + escapeHtml(u) + '">' + text + "</a>"
        );
      });
      s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]+)/g, (_, pre, url) => {
        return pre + stashPush('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>");
      });
      s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
      s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
      s = s.replace(/(^|[^\*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
      s = s.replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
      s = s.replace(/\u0000(\d+)\u0000/g, (_, idx) => stash[Number(idx)] || "");
      return s;
    }

    function normalizeMarkdownLinkTarget(raw) {
      let u = String(raw || "").trim();
      if (!u) return "";
      u = u
        .replace(/^&lt;([\s\S]*)&gt;$/i, "$1")
        .replace(/^<([\s\S]*)>$/, "$1")
        .trim();
      return u
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, "\"")
        .replace(/&#39;/g, "'");
    }

    function splitMarkdownTableCells(raw) {
      let line = String(raw || "").trim();
      if (!line.includes("|")) return [];
      if (line.startsWith("|")) line = line.slice(1);
      if (line.endsWith("|")) line = line.slice(0, -1);
      const cells = [];
      let cell = "";
      let escaped = false;
      let inCode = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (escaped) {
          cell += ch;
          escaped = false;
          continue;
        }
        if (ch === "\\") {
          escaped = true;
          continue;
        }
        if (ch === "`") inCode = !inCode;
        if (ch === "|" && !inCode) {
          cells.push(cell.trim());
          cell = "";
          continue;
        }
        cell += ch;
      }
      if (escaped) cell += "\\";
      cells.push(cell.trim());
      return cells;
    }

    function parseMarkdownTableDivider(raw) {
      const cells = splitMarkdownTableCells(raw);
      if (cells.length < 2) return null;
      const alignments = [];
      for (const cell of cells) {
        const token = String(cell || "").replace(/\s+/g, "");
        if (!/^:?-{3,}:?$/.test(token)) return null;
        if (token.startsWith(":") && token.endsWith(":")) alignments.push("center");
        else if (token.endsWith(":")) alignments.push("right");
        else alignments.push("left");
      }
      return alignments;
    }

    function isMarkdownTableStart(lines, idx) {
      if (!Array.isArray(lines) || idx < 0 || idx + 1 >= lines.length) return false;
      const header = splitMarkdownTableCells(lines[idx]);
      const alignments = parseMarkdownTableDivider(lines[idx + 1]);
      return !!(header.length >= 2 && alignments && alignments.length >= 2);
    }

    function markdownTableCellHtml(tag, value, align) {
      const cls = align ? (' class="md-table-align-' + escapeHtml(align) + '"') : "";
      return "<" + tag + cls + ">" + mdInline(String(value || "")) + "</" + tag + ">";
    }

    function renderMarkdownTable(lines, startIdx) {
      const headers = splitMarkdownTableCells(lines[startIdx]);
      const alignments = parseMarkdownTableDivider(lines[startIdx + 1]) || [];
      const width = Math.max(headers.length, alignments.length);
      const rows = [];
      let idx = startIdx + 2;
      while (idx < lines.length) {
        const raw = String(lines[idx] || "");
        const t = raw.trim();
        if (!t || !t.includes("|")) break;
        if (parseMarkdownTableDivider(t)) break;
        const cells = splitMarkdownTableCells(t);
        if (cells.length < 2) break;
        rows.push(cells);
        idx += 1;
      }
      const normalizedHeaders = headers.slice();
      while (normalizedHeaders.length < width) normalizedHeaders.push("");
      const head = normalizedHeaders
        .slice(0, width)
        .map((cell, cellIdx) => markdownTableCellHtml("th", cell, alignments[cellIdx] || "left"))
        .join("");
      const body = rows
        .map((cells) => {
          const normalizedCells = cells.slice();
          while (normalizedCells.length < width) normalizedCells.push("");
          return "<tr>" + normalizedCells
            .slice(0, width)
            .map((cell, cellIdx) => markdownTableCellHtml("td", cell, alignments[cellIdx] || "left"))
            .join("") + "</tr>";
        })
        .join("");
      return {
        html: '<div class="md-table-wrap"><table class="md-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + "</tbody></table></div>",
        nextIdx: idx,
      };
    }

    function renderMarkdownListItem(raw) {
      const text = String(raw || "").trim();
      const task = text.match(/^\[([ xX])\]\s+(.*)$/);
      if (task) {
        const checked = task[1].toLowerCase() === "x" ? " checked" : "";
        return '<li class="md-task-item"><input type="checkbox" disabled' + checked + "><span>" + mdInline(task[2]) + "</span></li>";
      }
      return "<li>" + mdInline(text) + "</li>";
    }

    function renderMarkdownCodeBlock(lines, lang) {
      const safeLang = String(lang || "").trim().replace(/[^\w-]/g, "").slice(0, 32);
      const langAttr = safeLang ? (' data-lang="' + escapeHtml(safeLang) + '"') : "";
      const codeClass = safeLang ? (' class="language-' + escapeHtml(safeLang) + '"') : "";
      return '<pre class="md-code"' + langAttr + "><code" + codeClass + ">" + escapeHtml(lines.join("\n")) + "</code></pre>";
    }

    function markdownToHtml(input) {
      const src = String(input || "").replace(/\r\n?/g, "\n");
      if (!src.trim()) return "";
      const lines = src.split("\n");
      const out = [];
      let paragraph = [];
      let listType = "";
      let listItems = [];
      let inCode = false;
      let codeLines = [];
      let codeLang = "";
      let quoteLines = [];

      function flushParagraph() {
        if (!paragraph.length) return;
        const text = paragraph.join("\n").trim();
        paragraph = [];
        if (!text) return;
        out.push("<p>" + mdInline(text).replace(/\n/g, "<br>") + "</p>");
      }
      function flushList() {
        if (!listItems.length || !listType) return;
        out.push("<" + listType + ' class="md-list">' + listItems.map((x) => renderMarkdownListItem(x)).join("") + "</" + listType + ">");
        listType = "";
        listItems = [];
      }
      function flushBlockquote() {
        if (!quoteLines.length) return;
        const text = quoteLines.join("\n").trim();
        quoteLines = [];
        if (!text) return;
        out.push("<blockquote>" + mdInline(text).replace(/\n/g, "<br>") + "</blockquote>");
      }
      function flushNormal() {
        flushParagraph();
        flushList();
        flushBlockquote();
      }

      for (let lineIdx = 0; lineIdx < lines.length; lineIdx += 1) {
        const ln = lines[lineIdx];
        const line = String(ln || "");
        if (inCode) {
          if (/^```/.test(line.trim())) {
            out.push(renderMarkdownCodeBlock(codeLines, codeLang));
            inCode = false;
            codeLines = [];
            codeLang = "";
          } else {
            codeLines.push(line);
          }
          continue;
        }

        const codeFence = line.trim().match(/^```([\w-]+)?\s*$/);
        if (codeFence) {
          flushNormal();
          inCode = true;
          codeLines = [];
          codeLang = codeFence[1] || "";
          continue;
        }

        const t = line.trim();
        if (!t) {
          flushNormal();
          continue;
        }

        if (/^[-*_]{3,}\s*$/.test(t)) {
          flushNormal();
          out.push('<hr class="md-hr">');
          continue;
        }

        if (isMarkdownTableStart(lines, lineIdx)) {
          flushNormal();
          const table = renderMarkdownTable(lines, lineIdx);
          out.push(table.html);
          lineIdx = Math.max(lineIdx, table.nextIdx - 1);
          continue;
        }

        let m = t.match(/^(#{1,6})\s+(.*)$/);
        if (m) {
          flushNormal();
          const lv = Math.min(6, Math.max(1, m[1].length));
          out.push("<h" + lv + ">" + mdInline(m[2]) + "</h" + lv + ">");
          continue;
        }

        m = t.match(/^[-*+]\s+(.*)$/);
        if (m) {
          flushParagraph();
          if (listType && listType !== "ul") flushList();
          listType = "ul";
          listItems.push(m[1]);
          continue;
        }

        m = t.match(/^\d+\.\s+(.*)$/);
        if (m) {
          flushParagraph();
          if (listType && listType !== "ol") flushList();
          listType = "ol";
          listItems.push(m[1]);
          continue;
        }

        m = t.match(/^>\s?(.*)$/);
        if (m) {
          flushParagraph();
          flushList();
          quoteLines.push(m[1]);
          continue;
        }

        if (listItems.length) flushList();
        if (quoteLines.length) flushBlockquote();
        paragraph.push(line);
      }

      flushNormal();
      if (inCode) out.push(renderMarkdownCodeBlock(codeLines, codeLang));
      return out.join("");
    }

    function enhanceMarkdownTypedBlocks(root) {
      if (!root || !root.querySelectorAll) return;
      Array.from(root.querySelectorAll("pre.md-code")).forEach((block) => {
        if (!block || block.__markdownCopyEnhanced) return;
        const code = block.querySelector("code");
        const copyValue = () => String((code || block).textContent || "");
        block.__markdownCopyEnhanced = true;
        block.classList.add("md-code-copyable");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "md-block-copy";
        btn.setAttribute("aria-label", "复制代码块内容");
        btn.setAttribute("title", "复制");
        btn.innerHTML = '<span class="md-block-copy-mark" aria-hidden="true"></span><span class="md-block-copy-feedback" aria-live="polite">已复制</span>';
        let timer = 0;
        btn.addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          const text = copyValue();
          if (!text) return;
          const ok = typeof copyText === "function" ? await copyText(text) : false;
          window.clearTimeout(timer);
          btn.classList.toggle("copied", !!ok);
          btn.classList.toggle("failed", !ok);
          block.classList.toggle("is-copying", !!ok);
          const feedback = btn.querySelector(".md-block-copy-feedback");
          if (feedback) feedback.textContent = ok ? "已复制" : "复制失败";
          timer = window.setTimeout(() => {
            btn.classList.remove("copied", "failed");
            block.classList.remove("is-copying");
          }, ok ? 1300 : 1800);
        });
        block.appendChild(btn);
      });
    }

    function setMarkdown(elNode, text, fallback = "") {
      if (!elNode) return;
      const src = String(text || "").trim() ? String(text || "") : String(fallback || "");
      elNode.innerHTML = markdownToHtml(src);
      enhanceMarkdownTypedBlocks(elNode);
      if (typeof enhanceMessageInteractiveObjects === "function") {
        enhanceMessageInteractiveObjects(elNode, { force: true });
      }
    }

    const MESSAGE_OBJECT_TOKEN_RE = /(https?:\/\/[^\s<>"']+|\/share\/[^\s<>"']+|\/\.runs\/[^\s<>"']+|\/(?:Users|Volumes|private|tmp|var|opt|Applications|Library|System)[^\s<>"']+|\/(?:产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/[^\s<>"']+)+|(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run)(?:\/[^\s<>"']+)+|(?:[\u4e00-\u9fa5A-Za-z0-9_.（）()【】「」《》#&+·-]+(?:[／-][\u4e00-\u9fa5A-Za-z0-9_.（）()【】「」《》#&+·-]+)*\/(?:产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/[^\s<>"']+)+)|(?:产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/[^\s<>"']+)+)/g;
    const MESSAGE_OBJECT_CHANNEL_RELATIVE_ROOT_RE = /^(?:\/?产出物(?:\/(?:材料|沉淀|证据|附件|图片|截图|文档|草稿|临时))?|\/?(?:材料|沉淀|证据|附件|图片|截图|文档|草稿|临时)|\/?(?:任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档))(?:\/.+)+$/;
    const MESSAGE_OBJECT_FILE_EXT_BOUNDARY_RE = /\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)(?:[?#][^\s<>"']*)?(?=$|[\s),.;:!?，。；：！？、」』】》〉])/i;
    const MESSAGE_OBJECT_EXTENDABLE_PATH_ROOT_RE = /^(?:\/(?:Users|Volumes|private|tmp|var|opt|Applications|Library|System|产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/|$)|(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run|产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/|$)|[\u4e00-\u9fa5A-Za-z0-9_.（）()【】「」《》#&+·-]+(?:[／-][\u4e00-\u9fa5A-Za-z0-9_.（）()【】「」《》#&+·-]+)*\/(?:产出物|材料|沉淀|证据|附件|图片|截图|文档|草稿|临时|任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档)(?:\/|$))/;
    const MESSAGE_OBJECT_EXTENDED_FORBIDDEN_RE = /[<>"'`]/;
    const MESSAGE_OBJECT_PATH_LINE_SUFFIX_RE = /^(.*\.(?:md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)):(\d+)(?::(\d+))?$/i;
    const MESSAGE_OBJECT_TRAILING_PUNCT_RE = /[),.;:!?，。；：！？、」』】》〉]+$/;
    const MESSAGE_OBJECT_RELATIVE_ROOT_RE = /^(?:web|docs|tests|static_sites|task_dashboard|任务规划|\.runs|\.run)(?:\/.+)+$/;
    const MESSAGE_OBJECT_PROJECT_CHANNEL_PREFIX_RE = /^([^/]+)\/((?:产出物(?:\/(?:材料|沉淀|证据|附件|图片|截图|文档|草稿|临时))?|(?:材料|沉淀|证据|附件|图片|截图|文档|草稿|临时)|(?:任务|问题|反馈|答复|讨论空间|已完成|暂缓|归档))(?:\/.+)+)$/;
    const MESSAGE_OBJECT_VIEWER = {
      open: false,
      loading: false,
      target: null,
      item: null,
      error: "",
      history: [],
      requestSeq: 0,
    };
    let TASK_DASHBOARD_ROOT_PATH_CACHE = "";

    function trimMessageObjectToken(raw) {
      const src = String(raw || "");
      if (!src) return { core: "", tail: "" };
      const tailMatch = src.match(MESSAGE_OBJECT_TRAILING_PUNCT_RE);
      if (!tailMatch) return { core: src, tail: "" };
      const tail = String(tailMatch[0] || "");
      return {
        core: src.slice(0, src.length - tail.length),
        tail,
      };
    }

    function isLikelyWorkspaceRelativePath(token) {
      return MESSAGE_OBJECT_RELATIVE_ROOT_RE.test(String(token || "").trim());
    }

    function normalizeMessageObjectProjectLike(raw) {
      return (raw && typeof raw === "object") ? raw : {};
    }

    function messageObjectCurrentProjectId() {
      try {
        if (typeof currentConversationCtx === "function") {
          const ctx = currentConversationCtx();
          const pid = String((ctx && ctx.projectId) || "").trim();
          if (pid) return pid;
        }
      } catch (_) {}
      return String((typeof STATE !== "undefined" && STATE && STATE.project) || "").trim();
    }

    function messageObjectCurrentChannelName() {
      try {
        if (typeof currentConversationCtx === "function") {
          const ctx = currentConversationCtx();
          const ch = String((ctx && ctx.channelName) || "").trim();
          if (ch) return ch;
        }
      } catch (_) {}
      try {
        if (typeof findConversationSessionById === "function" && typeof STATE !== "undefined" && STATE && STATE.selectedSessionId) {
          const session = findConversationSessionById(STATE.selectedSessionId);
          const ch = String((session && (session.channel_name || session.channelName || session.primaryChannel)) || "").trim();
          if (ch) return ch;
        }
      } catch (_) {}
      return String((typeof STATE !== "undefined" && STATE && STATE.channel) || "").trim();
    }

    function messageObjectProjectById(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid) return null;
      try {
        if (typeof projectById === "function") {
          const project = projectById(pid);
          if (project) return project;
        }
      } catch (_) {}
      const projects = (typeof DATA !== "undefined" && DATA && Array.isArray(DATA.projects)) ? DATA.projects : [];
      return projects.find((project) => String((project && project.id) || "") === pid) || null;
    }

    function messageObjectExecutionContextWorktreeRoot(project) {
      const proj = normalizeMessageObjectProjectLike(project);
      const context = normalizeMessageObjectProjectLike(proj.project_execution_context || proj.projectExecutionContext || proj.execution_context || proj.executionContext);
      const target = normalizeMessageObjectProjectLike(context.target || context.target_ref || context.targetRef);
      const source = normalizeMessageObjectProjectLike(context.source || context.source_ref || context.sourceRef);
      return firstNonEmptyText([
        target.worktree_root,
        target.worktreeRoot,
        source.worktree_root,
        source.worktreeRoot,
        context.worktree_root,
        context.worktreeRoot,
        proj.worktree_root,
        proj.worktreeRoot,
      ]);
    }

    function messageObjectProjectRootPath(projectId) {
      const pid = String(projectId || messageObjectCurrentProjectId() || "").trim();
      if (!pid || pid === "overview") return "";
      const project = messageObjectProjectById(pid);
      const contextRoot = messageObjectExecutionContextWorktreeRoot(project);
      if (contextRoot && contextRoot[0] === "/") return contextRoot.replace(/\/+$/, "");
      try {
        if (typeof resolveProjectRootPath === "function") {
          const resolved = String(resolveProjectRootPath(pid) || "").trim();
          if (resolved && resolved[0] === "/") return resolved.replace(/\/+$/, "");
        }
      } catch (_) {}
      const directRoot = firstNonEmptyText([
        project && project.project_root_abs,
        project && project.projectRootAbs,
        project && project.project_root,
        project && project.projectRoot,
      ]);
      if (directRoot && directRoot[0] === "/") return directRoot.replace(/\/+$/, "");
      const taskRoot = String((project && (project.task_root_rel || project.taskRootRel)) || "").trim();
      if (taskRoot && taskRoot[0] === "/") {
        const compact = taskRoot.replace(/\/+$/, "");
        const marker = "/任务规划";
        if (compact.endsWith(marker)) return compact.slice(0, compact.length - marker.length).replace(/\/+$/, "");
      }
      return "";
    }

    function normalizeMessageObjectChannelKey(raw) {
      let src = String(raw || "").trim();
      if (!src) return "";
      try {
        src = src.normalize("NFKC");
      } catch (_) {}
      return src
        .replace(/[\\／]+/g, "/")
        .replace(/\s*\/\s*/g, "/")
        .replace(/\s+/g, "")
        .replace(/體/g, "体")
        .replace(/題/g, "题")
        .toLowerCase();
    }

    function messageObjectProjectTaskRootPath(projectId) {
      const pid = String(projectId || messageObjectCurrentProjectId() || "").trim();
      if (!pid || pid === "overview") return "";
      const project = messageObjectProjectById(pid);
      const root = messageObjectProjectRootPath(pid);
      const taskRoot = String((project && (project.task_root_abs || project.taskRootAbs || project.task_root || project.taskRoot || project.task_root_rel || project.taskRootRel)) || "").trim();
      if (taskRoot && taskRoot[0] === "/") return taskRoot.replace(/\/+$/, "");
      if (!root) return "";
      const projectRootRel = String((project && (project.project_root_rel || project.projectRootRel)) || "").trim().replace(/^\/+|\/+$/g, "");
      const compactTaskRoot = taskRoot.replace(/^\/+|\/+$/g, "");
      if (projectRootRel && compactTaskRoot && (compactTaskRoot === projectRootRel || compactTaskRoot.startsWith(projectRootRel + "/"))) {
        const rest = compactTaskRoot.slice(projectRootRel.length).replace(/^\/+/, "");
        return (root.replace(/\/+$/, "") + (rest ? ("/" + rest) : "")).replace(/\/+$/, "");
      }
      const marker = "/任务规划";
      const idx = compactTaskRoot.indexOf(marker.replace(/^\//, ""));
      if (idx >= 0) {
        const rest = compactTaskRoot.slice(idx).replace(/^\/+/, "");
        return (root.replace(/\/+$/, "") + "/" + rest).replace(/\/+$/, "");
      }
      return root.replace(/\/+$/, "") + "/任务规划";
    }

    function messageObjectChannelCandidates(project) {
      const proj = normalizeMessageObjectProjectLike(project);
      const out = [];
      const push = (value) => {
        const text = String(value || "").trim();
        if (text && !out.includes(text)) out.push(text);
      };
      const fromRows = (rows) => {
        if (!Array.isArray(rows)) return;
        rows.forEach((row) => {
          if (!row || typeof row !== "object") return;
          push(row.name);
          push(row.channel_name);
          push(row.channelName);
          push(row.primaryChannel);
        });
      };
      fromRows(proj.channels);
      fromRows(proj.channel_sessions);
      fromRows(proj.sessions);
      fromRows(proj.sessions_json);
      return out;
    }

    function resolveMessageObjectConfiguredChannelName(project, channelName) {
      const ch = String(channelName || "").trim();
      if (!ch) return "";
      const channels = messageObjectChannelCandidates(project);
      if (channels.includes(ch)) return ch;
      const key = normalizeMessageObjectChannelKey(ch);
      if (!key) return ch;
      return channels.find((name) => normalizeMessageObjectChannelKey(name) === key) || ch;
    }

    function messageObjectCurrentSessionLike() {
      const sid = String((typeof STATE !== "undefined" && STATE && STATE.selectedSessionId) || "").trim();
      if (!sid) return null;
      try {
        if (typeof findConversationSessionById === "function") {
          const session = findConversationSessionById(sid);
          if (session) return session;
        }
      } catch (_) {}
      return null;
    }

    function inferMessageObjectChannelRootFromPath(path, channelName, taskRoot) {
      const p = String(path || "").trim().replace(/\/+$/, "");
      const chKey = normalizeMessageObjectChannelKey(channelName);
      if (!p || !chKey) return "";
      const segs = p.split("/").filter(Boolean);
      const taskIdx = segs.lastIndexOf("任务规划");
      if (taskIdx < 0 || taskIdx + 1 >= segs.length) return "";
      const dir = String(segs[taskIdx + 1] || "").trim();
      if (!dir || normalizeMessageObjectChannelKey(dir) !== chKey) return "";
      if (p[0] === "/") return "/" + segs.slice(0, taskIdx + 2).join("/");
      if (taskRoot) return taskRoot.replace(/\/+$/, "") + "/" + dir;
      return segs.slice(0, taskIdx + 2).join("/");
    }

    function messageObjectChannelRootFromCurrentSession(projectId, channelName) {
      const session = messageObjectCurrentSessionLike();
      if (!session) return "";
      const context = normalizeMessageObjectProjectLike(session.project_execution_context || session.projectExecutionContext);
      const target = normalizeMessageObjectProjectLike(context.target || context.target_ref || context.targetRef);
      const source = normalizeMessageObjectProjectLike(context.source || context.source_ref || context.sourceRef);
      const taskRoot = messageObjectProjectTaskRootPath(projectId);
      const workdir = firstNonEmptyText([
        target.workdir,
        target.work_dir,
        source.workdir,
        source.work_dir,
        session.workdir,
        session.work_dir,
      ]);
      return inferMessageObjectChannelRootFromPath(workdir, channelName, taskRoot);
    }

    function messageObjectItemsForProject(projectId) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      try {
        if (typeof itemsForProject === "function") {
          const items = itemsForProject(pid);
          if (Array.isArray(items) && items.length) return items;
        }
      } catch (_) {}
      const items = (typeof DATA !== "undefined" && DATA && Array.isArray(DATA.items)) ? DATA.items : [];
      return items.filter((it) => String((it && it.project_id) || "").trim() === pid);
    }

    function messageObjectChannelRootFromItems(projectId, channelName) {
      const taskRoot = messageObjectProjectTaskRootPath(projectId);
      const items = messageObjectItemsForProject(projectId);
      for (const it of items) {
        const inferred = inferMessageObjectChannelRootFromPath(it && it.path, channelName, taskRoot);
        if (inferred) return inferred;
      }
      return "";
    }

    function messageObjectChannelRootPath(projectId, channelName) {
      const pid = String(projectId || messageObjectCurrentProjectId() || "").trim();
      const ch = String(channelName || messageObjectCurrentChannelName() || "").trim();
      if (!pid || pid === "overview" || !ch) return "";
      const project = messageObjectProjectById(pid);
      const configuredChannel = resolveMessageObjectConfiguredChannelName(project, ch);
      const sessionRoot = messageObjectChannelRootFromCurrentSession(pid, configuredChannel) || messageObjectChannelRootFromCurrentSession(pid, ch);
      if (sessionRoot) return sessionRoot;
      const itemRoot = messageObjectChannelRootFromItems(pid, configuredChannel) || messageObjectChannelRootFromItems(pid, ch);
      if (itemRoot) return itemRoot;
      const taskRoot = messageObjectProjectTaskRootPath(pid);
      if (!taskRoot) return "";
      const fallbackChannel = configuredChannel.includes("/") ? configuredChannel.replace(/\s*\/\s*/g, "／") : configuredChannel;
      return taskRoot.replace(/\/+$/, "") + "/" + fallbackChannel.replace(/^\/+|\/+$/g, "");
    }

    function normalizeMessageObjectChannelRelativePath(raw) {
      let src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(raw)).trim();
      if (!src) return "";
      src = src.replace(/^\/+/, "");
      if (!src || !MESSAGE_OBJECT_CHANNEL_RELATIVE_ROOT_RE.test(src)) return "";
      if (/^(?:材料|沉淀|证据|附件|图片|截图|文档|草稿|临时)(?:\/|$)/.test(src)) {
        return "产出物/" + src.replace(/^\/+/, "");
      }
      return src;
    }

    function isLikelyChannelRelativePath(token) {
      return !!normalizeMessageObjectChannelRelativePath(token);
    }

    function resolveMessageObjectChannelRelativePath(path) {
      const rel = normalizeMessageObjectChannelRelativePath(path);
      if (!rel) return "";
      const channelRoot = messageObjectChannelRootPath();
      if (!channelRoot) return rel;
      return channelRoot.replace(/\/+$/, "") + "/" + rel.replace(/^\/+/, "");
    }

    function resolveMessageObjectProjectChannelName(project, channelName) {
      const raw = String(channelName || "").trim();
      if (!raw) return "";
      const channels = messageObjectChannelCandidates(project);
      const key = normalizeMessageObjectChannelKey(raw);
      if (!key) return "";
      const configured = channels.find((name) => normalizeMessageObjectChannelKey(name) === key);
      if (configured) return configured;
      const current = messageObjectCurrentChannelName();
      if (current && normalizeMessageObjectChannelKey(current) === key) return current;
      return "";
    }

    function resolveMessageObjectProjectChannelPrefixedPath(path) {
      const src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(path)).trim().replace(/^\/+/, "");
      if (!src) return "";
      const match = src.match(MESSAGE_OBJECT_PROJECT_CHANNEL_PREFIX_RE);
      if (!match) return "";
      const channelPrefix = String(match[1] || "").trim();
      const relPath = String(match[2] || "").trim();
      if (!channelPrefix || !relPath) return "";
      const pid = messageObjectCurrentProjectId();
      if (!pid || pid === "overview") return "";
      const project = messageObjectProjectById(pid);
      const channelName = resolveMessageObjectProjectChannelName(project, channelPrefix);
      if (!channelName) return "";
      const taskRoot = messageObjectProjectTaskRootPath(pid);
      if (!taskRoot) return "";
      const channelDir = channelName.includes("/") ? channelName.replace(/\s*\/\s*/g, "／") : channelName;
      return taskRoot.replace(/\/+$/, "") + "/" + channelDir.replace(/^\/+|\/+$/g, "") + "/" + relPath.replace(/^\/+/, "");
    }

    function isLikelyProjectChannelPrefixedPath(token) {
      return !!resolveMessageObjectProjectChannelPrefixedPath(token);
    }

    function guessTaskDashboardRootPath() {
      if (TASK_DASHBOARD_ROOT_PATH_CACHE) return TASK_DASHBOARD_ROOT_PATH_CACHE;
      try {
        if (typeof resolveProjectRootPath === "function") {
          const direct = String(resolveProjectRootPath("task_dashboard") || resolveProjectRootPath(STATE.project) || "").trim();
          if (direct) {
            TASK_DASHBOARD_ROOT_PATH_CACHE = direct.replace(/\/+$/, "");
            return TASK_DASHBOARD_ROOT_PATH_CACHE;
          }
        }
      } catch (_) {}
      const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
      for (const proj of projects) {
        const items = Array.isArray(proj && proj.items) ? proj.items : [];
        for (const it of items) {
          const p = String((it && it.path) || "").trim();
          if (!p || p[0] !== "/") continue;
          const idx = p.lastIndexOf("/task-dashboard/");
          if (idx >= 0) {
            TASK_DASHBOARD_ROOT_PATH_CACHE = p.slice(0, idx + "/task-dashboard".length);
            return TASK_DASHBOARD_ROOT_PATH_CACHE;
          }
        }
      }
      return "";
    }

    function decodeMessageObjectFsPath(raw) {
      let src = String(raw || "").trim();
      if (!src || src.indexOf("%") < 0) return src;
      for (let i = 0; i < 2; i += 1) {
        try {
          const next = decodeURIComponent(src);
          if (!next || next === src) break;
          src = next;
          continue;
        } catch (_) {}
        try {
          const next = decodeURI(src);
          if (!next || next === src) break;
          src = next;
        } catch (_) {}
        break;
      }
      return src;
    }

    function stripMessageObjectPathLineSuffix(raw) {
      const src = String(raw || "").trim();
      if (!src || src.indexOf(":") < 0) return src;
      const match = src.match(MESSAGE_OBJECT_PATH_LINE_SUFFIX_RE);
      return match ? String(match[1] || "") : src;
    }

    function resolveMessageObjectPath(path) {
      const src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(path));
      const channelPath = resolveMessageObjectChannelRelativePath(src);
      if (channelPath) return channelPath;
      const projectChannelPath = resolveMessageObjectProjectChannelPrefixedPath(src);
      if (projectChannelPath) return projectChannelPath;
      if (!src || src[0] === "/" || !isLikelyWorkspaceRelativePath(src)) return src;
      const root = messageObjectProjectRootPath() || guessTaskDashboardRootPath();
      if (!root) return src;
      return root.replace(/\/$/, "") + "/" + src.replace(/^\/+/, "");
    }

    function normalizeMessageObjectLookupText(raw) {
      return decodeMessageObjectFsPath(raw)
        .replace(/[?#].*$/, "")
        .split(/[\\/]/)
        .pop()
        .replace(/\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)$/i, "")
        .toLowerCase()
        .replace(/[^\u4e00-\u9fa5a-z0-9]+/g, "");
    }

    function messageObjectPathExt(raw) {
      const src = stripMessageObjectPathLineSuffix(decodeMessageObjectFsPath(raw).replace(/[?#].*$/, ""));
      const m = src.match(/\.([a-z0-9]+)$/i);
      return m ? String(m[1] || "").toLowerCase() : "";
    }

    function shouldExtendMessageObjectToken(raw) {
      const src = String(raw || "").trim();
      if (!src || /^https?:\/\//i.test(src) || /^\/share\//.test(src)) return false;
      if (!MESSAGE_OBJECT_EXTENDABLE_PATH_ROOT_RE.test(src)) return false;
      return !messageObjectPathExt(src);
    }

    function extendMessageObjectTokenAt(src, start, raw) {
      const initial = String(raw || "");
      if (!shouldExtendMessageObjectToken(initial)) return initial;
      const rest = String(src || "").slice(Number(start) || 0);
      if (rest.length <= initial.length) return initial;
      const lineBreakIndex = rest.search(/\n/);
      const line = lineBreakIndex >= 0 ? rest.slice(0, lineBreakIndex) : rest;
      const match = MESSAGE_OBJECT_FILE_EXT_BOUNDARY_RE.exec(line);
      if (!match) return initial;
      const end = Number(match.index || 0) + String(match[0] || "").length;
      if (end <= initial.length) return initial;
      const candidate = line.slice(0, end);
      if (MESSAGE_OBJECT_EXTENDED_FORBIDDEN_RE.test(candidate)) return initial;
      const trimmed = trimMessageObjectToken(candidate).core;
      if (!trimmed || trimmed.length <= initial.length) return initial;
      return classifyMessageObjectToken(trimmed) ? candidate : initial;
    }

    function isLooseMessageObjectSubsequence(needle, haystack) {
      const a = String(needle || "");
      const b = String(haystack || "");
      if (!a || !b || a.length > b.length) return false;
      let i = 0;
      for (let j = 0; j < b.length; j += 1) {
        if (a[i] === b[j]) i += 1;
        if (i >= a.length) return true;
      }
      return false;
    }

    function scoreMessageObjectFallbackEntry(target, entry) {
      const entryName = String(entry && entry.name || "").trim();
      const entryKey = normalizeMessageObjectLookupText(entryName);
      if (!entryKey) return -1;
      const pathKey = normalizeMessageObjectLookupText((target && (target.path || target.value)) || "");
      const labelKey = normalizeMessageObjectLookupText((target && (target.lookupLabel || target.label)) || "");
      let score = 0;
      if (pathKey && entryKey === pathKey) score = Math.max(score, 100);
      if (labelKey && entryKey === labelKey) score = Math.max(score, 96);
      if (pathKey && (entryKey.includes(pathKey) || pathKey.includes(entryKey))) score = Math.max(score, 88);
      if (labelKey && (entryKey.includes(labelKey) || labelKey.includes(entryKey))) score = Math.max(score, 84);
      if (pathKey && isLooseMessageObjectSubsequence(pathKey, entryKey)) score = Math.max(score, 76);
      if (labelKey && isLooseMessageObjectSubsequence(labelKey, entryKey)) score = Math.max(score, 72);
      const wantExt = messageObjectPathExt((target && (target.path || target.value || target.label)) || "");
      const gotExt = messageObjectPathExt(entryName);
      if (wantExt && gotExt && wantExt === gotExt) score += 4;
      return score;
    }

    async function readMessageObjectPathItem(path) {
      const normalizedPath = resolveMessageObjectPath(path);
      const qs = new URLSearchParams({ path: String(normalizedPath || "") });
      const resp = await fetch("/api/fs/read?" + qs.toString(), {
        headers: authHeaders(),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        const err = new Error(detail || ("HTTP " + resp.status));
        err.status = resp.status;
        err.detail = detail || "";
        err.path = normalizedPath;
        throw err;
      }
      const data = await resp.json().catch(() => ({}));
      return {
        path: normalizedPath,
        item: data && data.item ? data.item : null,
      };
    }

    async function tryResolveMessageObjectPathFallback(target) {
      const basePath = resolveMessageObjectPath((target && (target.path || target.value)) || "");
      if (!basePath || basePath[0] !== "/") return null;
      const slash = basePath.lastIndexOf("/");
      if (slash <= 0) return null;
      const parentPath = basePath.slice(0, slash) || "/";
      let dirRead = null;
      try {
        dirRead = await readMessageObjectPathItem(parentPath);
      } catch (_) {
        return null;
      }
      const dirItem = dirRead && dirRead.item;
      if (!dirItem || String(dirItem.kind || "") !== "dir") return null;
      const entries = Array.isArray(dirItem.entries) ? dirItem.entries : [];
      let best = null;
      entries.forEach((entry) => {
        if (!entry || !String(entry.name || "").trim()) return;
        const score = scoreMessageObjectFallbackEntry(target, entry);
        if (score < 72) return;
        if (!best || score > best.score) best = { entry, score };
      });
      if (!best || !best.entry) return null;
      const correctedPath = parentPath.replace(/\/+$/, "") + "/" + String(best.entry.name || "").trim();
      const correctedRead = await readMessageObjectPathItem(correctedPath);
      const nextTarget = Object.assign({}, target || {}, {
        path: correctedRead.path,
        value: correctedRead.path,
        label: String((target && target.label) || best.entry.name || "").trim() || String(best.entry.name || ""),
      });
      return {
        target: nextTarget,
        item: correctedRead.item,
      };
    }

    function isImagePathLike(value) {
      const src = String(value || "").trim().toLowerCase();
      return /\.(png|jpe?g|gif|webp|bmp|svg)(?:\?.*)?$/.test(src);
    }

    function isShareLikeUrl(value) {
      try {
        const u = new URL(String(value || ""), location.origin);
        return u.origin === location.origin && /^\/share\//.test(u.pathname || "");
      } catch (_) {
        return false;
      }
    }

    function isRunAttachmentLikeUrl(value) {
      try {
        const u = new URL(String(value || ""), location.origin);
        return u.origin === location.origin && /^\/\.runs\//.test(u.pathname || "");
      } catch (_) {
        return false;
      }
    }

    function classifyMessageObjectToken(raw) {
      const token = String(raw || "").trim();
      if (!token) return null;
      if (isHttpUrl(token)) {
        if (isRunAttachmentLikeUrl(token)) {
          const u = new URL(token, location.origin);
          return {
            kind: "attachment_url",
            tone: "attach",
            value: token,
            label: token,
            path: String(u.pathname || ""),
            openUrl: token,
            defaultAction: isImagePathLike(token) ? "preview_image" : "open_url",
          };
        }
        return {
          kind: isShareLikeUrl(token) ? "share_url" : "url",
          tone: "url",
          value: token,
          label: token,
          openUrl: token,
          defaultAction: "open_url",
        };
      }
      if (/^\/\.runs\//.test(token)) {
        const openUrl = location.origin + token;
        return {
          kind: "attachment_path",
          tone: "attach",
          value: token,
          label: token,
          path: token,
          openUrl,
          defaultAction: isImagePathLike(token) ? "preview_image" : "open_url",
        };
      }
      if (/^\/share\//.test(token)) {
        return {
          kind: "share_path",
          tone: "url",
          value: token,
          label: token,
          openUrl: location.origin + token,
          defaultAction: "open_url",
        };
      }
      if (isLikelyChannelRelativePath(token)) {
        const path = resolveMessageObjectPath(token);
        return {
          kind: "fs_path",
          tone: token.includes(".") ? "file" : "dir",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      if (isLikelyProjectChannelPrefixedPath(token)) {
        const path = resolveMessageObjectPath(token);
        return {
          kind: "fs_path",
          tone: token.includes(".") ? "file" : "dir",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      if (/^\//.test(token)) {
        const path = stripMessageObjectPathLineSuffix(token);
        return {
          kind: "fs_path",
          tone: "file",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      if (isLikelyWorkspaceRelativePath(token)) {
        const path = resolveMessageObjectPath(token);
        return {
          kind: "fs_path",
          tone: token.includes(".") ? "file" : "dir",
          value: token,
          label: token,
          path,
          defaultAction: "preview_path",
        };
      }
      return null;
    }

    function createMessageObjectInlineNode(obj) {
      const node = el("button", {
        class: "msg-object-link tone-" + String(obj.tone || "file"),
        type: "button",
        title: String(obj.value || obj.label || ""),
      });
      node.__messageObject = obj;
      node.textContent = String(obj.label || obj.value || "");
      node.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
      return node;
    }

    function bindMessageObjectActivator(node, obj) {
      if (!node || !obj) return;
      node.__messageObject = obj;
      if (node.__messageObjectBound) return;
      node.__messageObjectBound = true;
      node.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
      node.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        e.stopPropagation();
        activateMessageObject(obj);
      });
    }

    function splitTextByMessageObjects(text) {
      const src = String(text || "");
      if (!src) return null;
      const out = [];
      let matched = false;
      let lastIndex = 0;
      MESSAGE_OBJECT_TOKEN_RE.lastIndex = 0;
      let m;
      while ((m = MESSAGE_OBJECT_TOKEN_RE.exec(src))) {
        const raw = extendMessageObjectTokenAt(src, m.index, String(m[0] || ""));
        const start = Number(m.index || 0);
        const trimmed = trimMessageObjectToken(raw);
        const obj = classifyMessageObjectToken(trimmed.core);
        if (!obj) continue;
        matched = true;
        if (start > lastIndex) out.push({ type: "text", value: src.slice(lastIndex, start) });
        out.push({ type: "object", value: trimmed.core, object: obj });
        if (trimmed.tail) out.push({ type: "text", value: trimmed.tail });
        lastIndex = start + raw.length;
        MESSAGE_OBJECT_TOKEN_RE.lastIndex = lastIndex;
      }
      if (!matched) return null;
      if (lastIndex < src.length) out.push({ type: "text", value: src.slice(lastIndex) });
      return out;
    }

    function enhanceTextNodeWithMessageObjects(textNode) {
      if (!textNode || !textNode.parentNode) return false;
      const segments = splitTextByMessageObjects(textNode.nodeValue || "");
      if (!segments || !segments.length) return false;
      const frag = document.createDocumentFragment();
      segments.forEach((seg) => {
        if (seg.type === "text") frag.appendChild(document.createTextNode(String(seg.value || "")));
        else if (seg.type === "object") frag.appendChild(createMessageObjectInlineNode(seg.object));
      });
      textNode.parentNode.replaceChild(frag, textNode);
      return true;
    }

    function enhanceAnchorMessageObject(anchor) {
      if (!anchor) return;
      const href = String(
        anchor.getAttribute("data-msg-object-href")
        || anchor.getAttribute("href")
        || anchor.href
        || ""
      ).trim();
      const obj = classifyMessageObjectToken(href);
      if (!obj) return;
      anchor.classList.add("msg-object-link", "tone-" + String(obj.tone || "url"), "is-anchor");
      anchor.title = String(obj.value || href || "");
      bindMessageObjectActivator(anchor, obj);
    }

    function enhanceCodeMessageObject(codeEl) {
      if (!codeEl || codeEl.__messageObjectEnhanced) return;
      const raw = String(codeEl.textContent || "").trim();
      if (!raw) return;
      const trimmed = trimMessageObjectToken(raw);
      if (!trimmed.core || trimmed.core !== raw) return;
      const obj = classifyMessageObjectToken(trimmed.core);
      if (!obj) return;
      codeEl.__messageObjectEnhanced = true;
      const parentPre = codeEl.parentElement && codeEl.parentElement.tagName === "PRE" ? codeEl.parentElement : null;
      const target = parentPre && parentPre.childElementCount === 1 ? parentPre : codeEl;
      target.__messageObject = obj;
      target.classList.add("msg-object-code-target", "tone-" + String(obj.tone || "file"));
      target.setAttribute("title", String(obj.value || obj.label || ""));
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "0");
      if (!target.hasAttribute("role")) target.setAttribute("role", "button");
      bindMessageObjectActivator(target, obj);
    }

    function enhanceMessageInteractiveObjects(root, opts = {}) {
      const force = !!(opts && opts.force);
      if (!root || !root.querySelectorAll || (root.__messageObjectsEnhanced && !force)) return;
      root.__messageObjectsEnhanced = true;
      Array.from(root.querySelectorAll("a[href]")).forEach((anchor) => enhanceAnchorMessageObject(anchor));
      Array.from(root.querySelectorAll("code")).forEach((codeEl) => enhanceCodeMessageObject(codeEl));
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          if (!node || !node.parentElement) return NodeFilter.FILTER_REJECT;
          const parent = node.parentElement;
          if (parent.closest("a, button, pre, code, script, style")) return NodeFilter.FILTER_REJECT;
          return String(node.nodeValue || "").trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        },
      });
      const nodes = [];
      let current;
      while ((current = walker.nextNode())) nodes.push(current);
      nodes.forEach((node) => { enhanceTextNodeWithMessageObjects(node); });
    }

    function ensureMessageObjectViewer() {
      let mask = document.getElementById("msgObjectViewerMask");
      if (mask) return mask;
      mask = document.createElement("div");
      mask.className = "msgobj-viewer-mask";
      mask.id = "msgObjectViewerMask";
      mask.innerHTML = `
        <div class="msgobj-viewer-dialog" role="dialog" aria-modal="true" aria-label="对象预览">
          <div class="msgobj-viewer-head">
            <div class="msgobj-viewer-titlewrap">
              <div class="msgobj-viewer-kicker" id="msgObjectViewerKicker">对象预览</div>
              <div class="msgobj-viewer-title" id="msgObjectViewerTitle">-</div>
              <div class="msgobj-viewer-sub" id="msgObjectViewerSub">-</div>
            </div>
            <div class="msgobj-viewer-actions">
              <button class="btn msgobj-viewer-star" id="msgObjectViewerStarBtn" type="button">☆ 收藏</button>
              <button class="btn" id="msgObjectViewerOpenTabBtn" type="button">新标签打开</button>
              <button class="btn" id="msgObjectViewerCopyBtn" type="button">复制</button>
              <button class="btn" id="msgObjectViewerRevealBtn" type="button">定位 Finder</button>
              <button class="btn" id="msgObjectViewerCloseBtn" type="button">关闭</button>
            </div>
          </div>
          <div class="msgobj-viewer-body" id="msgObjectViewerBody"></div>
        </div>
      `;
      document.body.appendChild(mask);
      mask.addEventListener("click", (e) => {
        if (e.target === mask) closeMessageObjectViewer();
      });
      const closeBtn = document.getElementById("msgObjectViewerCloseBtn");
      if (closeBtn) closeBtn.addEventListener("click", closeMessageObjectViewer);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && MESSAGE_OBJECT_VIEWER.open) closeMessageObjectViewer();
      });
      return mask;
    }

    function messageObjectViewerConversationFileState(target) {
      const rawTarget = (target && typeof target === "object") ? target : {};
      const sessionKey = typeof currentConvComposerDraftKey === "function"
        ? String(currentConvComposerDraftKey() || "").trim()
        : "";
      let fileKey = String(rawTarget.conversationFileKey || rawTarget.fileKey || "").trim();
      if (!fileKey
        && typeof isCollectableConversationFileObject === "function"
        && typeof buildConversationFileObjectKey === "function"
        && isCollectableConversationFileObject(rawTarget)) {
        fileKey = String(buildConversationFileObjectKey(rawTarget) || "").trim();
      }
      if (!sessionKey || !fileKey || typeof getConversationFileStarredMapByKey !== "function") {
        return {
          available: false,
          sessionKey,
          fileKey,
          starred: false,
        };
      }
      const starredMap = getConversationFileStarredMapByKey(sessionKey);
      return {
        available: true,
        sessionKey,
        fileKey,
        starred: !!(starredMap && starredMap[fileKey]),
      };
    }

    function toggleMessageObjectViewerConversationFileStar() {
      const target = MESSAGE_OBJECT_VIEWER.target;
      const state = messageObjectViewerConversationFileState(target);
      if (!state.available || typeof toggleConversationFileStar !== "function") return;
      const nextStarred = !state.starred;
      toggleConversationFileStar(state.sessionKey, state.fileKey);
      if (typeof refreshConversationFilesFromCurrentTimeline === "function") {
        refreshConversationFilesFromCurrentTimeline();
      } else if (typeof renderConversationFileUi === "function") {
        renderConversationFileUi();
      }
      renderMessageObjectViewer();
      if (typeof setHintText === "function") {
        setHintText("conv", nextStarred ? "已加入会话文件收藏" : "已取消会话文件收藏");
      }
    }

    function isMessageObjectViewerImageEntry(entry) {
      if (!entry || typeof entry !== "object") return false;
      if (String(entry.kind || "file").trim() !== "file") return false;
      if (entry.is_image === true) return true;
      const mimeType = String(entry.mime_type || "").trim().toLowerCase();
      if (mimeType.startsWith("image/")) return true;
      return false;
    }

    function messageObjectViewerImageEntries(item) {
      const entries = Array.isArray(item && item.entries) ? item.entries : [];
      return entries.filter((entry) => String((entry && entry.kind) || "").trim() === "file" && isMessageObjectViewerImageEntry(entry));
    }

    function messageObjectViewerImageCaption(entry) {
      const name = String((entry && entry.name) || "").trim();
      const path = String((entry && entry.path) || "").trim();
      return name || path || "图片";
    }

    function renderMessageObjectViewerImageStage(entry, opts = {}) {
      const target = opts && typeof opts === "object" ? (opts.target || null) : null;
      const item = opts && typeof opts === "object" ? (opts.item || entry || null) : (entry || null);
      const src = String(messageObjectViewerOpenUrl(target, item) || "").trim();
      if (!src) return null;
      const caption = messageObjectViewerImageCaption(entry || item);
      const stage = el("div", { class: "msgobj-image-stage" });
      const imageBtn = el("button", {
        class: "msgobj-image-mainbtn",
        type: "button",
        title: "点击放大预览",
      });
      imageBtn.addEventListener("click", () => {
        openImagePreview(src, caption);
      });
      imageBtn.appendChild(el("img", {
        class: "msgobj-image-main",
        src,
        alt: caption,
      }));
      stage.appendChild(imageBtn);
      const meta = el("div", { class: "msgobj-image-stage-meta" });
      meta.appendChild(el("div", { class: "msgobj-image-stage-name", text: caption }));
      const metaBits = [];
      const mimeType = String(((entry || item) && (entry || item).mime_type) || "").trim();
      if (mimeType) metaBits.push(mimeType);
      const size = Number(((entry || item) && (entry || item).size) || 0);
      if (size > 0) metaBits.push(formatBytes(size));
      if (metaBits.length) {
        meta.appendChild(el("div", { class: "msgobj-image-stage-sub", text: metaBits.join(" · ") }));
      }
      stage.appendChild(meta);
      return stage;
    }

    function messageObjectViewerPathBasename(path) {
      const src = String(path || "").trim().replace(/\/+$/, "");
      if (!src) return "";
      const parts = src.split("/").filter(Boolean);
      return parts.length ? parts[parts.length - 1] : src;
    }

    function messageObjectViewerEntryTarget(entry) {
      const row = (entry && typeof entry === "object") ? entry : {};
      const path = String(row.path || "").trim();
      if (!path) return null;
      const itemKind = String(row.kind || "file").trim() === "dir" ? "dir" : "file";
      const name = String(row.name || "").trim();
      return {
        kind: "fs_path",
        tone: itemKind === "dir" ? "dir" : "file",
        value: path,
        label: name || messageObjectViewerPathBasename(path) || path,
        path,
        defaultAction: "preview_path",
      };
    }

    function messageObjectViewerSnapshotFrom(target, item) {
      const rawTarget = (target && typeof target === "object") ? target : {};
      const rawItem = (item && typeof item === "object") ? item : null;
      const path = String((rawItem && rawItem.path) || rawTarget.path || rawTarget.value || "").trim();
      if (!path) return null;
      const nextTarget = Object.assign({}, rawTarget, { path });
      if (String(nextTarget.kind || "").trim() === "fs_path") nextTarget.value = path;
      return {
        target: nextTarget,
        item: rawItem,
      };
    }

    function messageObjectViewerCurrentSnapshot() {
      return messageObjectViewerSnapshotFrom(MESSAGE_OBJECT_VIEWER.target, MESSAGE_OBJECT_VIEWER.item);
    }

    function messageObjectViewerSnapshotKey(snapshot) {
      return String((snapshot && snapshot.target && (snapshot.target.path || snapshot.target.value)) || "").trim();
    }

    function pushCurrentMessageObjectViewerSnapshot() {
      const snapshot = messageObjectViewerCurrentSnapshot();
      if (!snapshot) return;
      const history = Array.isArray(MESSAGE_OBJECT_VIEWER.history) ? MESSAGE_OBJECT_VIEWER.history : [];
      const key = messageObjectViewerSnapshotKey(snapshot);
      const lastKey = messageObjectViewerSnapshotKey(history[history.length - 1]);
      if (key && key === lastKey) return;
      MESSAGE_OBJECT_VIEWER.history = history.concat([snapshot]).slice(-24);
    }

    function messageObjectViewerTrail() {
      const history = Array.isArray(MESSAGE_OBJECT_VIEWER.history) ? MESSAGE_OBJECT_VIEWER.history.filter(Boolean) : [];
      const current = messageObjectViewerCurrentSnapshot();
      if (!current) return history;
      const currentKey = messageObjectViewerSnapshotKey(current);
      const lastKey = messageObjectViewerSnapshotKey(history[history.length - 1]);
      return currentKey && currentKey === lastKey ? history : history.concat([current]);
    }

    function messageObjectViewerCrumbLabel(snapshot, index) {
      const item = snapshot && snapshot.item;
      const target = snapshot && snapshot.target;
      const explicit = String((item && item.name) || (target && target.label) || "").trim();
      if (explicit) return explicit;
      const path = String((item && item.path) || (target && (target.path || target.value)) || "").trim();
      return messageObjectViewerPathBasename(path) || (index === 0 ? "起点" : "当前对象");
    }

    function restoreMessageObjectViewerSnapshot(index) {
      const trail = messageObjectViewerTrail();
      const pos = Number(index);
      if (!Number.isFinite(pos) || pos < 0 || pos >= trail.length) return;
      const snapshot = trail[pos];
      MESSAGE_OBJECT_VIEWER.requestSeq += 1;
      MESSAGE_OBJECT_VIEWER.history = trail.slice(0, pos);
      MESSAGE_OBJECT_VIEWER.target = Object.assign({}, snapshot.target || {});
      MESSAGE_OBJECT_VIEWER.item = snapshot.item || null;
      MESSAGE_OBJECT_VIEWER.error = "";
      MESSAGE_OBJECT_VIEWER.loading = false;
      renderMessageObjectViewer();
    }

    function goBackMessageObjectViewer() {
      const history = Array.isArray(MESSAGE_OBJECT_VIEWER.history) ? MESSAGE_OBJECT_VIEWER.history : [];
      if (!history.length) return;
      const snapshot = history[history.length - 1];
      MESSAGE_OBJECT_VIEWER.requestSeq += 1;
      MESSAGE_OBJECT_VIEWER.history = history.slice(0, -1);
      MESSAGE_OBJECT_VIEWER.target = Object.assign({}, snapshot.target || {});
      MESSAGE_OBJECT_VIEWER.item = snapshot.item || null;
      MESSAGE_OBJECT_VIEWER.error = "";
      MESSAGE_OBJECT_VIEWER.loading = false;
      renderMessageObjectViewer();
    }

    function renderMessageObjectViewerNav() {
      const trail = messageObjectViewerTrail();
      if (trail.length <= 1) return null;
      const nav = el("div", { class: "msgobj-nav" });
      const backBtn = el("button", {
        class: "btn msgobj-nav-back",
        type: "button",
        text: "返回上级",
      });
      backBtn.disabled = !(Array.isArray(MESSAGE_OBJECT_VIEWER.history) && MESSAGE_OBJECT_VIEWER.history.length);
      backBtn.addEventListener("click", goBackMessageObjectViewer);
      nav.appendChild(backBtn);

      const crumbs = el("div", { class: "msgobj-crumbs", "aria-label": "路径层级" });
      trail.forEach((snapshot, index) => {
        if (index > 0) crumbs.appendChild(el("span", { class: "msgobj-crumb-sep", text: "/" }));
        const isCurrent = index === trail.length - 1;
        const crumb = el("button", {
          class: "msgobj-crumb" + (isCurrent ? " current" : ""),
          type: "button",
          text: messageObjectViewerCrumbLabel(snapshot, index),
        });
        crumb.disabled = isCurrent;
        if (!isCurrent) crumb.addEventListener("click", () => restoreMessageObjectViewerSnapshot(index));
        crumbs.appendChild(crumb);
      });
      nav.appendChild(crumbs);
      return nav;
    }

    function renderMessageObjectViewerImageGrid(entries, opts = {}) {
      const rows = Array.isArray(entries) ? entries.filter(Boolean) : [];
      if (!rows.length) return null;
      const options = (opts && typeof opts === "object") ? opts : {};
      const openInViewer = !!options.openInViewer;
      const wrap = el("div", { class: "msgobj-image-grid-wrap" });
      wrap.appendChild(el("div", { class: "msgobj-image-grid-title", text: "图片预览" }));
      const grid = el("div", { class: "msgobj-image-grid" });
      rows.forEach((entry) => {
        const src = String(messageObjectViewerOpenUrl(null, entry) || "").trim();
        if (!src) return;
        const caption = messageObjectViewerImageCaption(entry);
        const rowTarget = openInViewer ? messageObjectViewerEntryTarget(entry) : null;
        const card = el("button", {
          class: "msgobj-image-card" + (openInViewer ? " open-viewer" : ""),
          type: "button",
          title: openInViewer ? "点击打开查看" : "点击放大预览",
        });
        card.addEventListener("click", () => {
          if (openInViewer && rowTarget) {
            openMessageObjectViewer(rowTarget, { keepHistory: true, pushCurrent: true });
            return;
          }
          openImagePreview(src, caption);
        });
        card.appendChild(el("img", {
          class: "msgobj-image-thumb",
          src,
          alt: caption,
        }));
        const info = el("div", { class: "msgobj-image-card-info" });
        info.appendChild(el("div", { class: "msgobj-image-name", text: caption }));
        const metaBits = [];
        const mimeType = String(entry.mime_type || "").trim();
        if (mimeType) metaBits.push(mimeType);
        if (metaBits.length) info.appendChild(el("div", { class: "msgobj-image-sub", text: metaBits.join(" · ") }));
        card.appendChild(info);
        grid.appendChild(card);
      });
      if (!grid.childNodes.length) return null;
      wrap.appendChild(grid);
      return wrap;
    }

    function renderMessageObjectViewerBody() {
      const body = document.getElementById("msgObjectViewerBody");
      if (!body) return;
      body.innerHTML = "";
      const nav = renderMessageObjectViewerNav();
      if (nav) body.appendChild(nav);
      if (MESSAGE_OBJECT_VIEWER.loading) {
        body.appendChild(el("div", { class: "hint", text: "对象加载中..." }));
        return;
      }
      if (MESSAGE_OBJECT_VIEWER.error) {
        body.appendChild(el("div", { class: "hint", text: MESSAGE_OBJECT_VIEWER.error }));
        return;
      }
      const item = MESSAGE_OBJECT_VIEWER.item;
      if (!item || typeof item !== "object") {
        body.appendChild(el("div", { class: "hint", text: "当前对象暂无可展示内容。" }));
        return;
      }
      if (String(item.kind || "") === "dir") {
        const meta = el("div", { class: "msgobj-meta-grid" });
        meta.appendChild(el("div", { class: "msgobj-meta-card", html: "<div class=\"k\">目录</div><div class=\"v\">" + escapeHtml(String(item.path || "")) + "</div>" }));
        meta.appendChild(el("div", { class: "msgobj-meta-card", html: "<div class=\"k\">条目数</div><div class=\"v\">" + String(item.entry_count || 0) + (item.truncated ? "（已截断）" : "") + "</div>" }));
        body.appendChild(meta);
        const imageGrid = renderMessageObjectViewerImageGrid(messageObjectViewerImageEntries(item), { openInViewer: true });
        if (imageGrid) body.appendChild(imageGrid);
        const list = el("div", { class: "msgobj-dir-list" });
        const entries = Array.isArray(item.entries) ? item.entries : [];
        const listEntries = imageGrid
          ? entries.filter((row) => !isMessageObjectViewerImageEntry(row))
          : entries;
        if (!listEntries.length) {
          list.appendChild(el("div", { class: "hint", text: imageGrid ? "目录内仅包含图片条目。" : "目录为空。" }));
        } else {
          if (imageGrid) {
            body.appendChild(el("div", { class: "msgobj-image-grid-title", text: "其余条目" }));
          }
          listEntries.forEach((row) => {
            const name = String((row && row.name) || "").trim() || "-";
            const kind = String((row && row.kind) || "file").trim();
            const rowTarget = messageObjectViewerEntryTarget(row);
            const itemNode = el("button", {
              class: "msgobj-dir-item" + (kind === "dir" ? " is-dir" : " is-file"),
              type: "button",
            });
            if (rowTarget) {
              itemNode.addEventListener("click", () => {
                openMessageObjectViewer(rowTarget, { keepHistory: true, pushCurrent: true });
              });
            } else {
              itemNode.disabled = true;
            }
            itemNode.appendChild(el("span", { class: "msgobj-dir-kind", text: kind === "dir" ? "目录" : "文件" }));
            itemNode.appendChild(el("span", { class: "msgobj-dir-name", text: name }));
            list.appendChild(itemNode);
          });
        }
        body.appendChild(list);
        return;
      }
      if (item.is_image) {
        const imageStage = renderMessageObjectViewerImageStage(item, { target: MESSAGE_OBJECT_VIEWER.target, item });
        if (imageStage) {
          body.appendChild(imageStage);
          return;
        }
        body.appendChild(el("div", {
          class: "hint",
          text: "当前识别为图片文件，但未拿到可访问预览地址；建议直接新标签打开或 Finder 定位。",
        }));
        return;
      }
      if (!item.is_text) {
        body.appendChild(el("div", { class: "hint", text: "当前对象不是文本文件，暂不展示正文预览。" }));
        return;
      }
      const mode = String(item.preview_mode || "text");
      const rawSequenceViewer = typeof buildSequenceDiagramViewer === "function"
        ? buildSequenceDiagramViewer(String(item.content || ""), { sourceKind: "plain_text" })
        : null;
      if (rawSequenceViewer) {
        body.appendChild(rawSequenceViewer);
        return;
      }
      if (mode === "markdown") {
        const box = el("div", { class: "msgobj-preview mdview" });
        box.innerHTML = markdownToHtml(String(item.content || ""));
        if (typeof enhanceDiagramTypedBlocks === "function") {
          enhanceDiagramTypedBlocks(box, { scope: "message_object_viewer" });
        }
        enhanceMarkdownTypedBlocks(box);
        if (typeof enhanceMessageInteractiveObjects === "function") {
          enhanceMessageInteractiveObjects(box, { force: true });
        }
        body.appendChild(box);
        return;
      }
      if (mode === "html") {
        if (item.truncated) {
          body.appendChild(el("div", {
            class: "hint",
            text: "当前 HTML 预览内容已截断，下面为截断后的安全渲染结果；如需完整查看，建议直接打开文件。",
          }));
        }
        const frameWrap = el("div", { class: "msgobj-html-preview-wrap" });
        const frame = el("iframe", {
          class: "msgobj-html-preview",
          sandbox: "",
          referrerpolicy: "no-referrer",
          title: String(item.name || item.path || "HTML 预览"),
        });
        try {
          frame.srcdoc = String(item.content || "");
        } catch (_) {
          frame.srcdoc = "<!doctype html><html><body><pre>HTML 预览加载失败</pre></body></html>";
        }
        frameWrap.appendChild(frame);
        body.appendChild(frameWrap);
        return;
      }
      const pre = el("pre", { class: "msgobj-preview-pre" });
      pre.textContent = String(item.content || "");
      body.appendChild(pre);
    }

    function renderMessageObjectViewer() {
      const mask = ensureMessageObjectViewer();
      const title = document.getElementById("msgObjectViewerTitle");
      const sub = document.getElementById("msgObjectViewerSub");
      const kicker = document.getElementById("msgObjectViewerKicker");
      const starBtn = document.getElementById("msgObjectViewerStarBtn");
      const openTabBtn = document.getElementById("msgObjectViewerOpenTabBtn");
      const copyBtn = document.getElementById("msgObjectViewerCopyBtn");
      const revealBtn = document.getElementById("msgObjectViewerRevealBtn");
      if (!mask || !title || !sub || !kicker || !starBtn || !openTabBtn || !copyBtn || !revealBtn) return;
      const target = MESSAGE_OBJECT_VIEWER.target || {};
      title.textContent = String(target.label || target.value || "对象预览");
      kicker.textContent = String(target.kind === "fs_path" ? "路径预览" : "对象预览");
      const item = MESSAGE_OBJECT_VIEWER.item;
      if (item && typeof item === "object") {
        const itemKind = String(item.kind || "file");
        sub.textContent = itemKind === "dir"
          ? ("目录 · " + String(item.path || ""))
          : ([
              String(item.mime_type || "") || "文件",
              Number(item.size || 0) > 0 ? formatBytes(Number(item.size || 0)) : "",
              String(item.path || ""),
            ].filter(Boolean).join(" · "));
      } else if (MESSAGE_OBJECT_VIEWER.error) {
        sub.textContent = MESSAGE_OBJECT_VIEWER.error;
      } else {
        sub.textContent = String(target.value || "");
      }
      const starState = messageObjectViewerConversationFileState(target);
      starBtn.style.display = starState.available ? "" : "none";
      starBtn.disabled = !starState.available;
      starBtn.classList.toggle("active", !!starState.starred);
      starBtn.textContent = starState.starred ? "★ 已收藏" : "☆ 收藏";
      starBtn.title = starState.starred ? "取消会话文件收藏" : "加入会话文件收藏";
      starBtn.onclick = starState.available ? toggleMessageObjectViewerConversationFileStar : null;
      const openUrl = messageObjectViewerOpenUrl(target, item);
      const canOpenInNewTab = !!openUrl && String((item && item.kind) || "").trim() !== "dir";
      openTabBtn.disabled = !canOpenInNewTab;
      openTabBtn.title = canOpenInNewTab ? "在新标签页打开当前对象" : "当前对象暂不支持新标签页打开";
      openTabBtn.onclick = () => {
        if (!canOpenInNewTab) return;
        openNew(openUrl);
      };
      copyBtn.onclick = () => copyText(String((item && item.path) || target.value || ""));
      revealBtn.disabled = !String(target.path || (item && item.path) || "").trim();
      revealBtn.onclick = async () => {
        const path = String(target.path || (item && item.path) || "").trim();
        if (!path) return;
        try {
          const resp = await fetch("/api/fs/reveal", {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ path }),
          });
          if (!resp.ok) throw new Error((await parseResponseDetail(resp)) || ("HTTP " + resp.status));
          setHintText("conv", "已打开 Finder 定位");
        } catch (err) {
          setHintText("conv", "打开 Finder 失败：" + String((err && err.message) || err || "未知错误"));
        }
      };
      renderMessageObjectViewerBody();
      mask.classList.toggle("show", !!MESSAGE_OBJECT_VIEWER.open);
    }

    function closeMessageObjectViewer() {
      MESSAGE_OBJECT_VIEWER.open = false;
      MESSAGE_OBJECT_VIEWER.loading = false;
      MESSAGE_OBJECT_VIEWER.target = null;
      MESSAGE_OBJECT_VIEWER.item = null;
      MESSAGE_OBJECT_VIEWER.error = "";
      MESSAGE_OBJECT_VIEWER.history = [];
      MESSAGE_OBJECT_VIEWER.requestSeq += 1;
      renderMessageObjectViewer();
    }

    function messageObjectViewerReadErrorText(err, target) {
      const detail = String((err && (err.detail || err.message)) || err || "未知错误").trim() || "未知错误";
      const status = Number(err && err.status);
      const notFound = status === 404 || /path not found|not found|不存在/i.test(detail);
      if (!notFound) return "对象预览失败：" + detail;
      const raw = String((target && (target.value || target.label)) || "").trim();
      const resolved = String((err && err.path) || (target && target.path) || "").trim();
      const parts = ["对象预览失败：文件不存在或尚未落盘"];
      if (raw) parts.push("原始路径：" + raw);
      if (resolved && resolved !== raw) parts.push("解析路径：" + resolved);
      return parts.join("。");
    }

    async function openMessageObjectViewer(target, opts = {}) {
      const obj = (target && typeof target === "object") ? target : null;
      if (!obj) return;
      const options = (opts && typeof opts === "object") ? opts : {};
      if (options.keepHistory) {
        if (options.pushCurrent) pushCurrentMessageObjectViewerSnapshot();
      } else {
        MESSAGE_OBJECT_VIEWER.history = [];
      }
      const nextTarget = Object.assign({}, obj);
      if (typeof isCollectableConversationFileObject === "function"
        && typeof buildConversationFileObjectKey === "function"
        && isCollectableConversationFileObject(obj)) {
        nextTarget.conversationFileKey = String(
          obj.conversationFileKey || obj.fileKey || buildConversationFileObjectKey(obj) || ""
        ).trim();
      }
      const normalizedPath = resolveMessageObjectPath(String(obj.path || obj.value || ""));
      if (normalizedPath) {
        nextTarget.path = normalizedPath;
        if (String(nextTarget.kind || "").trim() === "fs_path") nextTarget.value = normalizedPath;
      }
      MESSAGE_OBJECT_VIEWER.open = true;
      MESSAGE_OBJECT_VIEWER.loading = true;
      MESSAGE_OBJECT_VIEWER.target = nextTarget;
      MESSAGE_OBJECT_VIEWER.item = null;
      MESSAGE_OBJECT_VIEWER.error = "";
      const requestSeq = MESSAGE_OBJECT_VIEWER.requestSeq + 1;
      MESSAGE_OBJECT_VIEWER.requestSeq = requestSeq;
      renderMessageObjectViewer();
      try {
        const directRead = await readMessageObjectPathItem(String(nextTarget.path || nextTarget.value || ""));
        if (MESSAGE_OBJECT_VIEWER.requestSeq !== requestSeq) return;
        MESSAGE_OBJECT_VIEWER.target = Object.assign({}, nextTarget, {
          path: directRead.path,
          value: String(nextTarget.kind || "").trim() === "fs_path" ? directRead.path : nextTarget.value,
        });
        MESSAGE_OBJECT_VIEWER.item = directRead.item;
      } catch (err) {
        const fallback = await tryResolveMessageObjectPathFallback(nextTarget).catch(() => null);
        if (MESSAGE_OBJECT_VIEWER.requestSeq !== requestSeq) return;
        if (fallback && fallback.item) {
          MESSAGE_OBJECT_VIEWER.target = Object.assign({}, fallback.target || {}, {
            conversationFileKey: String(nextTarget.conversationFileKey || (fallback.target && fallback.target.conversationFileKey) || "").trim(),
          });
          MESSAGE_OBJECT_VIEWER.item = fallback.item;
          MESSAGE_OBJECT_VIEWER.error = "";
        } else {
          MESSAGE_OBJECT_VIEWER.error = messageObjectViewerReadErrorText(err, nextTarget);
        }
      } finally {
        if (MESSAGE_OBJECT_VIEWER.requestSeq === requestSeq) {
          MESSAGE_OBJECT_VIEWER.loading = false;
          renderMessageObjectViewer();
        }
      }
    }

    function activateMessageObject(obj) {
      const target = (obj && typeof obj === "object") ? obj : null;
      if (!target) return;
      if (target.defaultAction === "open_url") {
        openNew(String(target.openUrl || target.value || ""));
        return;
      }
      if (target.defaultAction === "preview_image") {
        openImagePreview(String(target.openUrl || target.value || ""), String(target.label || ""));
        return;
      }
      const nested = !!(MESSAGE_OBJECT_VIEWER.open && messageObjectViewerCurrentSnapshot());
      openMessageObjectViewer(target, nested ? { keepHistory: true, pushCurrent: true } : {});
    }

    if (typeof window !== "undefined") {
      window.__messageObjectViewer__ = Object.assign(window.__messageObjectViewer__ || {}, {
        open: openMessageObjectViewer,
        activate: activateMessageObject,
        classify: classifyMessageObjectToken,
      });
    }
