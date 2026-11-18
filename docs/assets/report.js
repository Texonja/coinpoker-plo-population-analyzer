document.querySelectorAll("[data-review-table]").forEach((table) => {
  const detail = document.getElementById(table.dataset.detail);
  if (!detail) return;
  function select(row) {
    table.querySelectorAll("tbody tr").forEach((candidate) => {
      candidate.setAttribute("aria-selected", String(candidate === row));
      candidate.tabIndex = candidate === row ? 0 : -1;
    });
    const data = JSON.parse(row.dataset.detail);
    Object.entries(data).forEach(([key, value]) => {
      const field = detail.querySelector('[data-field="' + key + '"]');
      if (field) field.textContent = value;
    });
    ["bet", "check", "fold", "call", "raise"].forEach((action) => {
      const bar = detail.querySelector('[data-bar="' + action + '"]');
      if (bar) bar.style.width = Math.max(0, Math.min(100, parseFloat(data[action]) || 0)) + "%";
    });
  }
  table.querySelectorAll("tbody tr").forEach((row) => {
    row.addEventListener("click", () => select(row));
    row.addEventListener("keydown", (event) => {
      const rows = [...table.querySelectorAll("tbody tr")];
      const index = rows.indexOf(row);
      let next;
      if (event.key === "ArrowDown") next = rows[Math.min(rows.length - 1, index + 1)];
      if (event.key === "ArrowUp") next = rows[Math.max(0, index - 1)];
      if (event.key === "Home") next = rows[0];
      if (event.key === "End") next = rows[rows.length - 1];
      if (next) {
        event.preventDefault();
        select(next);
        next.focus({preventScroll:true});
        next.scrollIntoView({block:"nearest"});
      }
    });
  });
});
