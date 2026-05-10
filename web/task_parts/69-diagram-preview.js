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

    function buildSequenceDiagramViewer(content, opts = {}) {
      const detected = detectSequenceDiagramSource(content, opts);
      if (!detected) return null;
      return renderSequenceDiagramPreview(detected.source, Object.assign({}, opts, { sourceKind: detected.sourceKind }));
    }

    function enhanceDiagramTypedBlocks(root, opts = {}) {
      if (!root || !root.querySelectorAll) return;
      Array.from(root.querySelectorAll("pre.md-code[data-lang=\"mermaid\"]")).forEach((block) => {
        if (!block || block.__sequenceDiagramEnhanced) return;
        const code = block.querySelector("code");
        const source = normalizeSequenceDiagramSource(String((code || block).textContent || ""));
        if (!source || !isSequenceDiagramFirstLine(source)) return;
        const viewer = renderSequenceDiagramPreview(source, Object.assign({}, opts, { sourceKind: "markdown_fenced" }));
        if (!viewer) return;
        block.__sequenceDiagramEnhanced = true;
        block.replaceWith(viewer);
      });
    }

    if (typeof globalThis !== "undefined") {
      globalThis.SEQUENCE_DIAGRAM_PREVIEW_LIMITS = SEQUENCE_DIAGRAM_PREVIEW_LIMITS;
      globalThis.detectSequenceDiagramSource = detectSequenceDiagramSource;
      globalThis.parseSequenceDiagramSource = parseSequenceDiagramSource;
      globalThis.renderSequenceDiagramPreview = renderSequenceDiagramPreview;
      globalThis.buildSequenceDiagramViewer = buildSequenceDiagramViewer;
      globalThis.enhanceDiagramTypedBlocks = enhanceDiagramTypedBlocks;
    }
