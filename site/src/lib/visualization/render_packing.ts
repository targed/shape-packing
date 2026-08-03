export interface SolutionData {
  S?: number;
  final_metric?: number;
  inner_sides?: number | string;
  container_sides?: number | string;
  N?: number;
  values?: number[];
}

export interface PolygonPoint {
  x: number;
  y: number;
}

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
  const containerSides = solution.container_sides;
  const innerSides = solution.inner_sides;
  const S = solution.S || solution.final_metric || 1.0;

  // Colors palette for shapes
  const colors = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#10b981',
    '#06b6d4', '#3b82f6', '#f59e0b', '#84cc16', '#a855f7'
  ];

  // Extract shapes
  const shapes: Array<{ cx: number; cy: number; angle: number; color: string }> = [];
  const stride = Math.floor(values.length / N);
  
  for (let i = 0; i < N; i++) {
    const idx = i * stride;
    const cx = values[idx] || 0;
    const cy = values[idx + 1] || 0;
    const angle = stride >= 3 ? (values[idx + 2] || 0) : 0;
    shapes.push({
      cx,
      cy,
      angle,
      color: colors[i % colors.length]
    });
  }

  // Determine bounding box
  let minX = -S, maxX = S, minY = -S, maxY = S;
  shapes.forEach(s => {
    minX = Math.min(minX, s.cx - 1.5);
    maxX = Math.max(maxX, s.cx + 1.5);
    minY = Math.min(minY, s.cy - 1.5);
    maxY = Math.max(maxY, s.cy + 1.5);
  });

  const padding = 0.5;
  const viewBox = `${minX - padding} ${minY - padding} ${(maxX - minX) + 2 * padding} ${(maxY - minY) + 2 * padding}`;

  return {
    viewBox,
    containerSides,
    innerSides,
    shapes,
    S
  };
}
