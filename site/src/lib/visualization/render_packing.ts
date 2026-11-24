export interface SolutionData {
  S?: number;
  final_metric?: number;
  inner_sides?: number | string;
  container_sides?: number | string;
  inner_token?: number | string;
  container_token?: number | string;
  nsi?: number | string;
  nsc?: number | string;
  N?: number;
  values?: number[];
}

export interface PolygonPoint {
  x: number;
  y: number;
}

export interface TransformedShape {
  cx: number;
  cy: number;
  angle: number;
  isCircle: boolean;
  vertices: PolygonPoint[] | null;
  color: string;
}

export interface PackingSvgData {
  viewBox: string;
  isContainerCircle: boolean;
  containerVertices: PolygonPoint[] | null;
  containerSides: string | number;
  containerOffsetAngle: number;
  innerSides: string | number;
  shapes: TransformedShape[];
  S: number;
  finalMetric: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  spanX: number;
  spanY: number;
  padding: number;
}

export const BLUEPRINT_PALETTE: string[] = [
  '#38bdf8', // cyan
  '#0284c7', // sky
  '#2563eb', // cobalt
  '#818cf8', // slate blue
  '#f59e0b', // cadmium
  '#14b8a6', // teal
  '#10b981', // emerald
];

export const NAMED_SHAPE_SIDES: Record<string, number> = {
  TRIANGLE: 3,
  SQUARE: 4,
  PENTAGON: 5,
  HEXAGON: 6,
  HEPTAGON: 7,
  OCTAGON: 8,
  NONAGON: 9,
  DECAGON: 10,
};

export function parseShapeToken(val: any): string | number {
  if (val === undefined || val === null) return 3;
  const s = String(val).trim().toUpperCase();
  if (s === 'CIRCLE' || s === 'CIR' || s === '0') return 'CIRCLE';
  if (s === 'DOMINO' || s === 'DOM') return 'DOMINO';
  if (s === 'TAN') return 'TAN';
  if (s === 'L' || s === 'L-TROMINO' || s === 'EL') return 'L';
  if (s in NAMED_SHAPE_SIDES) return NAMED_SHAPE_SIDES[s];
  const num = parseInt(s, 10);
  return isNaN(num) ? s : num;
}

// Backward compatibility
export const parseSides = parseShapeToken;

export function getRegularPolygonVertices(sides: number, radius: number = 1.0, offsetAngle: number = 0): PolygonPoint[] {
  const points: PolygonPoint[] = [];
  const angleStep = (2 * Math.PI) / sides;
  for (let i = 0; i < sides; i++) {
    const angle = offsetAngle + i * angleStep;
    points.push({
      x: radius * Math.cos(angle),
      y: radius * Math.sin(angle),
    });
  }
  return points;
}

export function getUnitShapeVertices(token: string | number): PolygonPoint[] | null {
  const parsed = parseShapeToken(token);
  if (parsed === 'CIRCLE') {
    return null; // Circles are rendered via SVG <circle>
  }
  if (parsed === 'DOMINO') {
    return [
      { x: -1.0, y: -0.5 },
      { x: 1.0, y: -0.5 },
      { x: 1.0, y: 0.5 },
      { x: -1.0, y: 0.5 },
    ];
  }
  if (parsed === 'TAN') {
    const r = 1.0 - Math.SQRT2 / 2.0;
    return [
      { x: -r, y: -r },
      { x: 1.0 - r, y: -r },
      { x: -r, y: 1.0 - r },
    ];
  }
  if (parsed === 'L') {
    return [
      { x: -5.0 / 6.0, y: -5.0 / 6.0 },
      { x: 7.0 / 6.0, y: -5.0 / 6.0 },
      { x: 7.0 / 6.0, y: 1.0 / 6.0 },
      { x: 1.0 / 6.0, y: 1.0 / 6.0 },
      { x: 1.0 / 6.0, y: 7.0 / 6.0 },
      { x: -5.0 / 6.0, y: 7.0 / 6.0 },
    ];
  }
  const sides = typeof parsed === 'number' && parsed >= 3 ? parsed : 3;
  return getRegularPolygonVertices(sides, 1.0, 0);
}

