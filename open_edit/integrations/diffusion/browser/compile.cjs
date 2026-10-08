// MIT. Strict, non-executable graphics vocabulary; upstream MPL files stay unchanged.
const babel = require('@babel/core');
const esbuild = require('esbuild');
const path = require('node:path');
const solid = require('babel-preset-solid');
const common = ['id', 'x', 'y', 'width', 'height', 'rotation', 'scale', 'scaleX', 'scaleY',
  'opacity', 'cornerRadius', 'start', 'end', 'sourceIn', 'sourceOut', 'playbackRate', 'hidden', 'fill'];
const props = {
  stage: ['id'], scene: ['id', 'width', 'height', 'active', 'fill'],
  group: common, rect: [...common, 'clipPath'],
  text: [...common, 'color', 'fontFamily', 'fontSize', 'fontWeight', 'textAlign', 'textBaseline'],
  image: [...common, 'src', 'fit'], sequence: ['id'],
  animation: ['id', 'type', 'phase', 'duration', 'delay'],
  keyframeTrack: ['id', 'property'], keyframe: ['id', 'time', 'value', 'easing'],
  solidPaint: ['id', 'color', 'opacity'],
};
const children = {
  stage: ['scene'], scene: ['group', 'rect', 'text', 'image', 'sequence'],
  group: ['group', 'rect', 'text', 'image', 'sequence', 'animation', 'keyframeTrack'],
  rect: ['rect', 'solidPaint', 'animation', 'keyframeTrack'],
  text: ['rect', 'solidPaint', 'animation', 'keyframeTrack'],
  image: ['rect', 'animation', 'keyframeTrack'],
  sequence: ['group', 'rect', 'text', 'image'], keyframeTrack: ['keyframe'],
  solidPaint: ['keyframeTrack'], animation: [], keyframe: [],
};
function literal(node) {
  if (!node) return true;
  if (['StringLiteral', 'NumericLiteral', 'BooleanLiteral'].includes(node.type)) return node.value;
  if (node.type === 'JSXExpressionContainer') return literal(node.expression);
  if (node.type === 'UnaryExpression' && ['-', '+'].includes(node.operator) && node.argument.type === 'NumericLiteral') {
    return node.argument.value * (node.operator === '-' ? -1 : 1);
  }
  throw new Error('Graphics properties must be literal strings, finite numbers, or booleans');
}
function parse(source) {
  if (typeof source !== 'string' || Buffer.byteLength(source) > 512 * 1024) throw new Error('Graphics source exceeds 512 KiB');
  const ast = babel.parseSync(source, { filename: 'index.tsx', configFile: false, babelrc: false, parserOpts: { plugins: ['jsx'] } });
  const decl = ast.program.body[0];
  if (ast.program.body.length !== 1 || decl?.type !== 'ExportDefaultDeclaration' || decl.declaration.type !== 'FunctionDeclaration') throw new Error('Export one default function returning literal JSX');
  const fn = decl.declaration;
  if (fn.async || fn.generator || fn.params.length || fn.body.body.length !== 1 || fn.body.body[0].type !== 'ReturnStatement') throw new Error('Graphics functions may only return literal JSX');
  const ids = new Set(); const assets = new Set(); const elements = [];
  function visit(node, parent, depth = 0) {
    const tag = node?.openingElement?.name?.name;
    if (node?.type !== 'JSXElement' || node.openingElement.name.type !== 'JSXIdentifier' || !props[tag] || (parent && !children[parent].includes(tag))) throw new Error(`Unsupported graphics element or nesting: ${tag}`);
    if (depth > 20 || elements.length >= 500) throw new Error('Graphics supports at most 500 elements and 20 nesting levels');
    const values = {};
    for (const attr of node.openingElement.attributes) {
      const name = attr.name?.name;
      if (attr.type !== 'JSXAttribute' || !props[tag].includes(name) || Object.hasOwn(values, name)) throw new Error(`Unsupported or duplicate ${tag} property: ${name}`);
      const value = literal(attr.value);
      if (typeof value === 'number' && (!Number.isFinite(value) || Math.abs(value) > 1e6)) throw new Error('Graphics numeric property is out of bounds');
      if (typeof value === 'string' && value.length > 10000) throw new Error('Graphics string is too long');
      values[name] = value;
    }
    if (typeof values.id !== 'string' || !/^[a-zA-Z][\w-]{0,127}$/.test(values.id) || ids.has(values.id)) throw new Error('Every graphics element needs a unique stable id');
    ids.add(values.id);
    const stringProps = ['fill', 'color', 'fontFamily', 'textAlign', 'textBaseline', 'src', 'fit', 'type', 'phase', 'property', 'easing'];
    for (const [key, val] of Object.entries(values)) {
      if (key === 'id') continue;
      if (['active', 'hidden', 'clipPath'].includes(key)) { if (typeof val !== 'boolean') throw new Error(`${key} must be boolean`); }
      else if (stringProps.includes(key)) { if (typeof val !== 'string') throw new Error(`${key} must be a string`); }
      else if (key === 'value' && typeof val === 'string') { /* animated color */ }
      else if (typeof val !== 'number') throw new Error(`${key} must be a number in seconds or pixels`);
    }
    if (values.playbackRate !== undefined && (values.playbackRate < 0.125 || values.playbackRate > 8)) throw new Error('playbackRate must be between 0.125 and 8');
    for (const key of ['start', 'end', 'sourceIn', 'sourceOut', 'time', 'duration', 'delay']) if (values[key] !== undefined && (values[key] < 0 || values[key] > 60)) throw new Error('Graphics time must be between 0 and 60 seconds');
    if (tag === 'image') {
      if (!/^asset:\/\/[a-f0-9]{64}$/.test(values.src || '')) throw new Error('Images must reference project CAS asset:// URLs');
      assets.add(values.src.slice(8));
    }
    if (values.fontFamily && values.fontFamily !== 'OpenEdit Sans') throw new Error('Use the bundled OpenEdit Sans font for reproducible text');
    if (tag === 'animation' && !['fade', 'grow', 'shrink', 'slideLeft', 'slideRight', 'slideUp', 'slideDown', 'spin'].includes(values.type)) throw new Error('Unsupported animation preset');
    if (values.phase && !['in', 'out'].includes(values.phase)) throw new Error('Animation phase must be in or out');
    if (tag === 'keyframeTrack' && !['x', 'y', 'width', 'height', 'rotation', 'scale', 'opacity', 'color'].includes(values.property)) throw new Error('Unsupported keyframe property');
    if (values.easing && !['linear', 'easeIn', 'easeOut', 'easeInOut'].includes(values.easing)) throw new Error('Unsupported easing');
    const entry = { tag, ...values }; elements.push(entry);
    for (const child of node.children) {
      if (child.type === 'JSXText') {
        if (child.value.trim() && tag !== 'text') throw new Error('Only text elements can contain text');
      } else if (child.type === 'JSXExpressionContainer' && child.expression.type === 'JSXEmptyExpression') continue;
      else visit(child, tag, depth + 1);
    }
    return entry;
  }
  const root = visit(fn.body.body[0].argument);
  if (root.tag !== 'stage' || elements.filter(e => e.tag === 'scene').length !== 1) throw new Error('Graphics requires one stage with one scene');
  const scene = elements.find(e => e.tag === 'scene');
  for (const key of ['width', 'height']) if (!Number.isInteger(scene[key]) || scene[key] < 16 || scene[key] > 1920 || scene[key] % 2) throw new Error('Scene dimensions must be even integers from 16 to 1920');
  return { scene, elements, assets: [...assets].sort() };
}
async function compile(source) {
  const document = parse(source);
  const transformed = await babel.transformAsync(source, { filename: 'index.tsx', configFile: false, babelrc: false,
    presets: [[solid, { generate: 'universal', moduleName: '@diffusionstudio/jsx' }]] });
  const compiled = await esbuild.transform(transformed.code, { format: 'cjs', target: 'chrome130' });
  return { document, code: compiled.code };
}
module.exports = { parse, compile };
