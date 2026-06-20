    const SEQUENCE_DIAGRAM_PREVIEW_LIMITS = Object.freeze({
      maxSourceChars: 30000,
      maxParticipants: 24,
      maxItems: 120,
      maxLineChars: 1200,
      maxLabelChars: 160,
      maxMessageChars: 360,
      maxNoteChars: 360,
    });

    function sequenceDiagramLimits(opts = {}) {
      const raw = opts && typeof opts === "object" ? (opts.limits || {}) : {};
      return Object.assign({}, SEQUENCE_DIAGRAM_PREVIEW_LIMITS, raw || {});
    }

    function normalizeSequenceDiagramSource(value) {
      return String(value || "").replace(/\r\n?/g, "\n").trim();
    }

    function trimSequenceDiagramLabel(value, maxLen) {
      const text = String(value || "").trim();
      if (!text) return "";
      const limit = Math.max(20, Number(maxLen) || SEQUENCE_DIAGRAM_PREVIEW_LIMITS.maxLabelChars);
      return text.length > limit ? (text.slice(0, limit - 1) + "…") : text;
    }

    function firstMeaningfulSequenceDiagramLine(lines) {
      const rows = Array.isArray(lines) ? lines : String(lines || "").split("\n");
      for (let i = 0; i < rows.length; i += 1) {
        const line = String(rows[i] || "").trim();
        if (!line || line.startsWith("%%")) continue;
        return { line, index: i };
      }
      return { line: "", index: -1 };
    }

    function isSequenceDiagramFirstLine(source) {
      const first = firstMeaningfulSequenceDiagramLine(normalizeSequenceDiagramSource(source).split("\n"));
      return /^sequenceDiagram\s*$/.test(first.line);
    }

    function extractMermaidSequenceFences(markdown, opts = {}) {
      const limits = sequenceDiagramLimits(opts);
      const text = String(markdown || "").replace(/\r\n?/g, "\n");
      if (!text.trim() || text.length > limits.maxSourceChars * 3) return [];
      const lines = text.split("\n");
      const blocks = [];
      let inFence = false;
      let lang = "";
      let code = [];
      for (let i = 0; i < lines.length; i += 1) {
        const line = String(lines[i] || "");
        if (!inFence) {
          const open = line.trim().match(/^```([A-Za-z0-9_-]+)?\s*$/);
          if (!open) continue;
          inFence = true;
          lang = String(open[1] || "").trim().toLowerCase();
          code = [];
          continue;
        }
        if (/^```\s*$/.test(line.trim())) {
          if (lang === "mermaid") {
            const source = normalizeSequenceDiagramSource(code.join("\n"));
            if (source && source.length <= limits.maxSourceChars && isSequenceDiagramFirstLine(source)) {
              blocks.push({ source, sourceKind: "markdown_fenced", startLine: i - code.length });
            }
          }
          inFence = false;
          lang = "";
          code = [];
          continue;
        }
        code.push(line);
      }
      if (inFence && lang === "mermaid") {
        const source = normalizeSequenceDiagramSource(code.join("\n"));
        if (source && source.length <= limits.maxSourceChars && isSequenceDiagramFirstLine(source)) {
          blocks.push({ source, sourceKind: "markdown_fenced", startLine: Math.max(0, lines.length - code.length) });
        }
      }
      return blocks;
    }

    function detectSequenceDiagramSource(content, opts = {}) {
      const sourceKind = String((opts && opts.sourceKind) || "auto");
      const limits = sequenceDiagramLimits(opts);
      const raw = String(content || "");
      if (!raw.trim()) return null;
      if (sourceKind !== "plain_text") {
        const blocks = extractMermaidSequenceFences(raw, opts);
        if (blocks.length) return blocks[0];
      }
      if (sourceKind !== "markdown_fenced") {
        const source = normalizeSequenceDiagramSource(raw);
        if (source && source.length <= limits.maxSourceChars && isSequenceDiagramFirstLine(source)) {
          return { source, sourceKind: "plain_text", startLine: 0 };
        }
      }
      return null;
    }

    function normalizeSequenceParticipantId(value) {
      const id = String(value || "").trim();
      if (!id || /\s/.test(id) || id.length > 80) return "";
      if (!/^[A-Za-z0-9_$.-]+$/.test(id)) return "";
      return id;
    }

    function parseSequenceDiagramSource(source, opts = {}) {
      const limits = sequenceDiagramLimits(opts);
      const normalized = normalizeSequenceDiagramSource(source);
      if (!normalized) return { ok: false, reason: "empty" };
      if (normalized.length > limits.maxSourceChars) return { ok: false, reason: "source_too_large" };
      const lines = normalized.split("\n");
      const first = firstMeaningfulSequenceDiagramLine(lines);
      if (!/^sequenceDiagram\s*$/.test(first.line)) return { ok: false, reason: "not_sequence_diagram" };

      const participants = [];
      const participantMap = Object.create(null);
      const items = [];
      let autonumber = false;

      function addParticipant(rawId, rawLabel, rawKind, implicit = false) {
        const id = normalizeSequenceParticipantId(rawId);
        if (!id) return { ok: false, reason: "invalid_participant_id" };
        const existing = participantMap[id];
        if (existing) {
          if (!existing.declared && rawLabel) {
            existing.label = trimSequenceDiagramLabel(rawLabel, limits.maxLabelChars) || id;
            existing.kind = rawKind || existing.kind || "participant";
            existing.declared = !implicit;
          }
          return { ok: true, participant: existing };
        }
        if (participants.length >= limits.maxParticipants) return { ok: false, reason: "too_many_participants" };
        const participant = {
          id,
          label: trimSequenceDiagramLabel(rawLabel || id, limits.maxLabelChars) || id,
          kind: rawKind || "participant",
          declared: !implicit,
        };
        participants.push(participant);
        participantMap[id] = participant;
        return { ok: true, participant };
      }

      for (let i = first.index + 1; i < lines.length; i += 1) {
        const rawLine = String(lines[i] || "");
        const line = rawLine.trim();
        if (!line || line.startsWith("%%")) continue;
        if (line.length > limits.maxLineChars) return { ok: false, reason: "line_too_long", line: i + 1 };
        if (items.length >= limits.maxItems) return { ok: false, reason: "too_many_items" };

        if (/^autonumber(?:\s+\d+(?:\s*,\s*\d+)?)?\s*$/.test(line)) {
          autonumber = true;
          continue;
        }

        let match = line.match(/^(participant|actor)\s+([A-Za-z0-9_$.-]+)(?:\s+as\s+(.+))?$/);
        if (match) {
          const added = addParticipant(match[2], match[3] || match[2], match[1].toLowerCase(), false);
          if (!added.ok) return { ok: false, reason: added.reason, line: i + 1 };
          continue;
        }

        match = line.match(/^Note\s+over\s+([^:]+?)\s*:\s*(.*)$/);
        if (match) {
          const noteText = String(match[2] || "").trim();
          if (noteText.length > limits.maxNoteChars) return { ok: false, reason: "note_too_long", line: i + 1 };
          const over = String(match[1] || "").split(",").map((part) => normalizeSequenceParticipantId(part)).filter(Boolean);
          if (!over.length) return { ok: false, reason: "invalid_note_target", line: i + 1 };
          for (const id of over) {
            const added = addParticipant(id, id, "participant", true);
            if (!added.ok) return { ok: false, reason: added.reason, line: i + 1 };
          }
          items.push({
            type: "note",
            over,
            text: noteText || "备注",
            line: i + 1,
          });
          continue;
        }

        match = line.match(/^([A-Za-z0-9_$.-]+?)\s*(-->>|->>)\s*([A-Za-z0-9_$.-]+)\s*:\s*(.*)$/);
        if (match) {
          const messageText = String(match[4] || "").trim();
          if (messageText.length > limits.maxMessageChars) return { ok: false, reason: "message_too_long", line: i + 1 };
          const fromAdded = addParticipant(match[1], match[1], "participant", true);
          if (!fromAdded.ok) return { ok: false, reason: fromAdded.reason, line: i + 1 };
          const toAdded = addParticipant(match[3], match[3], "participant", true);
          if (!toAdded.ok) return { ok: false, reason: toAdded.reason, line: i + 1 };
          items.push({
            type: "message",
            from: match[1],
            to: match[3],
            arrow: match[2],
            text: messageText || "消息",
            line: i + 1,
          });
          continue;
        }

        return { ok: false, reason: "unsupported_syntax", line: i + 1 };
      }

      if (!participants.length || !items.length) return { ok: false, reason: "empty_diagram" };
      return {
        ok: true,
        source: normalized,
        autonumber,
        participants,
        items,
      };
    }

    function createSequenceDiagramElement(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    }

    function setSequenceGridColumns(node, participantCount) {
      const count = Math.max(1, Math.min(48, Number(participantCount) || 1));
      node.style.setProperty("--seq-participant-count", String(count));
      node.style.gridTemplateColumns = "repeat(" + count + ", minmax(136px, 1fr))";
    }

    function participantIndexById(parsed) {
      const map = Object.create(null);
      (parsed.participants || []).forEach((participant, index) => {
        map[participant.id] = index;
      });
      return map;
    }

    function appendSequenceLanes(row, count) {
      for (let i = 0; i < count; i += 1) {
        const lane = createSequenceDiagramElement("div", "seq-diagram-lane");
        lane.style.gridColumn = String(i + 1) + " / " + String(i + 2);
        row.appendChild(lane);
      }
    }

    async function copySequenceDiagramSource(source) {
      const text = String(source || "");
      if (!text) return false;
      if (typeof copyText === "function") return copyText(text);
      if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
        return true;
      }
      return false;
    }

    function renderSequenceDiagramPreview(source, opts = {}) {
      if (typeof document === "undefined" || !document.createElement) return null;
      const parsed = opts && opts.parsed && opts.parsed.ok
        ? opts.parsed
        : parseSequenceDiagramSource(source, opts);
      if (!parsed || !parsed.ok) return null;

      const participantCount = parsed.participants.length;
      const indexById = participantIndexById(parsed);
      const card = createSequenceDiagramElement("section", "seq-diagram-card");
      card.setAttribute("data-source-kind", String((opts && opts.sourceKind) || "sequence_diagram"));

      const toolbar = createSequenceDiagramElement("div", "seq-diagram-toolbar");
      const heading = createSequenceDiagramElement("div", "seq-diagram-heading");
      heading.appendChild(createSequenceDiagramElement("div", "seq-diagram-title", "时序图预览"));
      heading.appendChild(createSequenceDiagramElement(
        "div",
        "seq-diagram-meta",
        participantCount + " 个参与方 · " + parsed.items.length + " 个事件" + (parsed.autonumber ? " · 自动编号" : "")
      ));
      toolbar.appendChild(heading);

      const actions = createSequenceDiagramElement("div", "seq-diagram-actions");
      const viewBtn = createSequenceDiagramElement("button", "seq-diagram-action active", "图形");
      viewBtn.type = "button";
      const sourceBtn = createSequenceDiagramElement("button", "seq-diagram-action", "源码");
      sourceBtn.type = "button";
      const copyBtn = createSequenceDiagramElement("button", "seq-diagram-action", "复制源码");
      copyBtn.type = "button";
      actions.appendChild(viewBtn);
      actions.appendChild(sourceBtn);
      actions.appendChild(copyBtn);
      toolbar.appendChild(actions);
      card.appendChild(toolbar);

      const scroll = createSequenceDiagramElement("div", "seq-diagram-scroll");
      const stage = createSequenceDiagramElement("div", "seq-diagram-stage");
      setSequenceGridColumns(stage, participantCount);
      stage.setAttribute("role", "img");
      stage.setAttribute("aria-label", "时序图，" + participantCount + " 个参与方，" + parsed.items.length + " 个事件");

      const heads = createSequenceDiagramElement("div", "seq-diagram-participants");
      setSequenceGridColumns(heads, participantCount);
      parsed.participants.forEach((participant) => {
        const head = createSequenceDiagramElement("div", "seq-diagram-participant");
        head.classList.add("is-" + (participant.kind === "actor" ? "actor" : "participant"));
        head.appendChild(createSequenceDiagramElement("div", "seq-diagram-participant-label", participant.label));
        head.appendChild(createSequenceDiagramElement("div", "seq-diagram-participant-id", participant.id));
        heads.appendChild(head);
      });
      stage.appendChild(heads);

      const body = createSequenceDiagramElement("div", "seq-diagram-rows");
      let messageIndex = 0;
      parsed.items.forEach((item) => {
        const row = createSequenceDiagramElement("div", "seq-diagram-row");
        setSequenceGridColumns(row, participantCount);
        appendSequenceLanes(row, participantCount);
        if (item.type === "message") {
          messageIndex += 1;
          const fromIndex = indexById[item.from];
          const toIndex = indexById[item.to];
          const minIndex = Math.min(fromIndex, toIndex);
          const maxIndex = Math.max(fromIndex, toIndex);
          const message = createSequenceDiagramElement("div", "seq-diagram-message");
          message.classList.add(fromIndex > toIndex ? "is-reverse" : "is-forward");
          if (fromIndex === toIndex) message.classList.add("is-self");
          if (item.arrow === "-->>") message.classList.add("is-dashed");
          message.style.gridColumn = String(minIndex + 1) + " / " + String(maxIndex + 2);
          const label = createSequenceDiagramElement("div", "seq-diagram-message-label");
          if (parsed.autonumber) {
            label.appendChild(createSequenceDiagramElement("span", "seq-diagram-message-index", String(messageIndex)));
          }
          label.appendChild(createSequenceDiagramElement("span", "seq-diagram-message-text", item.text));
          message.appendChild(label);
          row.appendChild(message);
        } else if (item.type === "note") {
          const indexes = item.over.map((id) => indexById[id]).filter((idx) => Number.isFinite(idx));
          const minIndex = Math.min.apply(null, indexes);
          const maxIndex = Math.max.apply(null, indexes);
          const note = createSequenceDiagramElement("div", "seq-diagram-note");
          note.style.gridColumn = String(minIndex + 1) + " / " + String(maxIndex + 2);
          note.appendChild(createSequenceDiagramElement("span", "seq-diagram-note-kicker", "Note"));
          note.appendChild(createSequenceDiagramElement("span", "seq-diagram-note-text", item.text));
          row.appendChild(note);
        }
        body.appendChild(row);
      });
      stage.appendChild(body);
      scroll.appendChild(stage);
      card.appendChild(scroll);

      const sourcePre = createSequenceDiagramElement("pre", "seq-diagram-source");
      sourcePre.hidden = true;
      const sourceCode = createSequenceDiagramElement("code", "", parsed.source);
      sourcePre.appendChild(sourceCode);
      card.appendChild(sourcePre);

      function setMode(mode) {
        const showSource = mode === "source";
        card.classList.toggle("show-source", showSource);
        scroll.hidden = showSource;
        sourcePre.hidden = !showSource;
        viewBtn.classList.toggle("active", !showSource);
        sourceBtn.classList.toggle("active", showSource);
        viewBtn.setAttribute("aria-pressed", showSource ? "false" : "true");
        sourceBtn.setAttribute("aria-pressed", showSource ? "true" : "false");
      }
      viewBtn.addEventListener("click", () => setMode("diagram"));
      sourceBtn.addEventListener("click", () => setMode("source"));
      copyBtn.addEventListener("click", async () => {
        const ok = await copySequenceDiagramSource(parsed.source);
        copyBtn.textContent = ok ? "已复制" : "复制失败";
        window.setTimeout(() => {
          copyBtn.textContent = "复制源码";
        }, ok ? 1200 : 1800);
      });
      setMode("diagram");
      return card;
    }

    const FLOWCHART_DIAGRAM_PREVIEW_LIMITS = Object.freeze({
      maxSourceChars: 30000,
      maxNodes: 96,
      maxGroups: 18,
      maxEdges: 180,
      maxLineChars: 1600,
      maxLabelChars: 180,
    });

    function flowchartDiagramLimits(opts = {}) {
      const raw = opts && typeof opts === "object" ? (opts.limits || {}) : {};
      return Object.assign({}, FLOWCHART_DIAGRAM_PREVIEW_LIMITS, raw || {});
    }

    function isFlowchartDiagramFirstLine(source) {
      const first = firstMeaningfulSequenceDiagramLine(normalizeSequenceDiagramSource(source).split("\n"));
      return /^(?:flowchart|graph)\s+(?:TB|TD|BT|RL|LR)\s*$/i.test(first.line);
    }

    function normalizeFlowchartTextLabel(value, maxLen) {
      let text = String(value || "").trim();
      if ((text.startsWith("\"") && text.endsWith("\"")) || (text.startsWith("'") && text.endsWith("'"))) {
        text = text.slice(1, -1);
      }
      text = text.replace(/<br\s*\/?>/gi, "\n").replace(/\\n/g, "\n").trim();
      const limit = Math.max(20, Number(maxLen) || FLOWCHART_DIAGRAM_PREVIEW_LIMITS.maxLabelChars);
      return text.length > limit ? (text.slice(0, limit - 1) + "…") : text;
    }

    function normalizeFlowchartNodeId(value) {
      const id = String(value || "").trim();
      if (!id || /\s/.test(id) || id.length > 80) return "";
      if (!/^[A-Za-z0-9_$.-]+$/.test(id)) return "";
      return id;
    }

    function parseFlowchartNodeRef(raw, limits) {
      const text = String(raw || "").trim().replace(/;$/, "").trim();
      if (!text) return null;
      const match = text.match(/^([A-Za-z0-9_$.-]+)(?:\s*(?:\[\s*(.+?)\s*\]|\(\s*(.+?)\s*\)|\{\s*(.+?)\s*\}))?$/);
      if (!match) return null;
      const id = normalizeFlowchartNodeId(match[1]);
      if (!id) return null;
      const labelRaw = [match[2], match[3], match[4]].find((item) => String(item || "").trim());
      return {
        id,
        label: normalizeFlowchartTextLabel(labelRaw || id, limits.maxLabelChars) || id,
      };
    }

    function extractMermaidFlowchartFences(markdown, opts = {}) {
      const limits = flowchartDiagramLimits(opts);
      const text = String(markdown || "").replace(/\r\n?/g, "\n");
      if (!text.trim() || text.length > limits.maxSourceChars * 3) return [];
      const lines = text.split("\n");
      const blocks = [];
      let inFence = false;
      let lang = "";
      let code = [];
      for (let i = 0; i < lines.length; i += 1) {
        const line = String(lines[i] || "");
        if (!inFence) {
          const open = line.trim().match(/^```([A-Za-z0-9_-]+)?\s*$/);
          if (!open) continue;
          inFence = true;
          lang = String(open[1] || "").trim().toLowerCase();
          code = [];
          continue;
        }
        if (/^```\s*$/.test(line.trim())) {
          if (lang === "mermaid") {
            const source = normalizeSequenceDiagramSource(code.join("\n"));
            if (source && source.length <= limits.maxSourceChars && isFlowchartDiagramFirstLine(source)) {
              blocks.push({ source, sourceKind: "markdown_fenced", startLine: i - code.length });
            }
          }
          inFence = false;
          lang = "";
          code = [];
          continue;
        }
        code.push(line);
      }
      if (inFence && lang === "mermaid") {
        const source = normalizeSequenceDiagramSource(code.join("\n"));
        if (source && source.length <= limits.maxSourceChars && isFlowchartDiagramFirstLine(source)) {
          blocks.push({ source, sourceKind: "markdown_fenced", startLine: Math.max(0, lines.length - code.length) });
        }
      }
      return blocks;
    }

    function detectFlowchartDiagramSource(content, opts = {}) {
      const sourceKind = String((opts && opts.sourceKind) || "auto");
      const limits = flowchartDiagramLimits(opts);
      const raw = String(content || "");
      if (!raw.trim()) return null;
      if (sourceKind !== "plain_text") {
        const blocks = extractMermaidFlowchartFences(raw, opts);
        if (blocks.length) return blocks[0];
      }
      if (sourceKind !== "markdown_fenced") {
        const source = normalizeSequenceDiagramSource(raw);
        if (source && source.length <= limits.maxSourceChars && isFlowchartDiagramFirstLine(source)) {
          return { source, sourceKind: "plain_text", startLine: 0 };
        }
      }
      return null;
    }

    function readFlowchartEndpoint(text, startIndex) {
      let i = Number(startIndex) || 0;
      while (i < text.length && /\s/.test(text[i])) i += 1;
      const start = i;
      let depth = 0;
      let quote = "";
      for (; i < text.length; i += 1) {
        const ch = text[i];
        const ahead = text.slice(i);
        if (quote) {
          if (ch === quote) quote = "";
          continue;
        }
        if (ch === "\"" || ch === "'") {
          quote = ch;
          continue;
        }
        if (ch === "[" || ch === "(" || ch === "{") {
          depth += 1;
          continue;
        }
        if (ch === "]" || ch === ")" || ch === "}") {
          depth = Math.max(0, depth - 1);
          continue;
        }
        if (depth === 0 && (/^\s*(?:-->|--|-\.)/.test(ahead))) {
          break;
        }
      }
      return { text: text.slice(start, i).trim(), index: i };
    }

    function readFlowchartArrow(text, startIndex) {
      let i = Number(startIndex) || 0;
      while (i < text.length && /\s/.test(text[i])) i += 1;
      if (text.slice(i, i + 3) === "-->") {
        i += 3;
        let label = "";
        if (text[i] === "|") {
          const end = text.indexOf("|", i + 1);
          if (end > i) {
            label = text.slice(i + 1, end);
            i = end + 1;
          }
        }
        return { ok: true, arrow: "-->", label, index: i };
      }
      if (text.slice(i, i + 2) === "--") {
        const end = text.indexOf("-->", i + 2);
        if (end > i) {
          return {
            ok: true,
            arrow: "-->",
            label: text.slice(i + 2, end),
            index: end + 3,
          };
        }
      }
      if (text.slice(i, i + 2) === "-.") {
        const end = text.indexOf(".->", i + 2);
        if (end > i) {
          return {
            ok: true,
            arrow: "-.->",
            label: text.slice(i + 2, end),
            index: end + 3,
          };
        }
      }
      return { ok: false, reason: "unsupported_edge_arrow", index: i };
    }

    function parseFlowchartEdgesLine(line, limits) {
      const edges = [];
      let left = readFlowchartEndpoint(line, 0);
      if (!left.text) return { ok: false, reason: "invalid_edge_source" };
      let index = left.index;
      while (index < line.length) {
        const arrow = readFlowchartArrow(line, index);
        if (!arrow.ok) return { ok: false, reason: arrow.reason };
        const right = readFlowchartEndpoint(line, arrow.index);
        if (!right.text) return { ok: false, reason: "invalid_edge_target" };
        edges.push({
          fromRef: left.text,
          toRef: right.text,
          label: normalizeFlowchartTextLabel(arrow.label || "", limits.maxLabelChars),
          dashed: arrow.arrow === "-.->",
        });
        left = right;
        index = right.index;
      }
      return edges.length ? { ok: true, edges } : { ok: false, reason: "empty_edge" };
    }

    function parseFlowchartSubgraphHeader(line, limits) {
      const text = String(line || "").replace(/^subgraph\s+/i, "").trim();
      const nodeRef = parseFlowchartNodeRef(text, limits);
      if (nodeRef) return nodeRef;
      const quoted = text.match(/^["'](.+)["']$/);
      if (quoted) {
        const label = normalizeFlowchartTextLabel(quoted[1], limits.maxLabelChars);
        return { id: "group_" + label.replace(/\W+/g, "_").slice(0, 32), label };
      }
      const fallback = normalizeFlowchartTextLabel(text, limits.maxLabelChars);
      if (!fallback) return null;
      return { id: "group_" + fallback.replace(/\W+/g, "_").slice(0, 32), label: fallback };
    }

    function parseFlowchartDiagramSource(source, opts = {}) {
      const limits = flowchartDiagramLimits(opts);
      const normalized = normalizeSequenceDiagramSource(source);
      if (!normalized) return { ok: false, reason: "empty" };
      if (normalized.length > limits.maxSourceChars) return { ok: false, reason: "source_too_large" };
      const lines = normalized.split("\n");
      const first = firstMeaningfulSequenceDiagramLine(lines);
      const head = first.line.match(/^(flowchart|graph)\s+(TB|TD|BT|RL|LR)\s*$/i);
      if (!head) return { ok: false, reason: "not_flowchart_diagram" };

      const direction = head[2].toUpperCase() === "TB" ? "TD" : head[2].toUpperCase();
      const nodes = [];
      const nodeMap = Object.create(null);
      const groups = [];
      const groupMap = Object.create(null);
      const edges = [];
      let currentGroupId = "";

      function ensureGroup(id, label) {
        const safeId = normalizeFlowchartNodeId(id) || ("group_" + String(groups.length + 1));
        const existing = groupMap[safeId];
        if (existing) return existing;
        if (groups.length >= limits.maxGroups) return null;
        const group = {
          id: safeId,
          label: normalizeFlowchartTextLabel(label || safeId, limits.maxLabelChars) || safeId,
          nodes: [],
          implicit: false,
        };
        groups.push(group);
        groupMap[safeId] = group;
        return group;
      }

      function ensureRootGroup() {
        let root = groupMap.__root;
        if (!root) {
          root = {
            id: "__root",
            label: "未分组",
            nodes: [],
            implicit: true,
          };
          groups.push(root);
          groupMap.__root = root;
        }
        return root;
      }

      function addNode(rawRef, groupId) {
        const ref = parseFlowchartNodeRef(rawRef, limits);
        if (!ref) return { ok: false, reason: "invalid_node_ref" };
        let node = nodeMap[ref.id];
        if (!node) {
          if (nodes.length >= limits.maxNodes) return { ok: false, reason: "too_many_nodes" };
          const group = groupId ? ensureGroup(groupId, groupId) : ensureRootGroup();
          if (!group) return { ok: false, reason: "too_many_groups" };
          node = {
            id: ref.id,
            label: ref.label || ref.id,
            groupId: group.id,
          };
          nodes.push(node);
          nodeMap[node.id] = node;
          group.nodes.push(node.id);
          return { ok: true, node };
        }
        if (ref.label && ref.label !== ref.id) node.label = ref.label;
        if (groupId && (!node.groupId || node.groupId === "__root")) {
          const nextGroup = ensureGroup(groupId, groupId);
          if (!nextGroup) return { ok: false, reason: "too_many_groups" };
          const prevGroup = groupMap[node.groupId];
          if (prevGroup) prevGroup.nodes = prevGroup.nodes.filter((id) => id !== node.id);
          node.groupId = nextGroup.id;
          if (!nextGroup.nodes.includes(node.id)) nextGroup.nodes.push(node.id);
        }
        return { ok: true, node };
      }

      for (let i = first.index + 1; i < lines.length; i += 1) {
        const rawLine = String(lines[i] || "");
        const line = rawLine.trim();
        if (!line || line.startsWith("%%")) continue;
        if (line.length > limits.maxLineChars) return { ok: false, reason: "line_too_long", line: i + 1 };

        if (/^subgraph\s+/i.test(line)) {
          if (currentGroupId) return { ok: false, reason: "nested_subgraph_not_supported", line: i + 1 };
          const group = parseFlowchartSubgraphHeader(line, limits);
          if (!group) return { ok: false, reason: "invalid_subgraph", line: i + 1 };
          const added = ensureGroup(group.id, group.label);
          if (!added) return { ok: false, reason: "too_many_groups", line: i + 1 };
          added.label = group.label || added.label;
          currentGroupId = added.id;
          continue;
        }

        if (/^end\s*;?$/i.test(line)) {
          currentGroupId = "";
          continue;
        }

        if (/(?:-->|--|-\.)/.test(line)) {
          if (edges.length >= limits.maxEdges) return { ok: false, reason: "too_many_edges", line: i + 1 };
          const parsedEdges = parseFlowchartEdgesLine(line, limits);
          if (!parsedEdges.ok) return { ok: false, reason: parsedEdges.reason, line: i + 1 };
          for (const edge of parsedEdges.edges) {
            const fromAdded = addNode(edge.fromRef, currentGroupId);
            if (!fromAdded.ok) return { ok: false, reason: fromAdded.reason, line: i + 1 };
            const toAdded = addNode(edge.toRef, currentGroupId);
            if (!toAdded.ok) return { ok: false, reason: toAdded.reason, line: i + 1 };
            edges.push({
              from: fromAdded.node.id,
              to: toAdded.node.id,
              label: edge.label,
              dashed: edge.dashed,
              line: i + 1,
            });
            if (edges.length > limits.maxEdges) return { ok: false, reason: "too_many_edges", line: i + 1 };
          }
          continue;
        }

        const nodeAdded = addNode(line, currentGroupId);
        if (!nodeAdded.ok) return { ok: false, reason: nodeAdded.reason, line: i + 1 };
      }

      const visibleGroups = groups.filter((group) => group.nodes.length);
      if (!nodes.length || !edges.length) return { ok: false, reason: "empty_diagram" };
      return {
        ok: true,
        source: normalized,
        direction,
        groups: visibleGroups,
        nodes,
        edges,
      };
    }

    function createFlowchartSvgElement(tag, attrs = {}) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.keys(attrs || {}).forEach((key) => {
        node.setAttribute(key, String(attrs[key]));
      });
      return node;
    }

    function appendFlowchartTextLines(textNode, value, x, y, opts = {}) {
      const maxLines = Math.max(1, Number(opts.maxLines) || 3);
      const lineHeight = Math.max(12, Number(opts.lineHeight) || 15);
      const rows = String(value || "")
        .split("\n")
        .map((row) => row.trim())
        .filter(Boolean)
        .slice(0, maxLines);
      if (!rows.length) rows.push("");
      rows.forEach((row, index) => {
        const tspan = createFlowchartSvgElement("tspan", {
          x,
          y: y + (index * lineHeight),
        });
        tspan.textContent = row;
        textNode.appendChild(tspan);
      });
    }

    function flowchartNodeTitle(value) {
      return String(value || "").split("\n").map((row) => row.trim()).filter(Boolean)[0] || "";
    }

    function renderFlowchartDiagramPreview(source, opts = {}) {
      if (typeof document === "undefined" || !document.createElement || !document.createElementNS) return null;
      const parsed = opts && opts.parsed && opts.parsed.ok
        ? opts.parsed
        : parseFlowchartDiagramSource(source, opts);
      if (!parsed || !parsed.ok) return null;

      const card = createSequenceDiagramElement("section", "seq-diagram-card flow-diagram-card");
      card.setAttribute("data-source-kind", String((opts && opts.sourceKind) || "flowchart_diagram"));

      const toolbar = createSequenceDiagramElement("div", "seq-diagram-toolbar");
      const heading = createSequenceDiagramElement("div", "seq-diagram-heading");
      heading.appendChild(createSequenceDiagramElement("div", "seq-diagram-title", "架构图预览"));
      heading.appendChild(createSequenceDiagramElement(
        "div",
        "seq-diagram-meta",
        parsed.groups.length + " 个分组 · " + parsed.nodes.length + " 个节点 · " + parsed.edges.length + " 条关系 · " + parsed.direction
      ));
      toolbar.appendChild(heading);

      const actions = createSequenceDiagramElement("div", "seq-diagram-actions");
      const viewBtn = createSequenceDiagramElement("button", "seq-diagram-action active", "图形");
      viewBtn.type = "button";
      const sourceBtn = createSequenceDiagramElement("button", "seq-diagram-action", "源码");
      sourceBtn.type = "button";
      const copyBtn = createSequenceDiagramElement("button", "seq-diagram-action", "复制源码");
      copyBtn.type = "button";
      actions.appendChild(viewBtn);
      actions.appendChild(sourceBtn);
      actions.appendChild(copyBtn);
      toolbar.appendChild(actions);
      card.appendChild(toolbar);

      const scroll = createSequenceDiagramElement("div", "seq-diagram-scroll flow-diagram-scroll");
      const svg = createFlowchartSvgElement("svg", {
        class: "flow-diagram-svg",
        role: "img",
        "aria-label": "架构图，" + parsed.groups.length + " 个分组，" + parsed.nodes.length + " 个节点，" + parsed.edges.length + " 条关系",
      });

      const groupWidth = 260;
      const groupGap = 72;
      const margin = 28;
      const headerHeight = 42;
      const nodeWidth = 214;
      const nodeHeight = 70;
      const nodeGap = 18;
      const nodeLeftPad = 22;
      const nodeTopPad = 58;
      const maxGroupNodes = Math.max.apply(null, parsed.groups.map((group) => group.nodes.length));
      const groupHeight = nodeTopPad + Math.max(1, maxGroupNodes) * nodeHeight + Math.max(0, maxGroupNodes - 1) * nodeGap + 22;
      const width = (margin * 2) + (parsed.groups.length * groupWidth) + Math.max(0, parsed.groups.length - 1) * groupGap;
      const height = margin * 2 + groupHeight;
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.style.minWidth = Math.max(width, 720) + "px";

      const defs = createFlowchartSvgElement("defs");
      const marker = createFlowchartSvgElement("marker", {
        id: "flow-diagram-arrow",
        viewBox: "0 0 10 10",
        refX: "8.5",
        refY: "5",
        markerWidth: "7",
        markerHeight: "7",
        orient: "auto-start-reverse",
      });
      marker.appendChild(createFlowchartSvgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "flow-diagram-arrow-head" }));
      defs.appendChild(marker);
      svg.appendChild(defs);

      const nodePositions = Object.create(null);
      const groupLayer = createFlowchartSvgElement("g", { class: "flow-diagram-groups" });
      parsed.groups.forEach((group, groupIndex) => {
        const x = margin + groupIndex * (groupWidth + groupGap);
        const y = margin;
        const groupNode = createFlowchartSvgElement("g", { class: "flow-diagram-group" + (group.implicit ? " is-implicit" : "") });
        groupNode.appendChild(createFlowchartSvgElement("rect", {
          x,
          y,
          width: groupWidth,
          height: groupHeight,
          rx: "18",
          ry: "18",
          class: "flow-diagram-group-box",
        }));
        const title = createFlowchartSvgElement("text", {
          x: x + 16,
          y: y + 28,
          class: "flow-diagram-group-title",
        });
        title.textContent = group.label;
        groupNode.appendChild(title);
        groupLayer.appendChild(groupNode);

        group.nodes.forEach((nodeId, nodeIndex) => {
          nodePositions[nodeId] = {
            x: x + nodeLeftPad,
            y: y + nodeTopPad + nodeIndex * (nodeHeight + nodeGap),
            width: nodeWidth,
            height: nodeHeight,
          };
        });
      });
      svg.appendChild(groupLayer);

      const edgeLayer = createFlowchartSvgElement("g", { class: "flow-diagram-edges" });
      parsed.edges.forEach((edge) => {
        const from = nodePositions[edge.from];
        const to = nodePositions[edge.to];
        if (!from || !to) return;
        let startX = from.x + from.width;
        let startY = from.y + from.height / 2;
        let endX = to.x;
        let endY = to.y + to.height / 2;
        let d = "";
        if (from.x === to.x) {
          startX = from.x + from.width / 2;
          startY = from.y + from.height;
          endX = to.x + to.width / 2;
          endY = to.y;
          const midY = startY + Math.max(18, (endY - startY) / 2);
          d = "M " + startX + " " + startY + " C " + startX + " " + midY + ", " + endX + " " + midY + ", " + endX + " " + endY;
        } else if (to.x < from.x) {
          startX = from.x;
          endX = to.x + to.width;
          const dx = Math.max(40, Math.abs(startX - endX) / 2);
          d = "M " + startX + " " + startY + " C " + (startX - dx) + " " + startY + ", " + (endX + dx) + " " + endY + ", " + endX + " " + endY;
        } else {
          const dx = Math.max(40, Math.abs(endX - startX) / 2);
          d = "M " + startX + " " + startY + " C " + (startX + dx) + " " + startY + ", " + (endX - dx) + " " + endY + ", " + endX + " " + endY;
        }
        edgeLayer.appendChild(createFlowchartSvgElement("path", {
          d,
          class: "flow-diagram-edge" + (edge.dashed ? " is-dashed" : ""),
          "marker-end": "url(#flow-diagram-arrow)",
        }));
        if (edge.label) {
          const label = createFlowchartSvgElement("text", {
            x: (startX + endX) / 2,
            y: (startY + endY) / 2 - 6,
            class: "flow-diagram-edge-label",
          });
          label.textContent = flowchartNodeTitle(edge.label);
          edgeLayer.appendChild(label);
        }
      });
      svg.appendChild(edgeLayer);

      const nodeLayer = createFlowchartSvgElement("g", { class: "flow-diagram-nodes" });
      parsed.nodes.forEach((node) => {
        const pos = nodePositions[node.id];
        if (!pos) return;
        const nodeGroup = createFlowchartSvgElement("g", { class: "flow-diagram-node" });
        nodeGroup.appendChild(createFlowchartSvgElement("rect", {
          x: pos.x,
          y: pos.y,
          width: pos.width,
          height: pos.height,
          rx: "14",
          ry: "14",
          class: "flow-diagram-node-box",
        }));
        const idText = createFlowchartSvgElement("text", {
          x: pos.x + 12,
          y: pos.y + 18,
          class: "flow-diagram-node-id",
        });
        idText.textContent = node.id;
        nodeGroup.appendChild(idText);
        const label = createFlowchartSvgElement("text", {
          x: pos.x + 12,
          y: pos.y + 38,
          class: "flow-diagram-node-label",
        });
        appendFlowchartTextLines(label, node.label, pos.x + 12, pos.y + 38, { maxLines: 2, lineHeight: 15 });
        nodeGroup.appendChild(label);
        nodeLayer.appendChild(nodeGroup);
      });
      svg.appendChild(nodeLayer);
      scroll.appendChild(svg);
      card.appendChild(scroll);

      const sourcePre = createSequenceDiagramElement("pre", "seq-diagram-source");
      sourcePre.hidden = true;
      sourcePre.appendChild(createSequenceDiagramElement("code", "", parsed.source));
      card.appendChild(sourcePre);

      function setMode(mode) {
        const showSource = mode === "source";
        card.classList.toggle("show-source", showSource);
        scroll.hidden = showSource;
        sourcePre.hidden = !showSource;
        viewBtn.classList.toggle("active", !showSource);
        sourceBtn.classList.toggle("active", showSource);
        viewBtn.setAttribute("aria-pressed", showSource ? "false" : "true");
        sourceBtn.setAttribute("aria-pressed", showSource ? "true" : "false");
      }
      viewBtn.addEventListener("click", () => setMode("diagram"));
      sourceBtn.addEventListener("click", () => setMode("source"));
      copyBtn.addEventListener("click", async () => {
        const ok = await copySequenceDiagramSource(parsed.source);
        copyBtn.textContent = ok ? "已复制" : "复制失败";
        window.setTimeout(() => {
          copyBtn.textContent = "复制源码";
        }, ok ? 1200 : 1800);
      });
      setMode("diagram");
      return card;
    }

    function buildFlowchartDiagramViewer(content, opts = {}) {
      const detected = detectFlowchartDiagramSource(content, opts);
      if (!detected) return null;
      return renderFlowchartDiagramPreview(detected.source, Object.assign({}, opts, { sourceKind: detected.sourceKind }));
    }

    function buildSequenceDiagramViewer(content, opts = {}) {
      const detected = detectSequenceDiagramSource(content, opts);
      if (!detected) return buildFlowchartDiagramViewer(content, opts);
      return renderSequenceDiagramPreview(detected.source, Object.assign({}, opts, { sourceKind: detected.sourceKind }));
    }

    function enhanceDiagramTypedBlocks(root, opts = {}) {
      if (!root || !root.querySelectorAll) return;
      Array.from(root.querySelectorAll("pre.md-code[data-lang=\"mermaid\"]")).forEach((block) => {
        if (!block || block.__diagramTypedEnhanced) return;
        const code = block.querySelector("code");
        const source = normalizeSequenceDiagramSource(String((code || block).textContent || ""));
        if (!source) return;
        const viewer = isSequenceDiagramFirstLine(source)
          ? renderSequenceDiagramPreview(source, Object.assign({}, opts, { sourceKind: "markdown_fenced" }))
          : (isFlowchartDiagramFirstLine(source)
            ? renderFlowchartDiagramPreview(source, Object.assign({}, opts, { sourceKind: "markdown_fenced" }))
            : null);
        if (!viewer) return;
        block.__diagramTypedEnhanced = true;
        block.replaceWith(viewer);
      });
    }

    if (typeof globalThis !== "undefined") {
      globalThis.SEQUENCE_DIAGRAM_PREVIEW_LIMITS = SEQUENCE_DIAGRAM_PREVIEW_LIMITS;
      globalThis.detectSequenceDiagramSource = detectSequenceDiagramSource;
      globalThis.parseSequenceDiagramSource = parseSequenceDiagramSource;
      globalThis.renderSequenceDiagramPreview = renderSequenceDiagramPreview;
      globalThis.buildSequenceDiagramViewer = buildSequenceDiagramViewer;
      globalThis.detectFlowchartDiagramSource = detectFlowchartDiagramSource;
      globalThis.parseFlowchartDiagramSource = parseFlowchartDiagramSource;
      globalThis.renderFlowchartDiagramPreview = renderFlowchartDiagramPreview;
      globalThis.buildFlowchartDiagramViewer = buildFlowchartDiagramViewer;
      globalThis.enhanceDiagramTypedBlocks = enhanceDiagramTypedBlocks;
    }
