export function initResultsFilters(): void {
  const familyFilter = document.getElementById('family-filter') as HTMLSelectElement | null;
  const attemptedFilter = document.getElementById('attempted-filter') as HTMLSelectElement | null;
  const statusFilter = document.getElementById('status-filter') as HTMLSelectElement | null;
  const searchInput = document.getElementById('search-input') as HTMLInputElement | null;
  const resetButton = document.getElementById('reset-filters') as HTMLButtonElement | null;
  const visibleCountDisplay = document.getElementById('visible-count');
  const container = document.getElementById('results-table-container');
  const tabs = document.querySelectorAll<HTMLElement>('.quick-filter-tab');

  let activeTab = 'all';

  function applyFilters(): void {
    const fam = (familyFilter?.value || '').toLowerCase().trim();
    const att = (attemptedFilter?.value || '').trim();
    const stat = (statusFilter?.value || '').toLowerCase().trim();
    const query = (searchInput?.value || '').toLowerCase().trim();

    const rows = container?.querySelectorAll<HTMLTableRowElement>('tbody tr') || [];
    let visibleCount = 0;

    rows.forEach((tr) => {
      const rowFam = (tr.getAttribute('data-family') || '').toLowerCase();
      const rowAtt = tr.getAttribute('data-attempted') || 'no';
      const rowComp = tr.getAttribute('data-comparison') || '';
      const rowStat = (tr.getAttribute('data-status') || '').toLowerCase();
      const rowTier = (tr.getAttribute('data-tier') || 'benchmark').toLowerCase();
      const rowPriority = tr.getAttribute('data-priority') || 'no';
      const rowSearch = (tr.getAttribute('data-search') || tr.innerText || '').toLowerCase();

      let matchesTab = true;
      if (activeTab === 'NEW_BEST') matchesTab = rowComp === 'NEW_BEST';
      else if (activeTab === 'proved_optimal') matchesTab = rowStat === 'proved_optimal';
      else if (activeTab === 'priority') matchesTab = rowPriority === 'yes';
      else if (activeTab === 'frontier') matchesTab = rowTier === 'frontier';

      const matchesFam = !fam || rowFam === fam;

      let matchesAtt = true;
      if (att === 'yes') matchesAtt = rowAtt === 'yes';
      else if (att === 'no') matchesAtt = rowAtt === 'no';
      else if (att === 'NEW_BEST') matchesAtt = rowComp === 'NEW_BEST';
      else if (att === 'matches_best_known') matchesAtt = rowComp === 'matches_best_known';
      else if (att === 'worse_than_best_known') matchesAtt = rowComp === 'worse_than_best_known';

      const matchesStat = !stat || rowStat === stat;
      const matchesQuery = !query || rowSearch.includes(query);

      if (matchesTab && matchesFam && matchesAtt && matchesStat && matchesQuery) {
        tr.style.display = '';
        visibleCount++;
      } else {
        tr.style.display = 'none';
      }
    });

    if (visibleCountDisplay) {
      visibleCountDisplay.textContent = visibleCount.toLocaleString();
    }
  }

  function setActiveTab(tabKey: string): void {
    activeTab = tabKey;
    tabs.forEach((tab) => {
      const isSelected = tab.getAttribute('data-tab') === tabKey;
      tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      tab.className = 'quick-filter-tab px-3.5 py-2 rounded-lg text-xs font-semibold border transition-colors flex items-center gap-2 cursor-pointer font-sans';

      if (isSelected) {
        if (tabKey === 'NEW_BEST') {
          tab.classList.add('bg-amber-500/10', 'border-amber-500', 'text-amber-300');
        } else if (tabKey === 'proved_optimal') {
          tab.classList.add('bg-emerald-500/10', 'border-emerald-500', 'text-emerald-300');
        } else if (tabKey === 'priority') {
          tab.classList.add('bg-sky-500/10', 'border-sky-500', 'text-sky-300');
        } else if (tabKey === 'frontier') {
          tab.classList.add('bg-violet-500/10', 'border-violet-500', 'text-violet-300');
        } else {
          tab.classList.add('bg-surface', 'border-slate-600', 'text-white');
        }
      } else {
        tab.classList.add('bg-surface/50', 'border-slate-800', 'text-slate-400', 'hover:text-slate-200', 'hover:border-slate-700');
      }
    });

    applyFilters();
  }

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const tabKey = tab.getAttribute('data-tab') || 'all';
      setActiveTab(tabKey);
    });
  });

  familyFilter?.addEventListener('change', applyFilters);
  attemptedFilter?.addEventListener('change', applyFilters);
  statusFilter?.addEventListener('change', applyFilters);
  searchInput?.addEventListener('input', applyFilters);
  resetButton?.addEventListener('click', () => {
    if (familyFilter) familyFilter.value = '';
    if (attemptedFilter) attemptedFilter.value = '';
    if (statusFilter) statusFilter.value = '';
    if (searchInput) searchInput.value = '';
    setActiveTab('all');
  });

  const urlParams = new URLSearchParams(window.location.search);
  const initialTab = urlParams.get('tab');
  if (initialTab && ['all', 'NEW_BEST', 'proved_optimal', 'priority', 'frontier'].includes(initialTab)) {
    setActiveTab(initialTab);
  }
}
