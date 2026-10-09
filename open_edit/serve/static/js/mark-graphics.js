/* Explicit conversion creates editable JSX; annotation data never renders itself. */
export function markGraphic(mark, points, width, height, duration, fps, id) {
  if (!points.length || points.some(p => p.length !== 2 || p.some(n => !Number.isFinite(n)))) throw new Error('This mark has no visible geometry at the playhead.');
  if (!Number.isFinite(duration) || duration <= 0 || duration > 60) throw new Error('Choose a graphic duration between one frame and 60 seconds.');
  const scale = Math.min(1, 1920 / Math.max(width, height));
  width = Math.max(16, Math.round(width * scale));
  height = Math.max(16, Math.round(height * scale));
  points = points.map(p => p.map(n => n * scale));
  const n = v => Math.round(v * 1000) / 1000,
    color = mark.color,
    stroke = Math.max(2, width / 320);
  const parts = [],
    rect = (x, y, w, h, rotation = 0) => parts.push(`<rect id="${id}-part-${parts.length}" x={${n(x)}} y={${n(y)}} width={${n(Math.max(.1, w))}} height={${n(Math.max(.1, h))}} rotation={${n(rotation)}} fill="${color}" />`);
  const line = (a, b) => {
    const dx = b[0] - a[0],
      dy = b[1] - a[1],
      angle = Math.atan2(dy, dx);
    rect(a[0] + Math.sin(angle) * stroke / 2, a[1] - Math.cos(angle) * stroke / 2, Math.hypot(dx, dy), stroke, angle * 180 / Math.PI);
  };
  const [a, b = a] = points;
  if (mark.tool === 'rectangle') {
    const x = Math.min(a[0], b[0]),
      y = Math.min(a[1], b[1]),
      w = Math.abs(b[0] - a[0]),
      h = Math.abs(b[1] - a[1]);
    rect(x, y, w, stroke);
    rect(x, y + h - stroke, w, stroke);
    rect(x, y, stroke, h);
    rect(x + w - stroke, y, stroke, h);
  } else if (mark.tool === 'arrow') {
    line(a, b);
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]),
      size = stroke * 7;
    for (const d of [-.5, .5]) line(b, [b[0] - size * Math.cos(angle + d), b[1] - size * Math.sin(angle + d)]);
  } else if (mark.tool === 'freehand') {
    if (points.length > 400) throw new Error('Simplify the freehand mark to 400 points before converting.');
    for (let i = 1; i < points.length; i++) line(points[i - 1], points[i]);
  } else rect(a[0] - stroke * 2, a[1] - stroke * 2, stroke * 4, stroke * 4);
  if (mark.text) parts.push(`<text id="${id}-text" x={${n(a[0] + stroke * 5)}} y={${n(Math.max(0, a[1] - stroke * 12))}} width={${n(Math.max(16, width - a[0] - stroke * 5))}} height={${n(Math.min(height, stroke * 40))}} fontFamily="OpenEdit Sans" fontSize={${n(stroke * 9)}} color="${color}">{${JSON.stringify(mark.text)}}</text>`);
  return {
    source: `export default function MarkGraphic(){return <stage id="${id}-stage"><scene id="${id}-scene" width={${width}} height={${height}} active><group id="${id}">${parts.join('\n')}</group></scene></stage>;}`,
    duration_sec: duration,
    fps,
    clip_id: `${id}-clip`,
    track_id: `${id}-track`,
    position_sec: mark.anchor_sec,
    label: `${mark.tool} graphic`
  };
}
