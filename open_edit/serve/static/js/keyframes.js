/* Literal source edit descriptions; no runtime entity IDs or baked frames. */
const uid = prefix => `${prefix}-${crypto.randomUUID()}`;
export const animatedProperties = ['x', 'y', 'width', 'height', 'rotation', 'scale', 'opacity', 'color'];
export function keyframeEdits(document, ownerId, property, time, value, easing = 'linear', baseValue) {
  if (!animatedProperties.includes(property) || !Number.isFinite(time) || time < 0 || time > 60) throw new Error('Choose an animatable property and a local time between 0 and 60 seconds.');
  if (property === 'color' ? typeof value !== 'string' : !Number.isFinite(value)) throw new Error('Keyframe value is invalid.');
  time = Math.min(60, Math.round(time * document.fps) / document.fps);
  const elements = document.elements || [],
    owner = elements.find(e => e.id === ownerId);
  if (!owner || !['rect', 'text', 'image', 'group'].includes(owner.tag)) throw new Error('Select an editable layer to animate.');
  const track = elements.find(e => e.parent_id === ownerId && e.tag === 'keyframeTrack' && e.property === property);
  const frame = track && elements.find(e => e.parent_id === track.id && e.tag === 'keyframe' && Math.abs(e.time - time) < .5 / document.fps);
  if (frame) return [{
    kind: 'set',
    source: `index.tsx:${frame.id}`,
    props: {
      time,
      value,
      easing
    }
  }];
  const literal = value => typeof value === 'string' ? `{${JSON.stringify(value)}}` : `{${value}}`;
  const frameJsx = (t, v) => `<keyframe id="${uid('key')}" time={${t}} value=${literal(v)} easing={${JSON.stringify(easing)}}/>`;
  const keyframe = frameJsx(time, value),
    initial = !track && time > 0 && baseValue !== undefined ? frameJsx(0, baseValue) : '';
  return [{
    kind: 'insert',
    parent: `index.tsx:${track?.id || ownerId}`,
    jsx: track ? keyframe : `<keyframeTrack id="${uid('motion')}" property="${property}">${initial}${keyframe}</keyframeTrack>`
  }];
}
