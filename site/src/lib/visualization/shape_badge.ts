/**
 * Shape Badge SVG Generator
 * Generates mini 20x20 geometric badges for shape packing problem families.
 * Shows container boundary (stroke #64748b) with nested inner shape (fill #38bdf8 or #f59e0b).
 */

export interface FamilyTokens {
  inner: string;
  container: string;
}

/**
 * Parse a family slug into inner and container shape tokens.
 * e.g. "3_in_4" -> { inner: "3", container: "4" }
 * e.g. "circle_in_3" -> { inner: "circle", container: "3" }
 */
export function parseFamilySlug(slug: string): FamilyTokens {
  if (!slug) return { inner: 'circle', container: '4' };
  const parts = slug.split('_in_');
  if (parts.length === 2) {
    return { inner: parts[0], container: parts[1] };
  }
  return { inner: 'circle', container: '4' };
}

function getPolygonPoints(sides: number, radius: number, offsetAngle: number): string {
  const points: string[] = [];
  const step = (2 * Math.PI) / sides;
  for (let i = 0; i < sides; i++) {
    const angle = offsetAngle + i * step;
    const x = (radius * Math.cos(angle)).toFixed(1);
    const y = (radius * Math.sin(angle)).toFixed(1);
    points.push(`${x},${y}`);
  }
  return points.join(' ');
}

