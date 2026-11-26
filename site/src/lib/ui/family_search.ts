export function initFamilySearch(): void {
  const searchInput = document.getElementById('family-search') as HTMLInputElement | null;
  const grid = document.getElementById('family-grid');
  const visibleCount = document.getElementById('visible-count');
  const noResults = document.getElementById('no-results');

  function filterFamilies(): void {
    const query = (searchInput?.value || '').toLowerCase().trim();
    const cards = grid?.querySelectorAll<HTMLElement>('a') || [];
    let visible = 0;

    cards.forEach((card) => {
      const text = card.getAttribute('data-family-name') || '';
      if (!query || text.includes(query)) {
        card.style.display = '';
        visible++;
      } else {
        card.style.display = 'none';
      }
    });

    if (visibleCount) {
      visibleCount.textContent = String(visible);
    }
    if (noResults) {
      if (visible === 0) {
        noResults.classList.remove('hidden');
      } else {
        noResults.classList.add('hidden');
      }
    }
  }

  searchInput?.addEventListener('input', filterFamilies);
}