export function getContainerRotationOffset(token: any): number {
  const parsed = parseShapeToken(token);
  if (typeof parsed === 'string') {
    return 0.0;
  }
  const sides = parsed;
  if (sides % 2 === 1) {
    return Math.PI / 2.0;
  } else {
    if (Math.floor(sides / 2) % 2 === 0) {
      return Math.PI / sides;
    } else {
      return 0.0;
    }
  }
}

export function inverseFriedmanMetric(fMetric: number, innerToken: any, containerToken: any): number {
  if (!fMetric || isNaN(fMetric) || fMetric <= 0) return 2.0;

  const cToken = parseShapeToken(containerToken);
  const iToken = parseShapeToken(innerToken);

  if (cToken === 'L' && iToken === 'L') {
    return fMetric;
  }

  let iScale = 1.0;
  if (typeof iToken === 'number') {
    iScale = 2.0 * Math.sin(Math.PI / iToken);
  } else if (iToken === 'CIRCLE' || iToken === 'DOMINO' || iToken === 'TAN' || iToken === 'L') {
    iScale = 1.0;
  } else {
    const num = parseInt(String(iToken), 10);
    iScale = !isNaN(num) && num >= 3 ? 2.0 * Math.sin(Math.PI / num) : 1.0;
  }

  const cMetric = fMetric * iScale;

  if (cToken === 'CIRCLE' || cToken === 'TAN' || cToken === 'DOMINO') {
    return cMetric;
  } else if (cToken === 'L') {
    return cMetric / 2.0;
  } else {
    let nsc = 3;
    if (typeof cToken === 'number') {
      nsc = cToken;
    } else {
      const num = parseInt(String(cToken), 10);
      if (!isNaN(num) && num >= 3) nsc = num;
    }
    return cMetric / (2.0 * Math.sin(Math.PI / nsc));
  }
}

export function transformPoint(pt: PolygonPoint, cx: number, cy: number, angle: number): PolygonPoint {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return {
    x: cx + (pt.x * cos - pt.y * sin),
    y: cy + (pt.x * sin + pt.y * cos),
  };
}

