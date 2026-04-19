(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");

  function text(value, fallback = "") {
    const out = String(value == null ? "" : value).trim();
    return out || fallback;
  }

  function canonicalBase() {
    const links = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
    return text(
      links.project_chat_page
      || DATA.project_chat_page
      || links.task_page
      || DATA.task_page,
      "/share/project-task-dashboard.html"
    );
  }

  function targetUrl() {
    const base = canonicalBase();
    const href = /^https?:\/\//i.test(base) || base.startsWith("/")
      ? base
      : ("/share/" + base.replace(/^\/+/, ""));
    const url = new URL(href, window.location.origin);
    const params = new URLSearchParams(window.location.search || "");
    params.forEach((value, key) => {
      if (!url.searchParams.has(key)) url.searchParams.set(key, value);
    });
    return url;
  }

  function applyFallbackLink(url) {
    const link = document.getElementById("redirectTarget");
    if (!link) return;
    link.href = url.toString();
    link.textContent = url.pathname + url.search;
  }

  function redirect() {
    const url = targetUrl();
    applyFallbackLink(url);
    const status = document.getElementById("redirectStatus");
    if (status) {
      status.textContent = "旧 project_chat 已退役，正在跳转到当前主页面 share-mode。";
    }
    window.location.replace(url.toString());
  }

  redirect();
})();
