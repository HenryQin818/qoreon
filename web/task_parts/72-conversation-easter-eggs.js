(function () {
  const root = typeof window !== "undefined" ? window : globalThis;

  const EASTER_EGG_STORAGE_KEY = "taskDashboard.conversationEasterEgg.seen";
  const EASTER_EGG_MAX_SEEN = 80;
  const EASTER_EGG_COOLDOWN_MS = 2200;

  const EASTER_EGG_RULES = [
    {
      id: "start",
      tone: "start",
      title: "开工大吉",
      subtitle: "开始干活儿，礼花到位",
      iconSet: "tools",
      keywords: ["开工大吉", "开工", "开始", "启动", "执行"],
      maxLength: 48,
    },
    {
      id: "nice-work",
      tone: "gold",
      title: "干得漂亮",
      subtitle: "这一步完成得很扎实",
      iconSet: "celebration",
      keywords: ["干得漂亮"],
      maxLength: 64,
    },
    {
      id: "well-done",
      tone: "green",
      title: "做得好",
      subtitle: "结果稳定，继续收口",
      iconSet: "celebration",
      keywords: ["做得好", "做得不错"],
      maxLength: 64,
    },
    {
      id: "thanks",
      tone: "warm",
      title: "辛苦了",
      subtitle: "这一轮推进已记录",
      iconSet: "celebration",
      keywords: ["辛苦了"],
      maxLength: 64,
    },
    {
      id: "bravo",
      tone: "blue",
      title: "太棒了",
      subtitle: "当前成果值得标记一下",
      iconSet: "celebration",
      keywords: ["太棒了", "漂亮"],
      maxLength: 64,
    },
  ];

  const EASTER_EGG_ICON_SETS = {
    tools: [
      {
        id: "hammer",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.2 3.4 21 10.2l-2.1 2.1-2.2-2.2-8.9 8.9a2 2 0 0 1-2.8 0 2 2 0 0 1 0-2.8l8.9-8.9-2.2-2.2 2.5-1.7Z"/></svg>',
      },
      {
        id: "wrench",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.7 6.1a6 6 0 0 1-7.2 7.2L7.4 19.4a2.2 2.2 0 0 1-3.1-3.1l6.1-6.1a6 6 0 0 1 7.2-7.2l-3.1 3.1 3.1 3.1 3.1-3.1Z"/></svg>',
      },
      {
        id: "gear",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.3 2.5 14 5a7.3 7.3 0 0 1 1.7.7l2.3-1.2 1.6 2.7-2 1.6c.1.6.1 1.2 0 1.8l2 1.6-1.6 2.7-2.3-1.2c-.5.3-1.1.5-1.7.7l-.7 2.5h-3.2l-.7-2.5a7.3 7.3 0 0 1-1.7-.7l-2.3 1.2-1.6-2.7 2-1.6a7.2 7.2 0 0 1 0-1.8l-2-1.6 1.6-2.7 2.3 1.2c.5-.3 1.1-.5 1.7-.7l.7-2.5h3.2Zm-1.6 6a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6Z"/></svg>',
      },
      {
        id: "screwdriver",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16.6 2.7 21.3 7.4l-2.2 2.2-1.4-1.4-7.6 7.6-1.9-.2-.2-1.9 7.6-7.6-1.2-1.2 2.2-2.2ZM7.4 16.4l.2 2.6-2.1 2.1a1.8 1.8 0 0 1-2.6-2.6L5 16.4h2.4Z"/></svg>',
      },
    ],
    celebration: [
      {
        id: "star",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2.8 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.8l-5.4 2.8 1-6.1-4.4-4.3 6.1-.9L12 2.8Z"/></svg>',
      },
      {
        id: "medal",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h4l1 4 1-4h4l-3 6.2a6 6 0 1 1-4 0L7 2Zm5 8.5a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4Z"/></svg>',
      },
      {
        id: "spark",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 14 9.4 21.4 12 14 14.6 12 22l-2-7.4L2.6 12 10 9.4 12 2Z"/></svg>',
      },
      {
        id: "ribbon",
        svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5a5.5 5.5 0 0 1 3.4 9.8l2.1 8.2-5.5-3-5.5 3 2.1-8.2A5.5 5.5 0 0 1 12 2.5Zm0 3.2a2.3 2.3 0 1 0 0 4.6 2.3 2.3 0 0 0 0-4.6Z"/></svg>',
      },
    ],
  };

  const seenElements = typeof WeakSet === "function" ? new WeakSet() : null;
  let observer = null;
  let retryTimer = null;
  let lastPlayAt = 0;

  function normalizeConversationEasterEggText(text) {
    return String(text || "")
      .replace(/\u00a0/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function compactConversationEasterEggText(text) {
    return normalizeConversationEasterEggText(text).replace(/[，。！？、；;：:,.!?\s"'“”‘’（）()【】\[\]<>《》]/g, "");
  }

  function hashConversationEasterEggText(text) {
    const normalized = normalizeConversationEasterEggText(text);
    let hash = 0;
    for (let i = 0; i < normalized.length; i += 1) {
      hash = ((hash << 5) - hash + normalized.charCodeAt(i)) | 0;
    }
    return Math.abs(hash).toString(36);
  }

  function matchConversationEasterEgg(text) {
    const normalized = normalizeConversationEasterEggText(text);
    if (!normalized) return null;
    const compact = compactConversationEasterEggText(normalized);
    if (!compact) return null;
    for (const rule of EASTER_EGG_RULES) {
      for (const keyword of rule.keywords) {
        if (!compact.includes(keyword)) continue;
        if (normalized.length > rule.maxLength && compact !== keyword && keyword !== "开工大吉") {
          continue;
        }
        return {
          id: rule.id,
          tone: rule.tone,
          iconSet: rule.iconSet || "celebration",
          title: keyword === "做得不错" ? "做得不错" : rule.title,
          subtitle: rule.subtitle,
          keyword,
        };
      }
    }
    return null;
  }

  function readConversationEasterEggSeen() {
    if (!root.sessionStorage) return [];
    try {
      const raw = root.sessionStorage.getItem(EASTER_EGG_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
    } catch (_) {
      return [];
    }
  }

  function writeConversationEasterEggSeen(items) {
    if (!root.sessionStorage) return;
    try {
      root.sessionStorage.setItem(EASTER_EGG_STORAGE_KEY, JSON.stringify(items.slice(-EASTER_EGG_MAX_SEEN)));
    } catch (_) {
      // 彩蛋状态不参与业务逻辑，存储失败时直接降级为当前页去重。
    }
  }

  function rememberConversationEasterEgg(key) {
    if (!key) return false;
    const items = readConversationEasterEggSeen();
    if (items.includes(key)) return false;
    items.push(key);
    writeConversationEasterEggSeen(items);
    return true;
  }

  function conversationEasterEggReducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function removeExistingConversationEasterEggLayer() {
    if (!root.document) return;
    root.document.querySelectorAll(".conv-easteregg-layer").forEach((node) => node.remove());
  }

  function buildConversationEasterEggPiece(index, total) {
    const piece = root.document.createElement("i");
    piece.className = "conv-easteregg-piece";
    const angle = (Math.PI * 2 * index) / Math.max(total, 1);
    const distance = 150 + ((index * 37) % 160);
    const x = Math.cos(angle) * distance;
    const y = Math.sin(angle) * distance - 30 - ((index * 19) % 90);
    piece.style.setProperty("--egg-x", x.toFixed(1) + "px");
    piece.style.setProperty("--egg-y", y.toFixed(1) + "px");
    piece.style.setProperty("--egg-rot", ((index * 43) % 420 - 210) + "deg");
    piece.style.setProperty("--egg-delay", ((index % 9) * 26) + "ms");
    piece.style.setProperty("--egg-hue", String((index * 29 + 18) % 360));
    return piece;
  }

  function buildConversationEasterEggIcon(match, index, total) {
    const iconSetName = match && match.iconSet === "tools" ? "tools" : "celebration";
    const iconSet = EASTER_EGG_ICON_SETS[iconSetName] || EASTER_EGG_ICON_SETS.celebration;
    const icon = iconSet[index % iconSet.length];
    const node = root.document.createElement("span");
    node.className = "conv-easteregg-icon icon-" + iconSetName + " icon-" + icon.id;
    node.innerHTML = icon.svg;
    const left = 8 + ((index * 17) % 84);
    const top = 14 + ((index * 23) % 70);
    const drift = (index % 2 === 0 ? 1 : -1) * (18 + ((index * 11) % 46));
    node.style.setProperty("--icon-left", left + "%");
    node.style.setProperty("--icon-top", top + "%");
    node.style.setProperty("--icon-drift", drift + "px");
    node.style.setProperty("--icon-rot", ((index * 31) % 160 - 80) + "deg");
    node.style.setProperty("--icon-delay", ((index % Math.max(total, 1)) * 42) + "ms");
    node.style.setProperty("--icon-size", (34 + ((index * 7) % 18)) + "px");
    return node;
  }

  function buildConversationEasterEggIconField(match, reduced) {
    const field = root.document.createElement("div");
    field.className = "conv-easteregg-icon-field iconset-" + (match && match.iconSet === "tools" ? "tools" : "celebration");
    const iconCount = reduced ? 4 : (match && match.iconSet === "tools" ? 14 : 18);
    for (let i = 0; i < iconCount; i += 1) {
      field.appendChild(buildConversationEasterEggIcon(match, i, iconCount));
    }
    return field;
  }

  function playConversationEasterEgg(match) {
    if (!root.document || !match) return false;
    removeExistingConversationEasterEggLayer();
    const reduced = conversationEasterEggReducedMotion();
    const layer = root.document.createElement("div");
    layer.className = "conv-easteregg-layer tone-" + String(match.tone || "start") + (reduced ? " is-reduced" : "");
    layer.setAttribute("aria-live", "polite");
    layer.setAttribute("aria-label", String(match.title || "彩蛋"));

    const burst = root.document.createElement("div");
    burst.className = "conv-easteregg-burst";
    const pieceCount = reduced ? 0 : 44;
    for (let i = 0; i < pieceCount; i += 1) {
      burst.appendChild(buildConversationEasterEggPiece(i, pieceCount));
    }

    layer.appendChild(burst);
    layer.appendChild(buildConversationEasterEggIconField(match, reduced));
    root.document.body.appendChild(layer);
    const removeDelay = reduced ? 1500 : 2600;
    root.setTimeout(() => {
      layer.classList.add("is-leaving");
      root.setTimeout(() => layer.remove(), 280);
    }, removeDelay);
    return true;
  }

  function triggerConversationEasterEggForText(text, meta = {}) {
    const match = matchConversationEasterEgg(text);
    if (!match) return false;
    const now = Date.now();
    if (now - lastPlayAt < EASTER_EGG_COOLDOWN_MS) return false;
    const sessionId = String(meta.sessionId || meta.session_id || (root.STATE && root.STATE.selectedSessionId) || "").trim();
    const runId = String(meta.runId || meta.run_id || "").trim();
    const source = String(meta.source || "message").trim();
    const key = [sessionId, runId || source, match.id, hashConversationEasterEggText(text)].join("|");
    if (!rememberConversationEasterEgg(key)) return false;
    lastPlayAt = now;
    return playConversationEasterEgg(match);
  }

  function markConversationEasterEggExistingBubble(bubble) {
    if (!bubble || !seenElements) return;
    seenElements.add(bubble);
  }

  function maybeTriggerConversationEasterEggFromBubble(bubble) {
    if (!bubble || !seenElements || seenElements.has(bubble)) return;
    seenElements.add(bubble);
    const row = bubble.closest && bubble.closest(".msgrow.user.self-user");
    if (!row) return;
    const text = String(bubble.innerText || bubble.textContent || "").trim();
    const runId = String((row.dataset && (row.dataset.runId || row.dataset.conversationRunId)) || "").trim();
    triggerConversationEasterEggForText(text, { runId, source: "timeline" });
  }

  function scanConversationEasterEggNode(node) {
    if (!node || !node.querySelectorAll) return;
    const bubbles = [];
    if (node.matches && node.matches(".msgrow.user.self-user .mbubble")) bubbles.push(node);
    node.querySelectorAll(".msgrow.user.self-user .mbubble").forEach((bubble) => bubbles.push(bubble));
    bubbles.forEach(maybeTriggerConversationEasterEggFromBubble);
  }

  function initConversationEasterEggs() {
    if (!root.document || observer) return;
    const timeline = root.document.getElementById("convTimeline");
    if (!timeline) {
      if (!retryTimer) {
        retryTimer = root.setTimeout(() => {
          retryTimer = null;
          initConversationEasterEggs();
        }, 800);
      }
      return;
    }
    timeline.querySelectorAll(".msgrow.user.self-user .mbubble").forEach(markConversationEasterEggExistingBubble);
    observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          root.setTimeout(() => scanConversationEasterEggNode(node), 40);
        });
      });
    });
    observer.observe(timeline, { childList: true, subtree: true });
  }

  root.matchConversationEasterEgg = matchConversationEasterEgg;
  root.triggerConversationEasterEggForText = triggerConversationEasterEggForText;
  root.playConversationEasterEgg = playConversationEasterEgg;
  root.initConversationEasterEggs = initConversationEasterEggs;

  if (root.document) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", initConversationEasterEggs, { once: true });
    } else {
      initConversationEasterEggs();
    }
  }
})();
