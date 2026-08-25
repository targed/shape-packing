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

export function parseShapeToken(val: any): string | number {
  if (val === undefined || val === null) return 3;
  const s = String(val).trim().toUpperCase();
  if (s === 'CIRCLE' || s === 'CIR' || s === '0') return 'CIRCLE';
  if (s === 'DOMINO' || s === 'DOM') return 'DOMINO';
  if (s === 'TAN') return 'TAN';
  if (s === 'L' || s === 'L-TROMINO' || s === 'EL') return 'L';
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

export function transformPoint(pt: PolygonPoint, cx: number, cy: number, angle: number): PolygonPoint {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return {
    x: cx + (pt.x * cos - pt.y * sin),
    y: cy + (pt.x * sin + pt.y * cos),
  };
}

export function generatePackingSvgElements(solution: SolutionData, width: number = 400, height: number = 400) {
  if (!solution || !solution.values || !solution.N) {
    return null;
  }

  const N = solution.N;
  const values = solution.values;
  const rawContainer = solution.container_token ?? solution.container_sides ?? solution.nsc;
  const rawInner = solution.inner_token ?? solution.inner_sides ?? solution.nsi;

  const containerToken = parseShapeToken(rawContainer);
  const innerToken = parseShapeToken(rawInner);
  const S = solution.S || 1.0;
  const finalMetric = solution.final_metric || S;

  const colors = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#10b981',
    '#06b6d4', '#3b82f6', '#f59e0b', '#84cc16', '#a855f7'
  ];

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
        y: ry * S,
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
      shapeVertices = unitInnerVertices.map(v => transformPoint(v, cx, cy, angle));
    }

    shapes.push({
      cx,
      cy,
      angle,
      isCircle: isInnerCircle,
      vertices: shapeVertices,
      color: colors[i % colors.length]
    });
  }

  // 3. Compute ViewBox
  let minX = isContainerCircle ? -S : Infinity;
  let maxX = isContainerCircle ? S : -Infinity;
  let minY = isContainerCircle ? -S : Infinity;
  let maxY = isContainerCircle ? S : -Infinity;

  if (containerVertices) {
    containerVertices.forEach(pt => {
      minX = Math.min(minX, pt.x);
      maxX = Math.max(maxX, pt.x);
      minY = Math.min(minY, pt.y);
      maxY = Math.max(maxY, pt.y);
    });
  }

  shapes.forEach(s => {
    if (s.isCircle) {
      minX = Math.min(minX, s.cx - 1.0);
      maxX = Math.max(maxX, s.cx + 1.0);
      minY = Math.min(minY, s.cy - 1.0);
      maxY = Math.max(maxY, s.cy + 1.0);
    } else if (s.vertices) {
      s.vertices.forEach(pt => {
        minX = Math.min(minX, pt.x);
        maxX = Math.max(maxX, pt.x);
        minY = Math.min(minY, pt.y);
        maxY = Math.max(maxY, pt.y);
      });
    }
  });

  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const padding = Math.max(spanX, spanY) * 0.06 || 0.5;

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
    finalMetric
  };
}