export function generatePackingSvgElements(solution: SolutionData, width: number = 400, height: number = 400): PackingSvgData | null {
  if (!solution || !solution.values || !solution.N) {
    return null;
  }

  const N = solution.N;
  const values = solution.values;
  const rawContainer = solution.container_token ?? solution.container_sides ?? solution.nsc;
  const rawInner = solution.inner_token ?? solution.inner_sides ?? solution.nsi;

  const containerToken = parseShapeToken(rawContainer);
  const innerToken = parseShapeToken(rawInner);
  const finalMetric = solution.final_metric || (solution as any).computed_metric || solution.S || 1.0;

  // Mathematically verified container scale factor S:
  const expectedS = inverseFriedmanMetric(finalMetric, innerToken, containerToken);
  let S = solution.S;
  if (!S || S <= 0 || (expectedS > 0 && Math.abs(S - expectedS) > 0.05 * expectedS)) {
    S = expectedS;
  }
  if (!S || S <= 0) {
    S = 1.0;
  }

  const colors = BLUEPRINT_PALETTE;

  const rot = getContainerRotationOffset(containerToken);
  const cos = Math.cos(rot);
  const sin = Math.sin(rot);

  // 1. Build Container Vertices / Bounds
  const isContainerCircle = containerToken === 'CIRCLE';
  let containerVertices: PolygonPoint[] | null = null;
  if (!isContainerCircle) {
    const unitContainer = getUnitShapeVertices(containerToken) || getRegularPolygonVertices(3, 1.0, 0);
    containerVertices = unitContainer.map(pt => {
      const rx = pt.x * cos - pt.y * sin;
      const ry = pt.x * sin + pt.y * cos;
      return {
        x: rx * S,
        y: -ry * S,
      };
    });
  }

  // 2. Build Inner Shapes
  const isInnerCircle = innerToken === 'CIRCLE';
  const unitInnerVertices = isInnerCircle ? null : (getUnitShapeVertices(innerToken) || getRegularPolygonVertices(3, 1.0, 0));

  const shapes: TransformedShape[] = [];
  const stride = Math.floor(values.length / N);

  for (let i = 0; i < N; i++) {
    const idx = i * stride;
    const rawCx = values[idx] || 0;
    const rawCy = values[idx + 1] || 0;
    const rawAngle = stride >= 3 ? (values[idx + 2] || 0) : 0;

    const cx = rawCx * cos - rawCy * sin;
    const cy = rawCx * sin + rawCy * cos;
    const angle = rawAngle + rot;

    let shapeVertices: PolygonPoint[] | null = null;
    if (!isInnerCircle && unitInnerVertices) {
      shapeVertices = unitInnerVertices.map(v => {
        const pt = transformPoint(v, cx, cy, angle);
        return {
          x: pt.x,
          y: -pt.y,
        };
      });
    }

    shapes.push({
      cx,
      cy: -cy,
      angle,
      isCircle: isInnerCircle,
      vertices: shapeVertices,
      color: colors[i % colors.length]
    });
  }

  // 3. Compute ViewBox (centered at origin (0, 0) for perfect symmetry and crosshair alignment)
  let maxExtent = isContainerCircle ? S : 0;

  if (containerVertices) {
    containerVertices.forEach(pt => {
      maxExtent = Math.max(maxExtent, Math.abs(pt.x), Math.abs(pt.y));
    });
  }

  shapes.forEach(s => {
    if (s.isCircle) {
      maxExtent = Math.max(maxExtent, Math.abs(s.cx) + 1.0, Math.abs(s.cy) + 1.0);
    } else if (s.vertices) {
      s.vertices.forEach(pt => {
        maxExtent = Math.max(maxExtent, Math.abs(pt.x), Math.abs(pt.y));
      });
    }
  });

  if (maxExtent <= 0) {
    maxExtent = S > 0 ? S : 2.0;
  }

  const minX = -maxExtent;
  const maxX = maxExtent;
  const minY = -maxExtent;
  const maxY = maxExtent;
  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const padding = maxExtent * 0.08 || 0.2;

  const viewBox = `${(minX - padding).toFixed(4)} ${(minY - padding).toFixed(4)} ${(spanX + 2 * padding).toFixed(4)} ${(spanY + 2 * padding).toFixed(4)}`;

  return {
    viewBox,
    isContainerCircle,
    containerVertices,
    containerSides: containerToken,
    containerOffsetAngle: rot,
    innerSides: innerToken,
    shapes,
    S,
    finalMetric,
    minX,
    maxX,
    minY,
    maxY,
    spanX,
    spanY,
    padding,
  };
}

/**
 * Render solution SVG element string for popovers and lightweight previews.
 */
export function renderSolutionSvgHtml(solution: SolutionData): { svgHtml: string; spanX: number; spanY: number } | null {
  const data = generatePackingSvgElements(solution);
  if (!data) return null;

  const containerElem = data.isContainerCircle
    ? `<circle cx="0" cy="0" r="${data.S.toFixed(4)}" fill="none" stroke="#64748b" stroke-width="0.04" stroke-dasharray="0.1,0.1" />`
    : data.containerVertices
      ? `<polygon points="${data.containerVertices.map(p => `${p.x.toFixed(4)},${p.y.toFixed(4)}`).join(' ')}" fill="none" stroke="#64748b" stroke-width="0.04" stroke-dasharray="0.1,0.1" />`
      : '';

  const shapesElems = data.shapes.map(s => {
    if (s.isCircle) {
      return `<circle cx="${s.cx.toFixed(4)}" cy="${s.cy.toFixed(4)}" r="1" fill="${s.color}" fill-opacity="0.25" stroke="${s.color}" stroke-width="0.03" />`;
    }
    if (s.vertices) {
      const pts = s.vertices.map(p => `${p.x.toFixed(4)},${p.y.toFixed(4)}`).join(' ');
      return `<polygon points="${pts}" fill="${s.color}" fill-opacity="0.25" stroke="${s.color}" stroke-width="0.03" />`;
    }
    return '';
  }).join('');

  const svgHtml = `<svg viewBox="${data.viewBox}" class="w-full h-full overflow-visible">${containerElem}${shapesElems}</svg>`;

  return {
    svgHtml,
    spanX: data.spanX,
    spanY: data.spanY,
  };
}

