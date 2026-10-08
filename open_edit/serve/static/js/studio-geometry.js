/* Composition-space geometry, independent of the DOM and renderer. */
export const identity = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
export const transformPoint = (m, [x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
export function inverse(m = identity) {
  const det = m.a * m.d - m.b * m.c;
  if (Math.abs(det) < 1e-10) return null;
  return { a: m.d / det, b: -m.b / det, c: -m.c / det, d: m.a / det,
    e: (m.c * m.f - m.d * m.e) / det, f: (m.b * m.e - m.a * m.f) / det };
}
export function localDelta(matrix, dx, dy) {
  const m = inverse(matrix); return m ? [m.a * dx + m.c * dy, m.b * dx + m.d * dy] : [0, 0];
}
export function insidePolygon([x, y], points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i], [xj, yj] = points[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
export function bounds(points) {
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  return { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
}
export function selectionRoots(ids, elements) {
  const selected = new Set(ids), map = new Map(elements.map(e => [e.id, e]));
  return ids.filter(id => {
    let parent = map.get(id)?.parent_id;
    while (parent) { if (selected.has(parent)) return false; parent = map.get(parent)?.parent_id; }
    return true;
  });
}
export function layerLocked(id, elements, locks, documentLocked = false) {
  if (documentLocked) return true;
  const map = new Map(elements.map(e => [e.id, e]));
  for (let item = id; item; item = map.get(item)?.parent_id) if (locks.includes(item)) return true;
  return false;
}
export function annotationPoints(mark, geometries) {
  if (mark.coordinate_space !== 'object') return mark.points;
  const anchor = geometries.find(g => g.id === mark.anchor_id);
  return anchor ? mark.points.map(p => transformPoint(anchor.matrix, p)) : [];
}
export function alignmentOffsets(items, mode, width, height) {
  const boxes = items.map(item => ({ item, ...bounds(item.corners) }));
  if (!boxes.length) return {};
  const horizontal = ['left', 'center', 'right', 'distribute-x'].includes(mode);
  const low = horizontal ? 'left' : 'top', high = horizontal ? 'right' : 'bottom';
  const min = boxes.length === 1 ? 0 : Math.min(...boxes.map(b => b[low]));
  const max = boxes.length === 1 ? (horizontal ? width : height) : Math.max(...boxes.map(b => b[high]));
  const offsets = {};
  if (mode.startsWith('distribute')) {
    if (boxes.length < 3) return offsets;
    boxes.sort((a, b) => a[low] - b[low]);
    const space = (max - min - boxes.reduce((sum, b) => sum + b[high] - b[low], 0)) / (boxes.length - 1);
    let cursor = min;
    for (const box of boxes) { offsets[box.item.id] = horizontal ? [cursor - box[low], 0] : [0, cursor - box[low]]; cursor += box[high] - box[low] + space; }
  } else for (const box of boxes) {
    const delta = ['left', 'top'].includes(mode) ? min - box[low] : ['right', 'bottom'].includes(mode) ? max - box[high] : (min + max - box[low] - box[high]) / 2;
    offsets[box.item.id] = horizontal ? [delta, 0] : [0, delta];
  }
  return offsets;
}