function renderContainerElement(token: string): string {
  const t = token.toLowerCase();
  const stroke = '#64748b';
  const strokeWidth = '1.25';

  if (t === 'circle' || t === 'cir' || t === '0') {
    return `<circle cx="0" cy="0" r="8" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" />`;
  }
  if (t === 'ellipse') {
    return `<ellipse cx="0" cy="0" rx="8.5" ry="5.5" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" />`;
  }
  if (t === 'domino') {
    return `<rect x="-8" y="-4.2" width="16" height="8.4" rx="1" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" />`;
  }
  if (t === '4' || t === 'square') {
    return `<rect x="-7.2" y="-7.2" width="14.4" height="14.4" rx="1" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" />`;
  }
  if (t === '3' || t === 'triangle') {
    return `<polygon points="0.0,-8.2 7.2,4.8 -7.2,4.8" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '5' || t === 'pentagon') {
    const pts = getPolygonPoints(5, 8.0, -Math.PI / 2);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '6' || t === 'hexagon') {
    const pts = getPolygonPoints(6, 8.0, -Math.PI / 2);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '8' || t === 'octagon') {
    const pts = getPolygonPoints(8, 8.0, -Math.PI / 8);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'tan') {
    return `<polygon points="-7.0,7.0 7.0,7.0 -7.0,-7.0" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'l' || t === 'l-tromino') {
    return `<polygon points="-7.0,-7.0 -1.5,-7.0 -1.5,1.5 7.0,1.5 7.0,7.0 -7.0,7.0" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'semicircle' || t === 'semi') {
    return `<path d="M -8.0,4.0 A 8.0,8.0 0 0,1 8.0,4.0 Z" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'quadrant' || t === 'quad') {
    return `<path d="M -6.5,6.5 L 6.5,6.5 A 13.0,13.0 0 0,0 -6.5,-6.5 Z" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'rhombus' || t === 'rhom' || t === 'diamond') {
    return `<polygon points="8.6,0.0 0.0,5.2 -8.6,0.0 0.0,-5.2" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'parallelogram' || t === 'para') {
    return `<polygon points="-8.5,4.2 3.5,4.2 8.5,-4.2 -3.5,-4.2" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === 'trapezoid' || t === 'trap') {
    return `<polygon points="-8.5,5.0 8.5,5.0 4.2,-5.0 -4.2,-5.0" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '7' || t === 'heptagon') {
    const pts = getPolygonPoints(7, 8.0, -Math.PI / 2);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '9' || t === 'nonagon' || t === 'enneagon') {
    const pts = getPolygonPoints(9, 8.0, -Math.PI / 2);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }
  if (t === '10' || t === 'decagon') {
    const pts = getPolygonPoints(10, 8.0, -Math.PI / 10);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }

  // Fallback regular polygon if numeric
  const sides = parseInt(t, 10);
  if (!isNaN(sides) && sides >= 3) {
    const pts = getPolygonPoints(sides, 8.0, -Math.PI / 2);
    return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linejoin="round" />`;
  }

  return `<rect x="-7.2" y="-7.2" width="14.4" height="14.4" rx="1" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" />`;
}

function renderInnerElement(token: string, fill: string): string {
  const t = token.toLowerCase();

  if (t === 'circle' || t === 'cir' || t === '0') {
    return `<circle cx="0" cy="0" r="3.2" fill="${fill}" />`;
  }
  if (t === 'line') {
    return `<line x1="-3.8" y1="0" x2="3.8" y2="0" stroke="${fill}" stroke-width="1.8" stroke-linecap="round" />`;
  }
  if (t === 'domino') {
    return `<rect x="-3.5" y="-1.8" width="7" height="3.6" rx="0.5" fill="${fill}" />`;
  }
  if (t === '4' || t === 'square') {
    return `<rect x="-3.0" y="-3.0" width="6.0" height="6.0" rx="0.5" fill="${fill}" />`;
  }
  if (t === '3' || t === 'triangle') {
    return `<polygon points="0.0,-3.8 3.5,2.4 -3.5,2.4" fill="${fill}" />`;
  }
  if (t === '5' || t === 'pentagon') {
    const pts = getPolygonPoints(5, 3.8, -Math.PI / 2);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }
  if (t === '6' || t === 'hexagon') {
    const pts = getPolygonPoints(6, 3.8, -Math.PI / 2);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }
  if (t === '8' || t === 'octagon') {
    const pts = getPolygonPoints(8, 3.8, -Math.PI / 8);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }
  if (t === 'tan') {
    return `<polygon points="-3.2,3.2 3.2,3.2 -3.2,-3.2" fill="${fill}" />`;
  }
  if (t === 'l' || t === 'l-tromino') {
    return `<polygon points="-3.2,-3.2 -0.8,-3.2 -0.8,0.8 3.2,0.8 3.2,3.2 -3.2,3.2" fill="${fill}" />`;
  }
  if (t === 'semicircle' || t === 'semi') {
    return `<path d="M -3.5,1.8 A 3.5,3.5 0 0,1 3.5,1.8 Z" fill="${fill}" />`;
  }
  if (t === 'quadrant' || t === 'quad') {
    return `<path d="M -2.5,2.5 L 3.0,2.5 A 5.5,5.5 0 0,0 -2.5,-3.0 Z" fill="${fill}" />`;
  }
  if (t === 'rhombus' || t === 'rhom' || t === 'diamond') {
    return `<polygon points="4.0,0.0 0.0,2.4 -4.0,0.0 0.0,-2.4" fill="${fill}" />`;
  }
  if (t === 'parallelogram' || t === 'para') {
    return `<polygon points="-4.0,2.0 1.6,2.0 4.0,-2.0 -1.6,-2.0" fill="${fill}" />`;
  }
  if (t === 'trapezoid' || t === 'trap') {
    return `<polygon points="-4.0,2.4 4.0,2.4 2.0,-2.4 -2.0,-2.4" fill="${fill}" />`;
  }
  if (t === '7' || t === 'heptagon') {
    const pts = getPolygonPoints(7, 3.8, -Math.PI / 2);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }
  if (t === '9' || t === 'nonagon' || t === 'enneagon') {
    const pts = getPolygonPoints(9, 3.8, -Math.PI / 2);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }
  if (t === '10' || t === 'decagon') {
    const pts = getPolygonPoints(10, 3.8, -Math.PI / 10);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }

  // Fallback regular polygon if numeric
  const sides = parseInt(t, 10);
  if (!isNaN(sides) && sides >= 3) {
    const pts = getPolygonPoints(sides, 3.8, -Math.PI / 2);
    return `<polygon points="${pts}" fill="${fill}" />`;
  }

  return `<circle cx="0" cy="0" r="3.2" fill="${fill}" />`;
}

/**
 * Generate a 20x20 SVG string representing the problem family geometric badge.
 * @param innerToken The inner shape (e.g. "3", "circle", "domino", "L", "tan")
 * @param containerToken The container shape (e.g. "4", "3", "circle", "domino", "L", "ellipse")
 * @param isCadmium Whether to use cadmium gold (#f59e0b) for broken record styling
 */
export function generateShapeBadgeSvg(
  innerToken: string | number,
  containerToken: string | number,
  isCadmium: boolean = false
): string {
  const innerStr = String(innerToken || 'circle');
  const containerStr = String(containerToken || '4');
  const fill = isCadmium ? '#f59e0b' : '#38bdf8';

  const containerSvg = renderContainerElement(containerStr);
  const innerSvg = renderInnerElement(innerStr, fill);

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 20 20" width="20" height="20" class="shrink-0 pointer-events-none" aria-hidden="true">${containerSvg}${innerSvg}</svg>`;
}

/**
 * Alias for generateShapeBadgeSvg as requested by specification.
 */
export const getShapeBadgeSvg = generateShapeBadgeSvg;

