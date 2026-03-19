(() => {
  const DATA = JSON.parse(document.getElementById('data').textContent || '{}');
  const totals = DATA.totals || {};
  const rows = Array.isArray(DATA.projects) ? DATA.projects : [];
  const searchInput = document.getElementById('searchInput');
  const rowsEl = document.getElementById('rows');
  const summaryGrid = document.getElementById('summaryGrid');

  document.getElementById('generatedAt').textContent = '更新时间：' + String(DATA.generated_at || '-');
  document.getElementById('tagNeeds').textContent = '待适配 ' + String(totals.needs_adaptation || 0);
  document.getElementById('tagDual').textContent = '双源 ' + String(totals.dual_source_pending || 0);
  document.getElementById('tagReady').textContent = '单源 ' + String(totals.single_source_ready || 0);
  document.getElementById('tagBuilder').textContent = '构建旧源兼容：' + (DATA.builder_legacy_merge ? '是' : '否');

  const summaryCards = [
    ['项目总数', totals.projects || 0, '当前配置在册项目'],
    ['待适配', totals.needs_adaptation || 0, '仍需做数据面改造或清理'],
    ['已有 .sessions', totals.store_ready || 0, '具备单源主数据基础'],
    ['旧源配置', totals.legacy_configured || 0, '仍挂 session_json_rel/session_list_rel'],
    ['仅旧源', totals.legacy_only || 0, '优先迁移批次'],
    ['双源并存', totals.dual_source_pending || 0, '需切运行时口径'],
  ];
  summaryCards.forEach(([k, v, d]) => {
    const card = document.createElement('div');
    card.className = 'summary-card';
    card.innerHTML = '<div class="k">' + k + '</div><div class="v">' + v + '</div><div class="d">' + d + '</div>';
    summaryGrid.appendChild(card);
  });

  function badgeCls(tone) {
    if (tone === 'good') return 'good';
    if (tone === 'danger') return 'danger';
    if (tone === 'warn') return 'warn';
    return 'muted';
  }

  function render(list) {
    rowsEl.innerHTML = '';
    if (!list.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 5;
      td.className = 'empty';
      td.textContent = '没有匹配项目';
      tr.appendChild(td);
      rowsEl.appendChild(tr);
      return;
    }
    list.forEach((row) => {
      const tr = document.createElement('tr');
      const sourceKind = row.legacy_source_kind || '-';
      tr.innerHTML = [
        '<td><div class="project-name">' + (row.project_name || row.project_id || '-') + '</div><div class="project-id">' + (row.project_id || '-') + '</div></td>',
        '<td><span class="badge ' + badgeCls(row.tone) + '">' + (row.status_label || '-') + '</span><div class="project-id" style="margin-top:8px;">' + (row.priority || '-') + '</div></td>',
        '<td><div class="struct-list">'
          + '<div>store：<code>' + (row.store_exists ? 'Y' : 'N') + '</code> / sessions=' + String(row.store_session_count || 0) + '</div>'
          + '<div>legacy：<code>' + (row.legacy_source_exists ? 'Y' : 'N') + '</code> / ' + sourceKind + '</div>'
          + '<div>roots：<code>' + (row.project_root_exists ? 'P' : '-') + (row.task_root_exists ? 'T' : '-') + (row.runtime_root_exists ? 'R' : '-') + '</code></div>'
          + '</div></td>',
        '<td>' + (row.summary || '-') + '</td>',
        '<td>' + (row.next_action || '-') + '</td>'
      ].join('');
      rowsEl.appendChild(tr);
    });
  }

  function applyFilter() {
    const q = String(searchInput.value || '').trim().toLowerCase();
    if (!q) return render(rows);
    const filtered = rows.filter((row) => {
      const hay = [row.project_id, row.project_name, row.status_label, row.priority, row.summary, row.next_action].join(' ').toLowerCase();
      return hay.includes(q);
    });
    render(filtered);
  }

  searchInput.addEventListener('input', applyFilter);
  render(rows);
})();
