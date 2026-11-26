function triggerBlobDownload(blob: Blob, filename: string): void {
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
}

export function setupPackingExportButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('.export-svg-btn').forEach((btn) => {
    if (btn.dataset.hasExportHandler === 'true') return;
    btn.dataset.hasExportHandler = 'true';

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      const plate = btn.closest('.packing-plate');
      if (!plate) return;
      const svg = plate.querySelector<SVGSVGElement>('svg.packing-svg');
      if (!svg) return;

      const clone = svg.cloneNode(true) as SVGSVGElement;
      clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');

      const viewBoxAttr = clone.getAttribute('viewBox') || '0 0 100 100';
      const [vx, vy, vw, vh] = viewBoxAttr.trim().split(/[\s,]+/).map(Number);

      const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bgRect.setAttribute('x', String(vx));
      bgRect.setAttribute('y', String(vy));
      bgRect.setAttribute('width', String(vw));
      bgRect.setAttribute('height', String(vh));
      bgRect.setAttribute('fill', '#0b0f17');

      const children = Array.from(clone.childNodes);
      clone.replaceChildren(bgRect, ...children);
      clone.removeAttribute('style');

      const svgSerializer = new XMLSerializer();
      const svgString = '<?xml version="1.0" encoding="UTF-8"?>\n' + svgSerializer.serializeToString(clone);
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
      const filename = btn.getAttribute('data-filename') || 'packing.svg';
      triggerBlobDownload(svgBlob, filename);
    });
  });

  document.querySelectorAll<HTMLButtonElement>('.export-json-btn').forEach((btn) => {
    if (btn.dataset.hasExportHandler === 'true') return;
    btn.dataset.hasExportHandler = 'true';

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const jsonPayload = btn.getAttribute('data-json');
      if (!jsonPayload) return;
      const jsonBlob = new Blob([jsonPayload], { type: 'application/json;charset=utf-8' });
      const filename = btn.getAttribute('data-filename') || 'packing.json';
      triggerBlobDownload(jsonBlob, filename);
    });
  });
}

export function initPackingExports(): void {
  setupPackingExportButtons();
  document.addEventListener('astro:page-load', setupPackingExportButtons);
}
