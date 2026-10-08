// MIT. Structural source edits over the validated literal JSX document.
const babel = require('@babel/core');
const { randomUUID } = require('node:crypto');
const t = babel.types;

function astOf(source) {
  return babel.parseSync(source, { filename: 'index.tsx', configFile: false, babelrc: false,
    parserOpts: { plugins: ['jsx'] } });
}
function index(ast) {
  const nodes = new Map();
  function visit(node, parent) {
    if (node?.type !== 'JSXElement') return;
    const attr = node.openingElement.attributes.find(a => a.name?.name === 'id');
    const id = attr?.value?.value || attr?.value?.expression?.value;
    if (id) nodes.set(id, { node, parent });
    for (const child of node.children) visit(child, node);
  }
  visit(ast.program.body[0].declaration.body.body[0].argument, null);
  return nodes;
}
function identity(value) {
  if (typeof value !== 'string' || !/^index\.tsx:[a-zA-Z][\w-]{0,127}$/.test(value)) throw new Error('Use an existing stable source ID');
  return value.slice(10);
}
function get(nodes, value) {
  const entry = nodes.get(identity(value));
  if (!entry) throw new Error(`Source object not found: ${value}`);
  return entry;
}
function open(node) {
  if (node.openingElement.selfClosing) {
    node.openingElement.selfClosing = false;
    node.closingElement = t.jsxClosingElement(t.cloneNode(node.openingElement.name));
  }
}
function valueNode(value) {
  if (typeof value === 'string') return t.stringLiteral(value);
  if (typeof value === 'boolean') return t.jsxExpressionContainer(t.booleanLiteral(value));
  if (typeof value === 'number' && Number.isFinite(value)) return t.jsxExpressionContainer(t.valueToNode(value));
  if (value && typeof value === 'object' && !Array.isArray(value)) return t.jsxExpressionContainer(t.valueToNode(value));
  throw new Error('Property values must be finite literals; null removes a property');
}
function put(parent, child, before, nodes) {
  if (before) {
    const anchor = get(nodes, before);
    if (anchor.parent !== parent) throw new Error('The insertion anchor must belong to the destination parent');
    parent.children.splice(parent.children.indexOf(anchor.node), 0, child);
  } else parent.children.push(child);
  open(parent);
}
function editSource(source, edits, validate) {
  validate(source);
  if (!Array.isArray(edits) || edits.length > 1000) throw new Error('Graphics edits must be a bounded list');
  if (!edits.length) return source;
  const ast = astOf(source);
  for (const edit of edits) {
    if (!edit || typeof edit !== 'object' || Array.isArray(edit)) throw new Error('Invalid graphics edit');
    const allowed = {
      set: ['kind', 'source', 'props'], text: ['kind', 'source', 'text'],
      remove: ['kind', 'source'], insert: ['kind', 'parent', 'jsx', 'before'],
      move: ['kind', 'source', 'parent', 'before'], duplicate: ['kind', 'source', 'parent', 'before', 'id_map'],
      group: ['kind', 'sources', 'id'],
      translate: ['kind', 'source', 'dx', 'dy'],
    }[edit.kind];
    if (!allowed || Object.keys(edit).some(k => !allowed.includes(k))) throw new Error('Unsupported graphics source edit');
    const nodes = index(ast);
    if (edit.kind === 'insert') {
      if (typeof edit.jsx !== 'string' || Buffer.byteLength(edit.jsx) > 512 * 1024) throw new Error('Insert requires bounded literal JSX');
      const snippet = babel.parseSync(`const item = (${edit.jsx});`, { configFile: false, babelrc: false,
        parserOpts: { plugins: ['jsx'] } });
      const child = snippet.program.body[0]?.declarations?.[0]?.init;
      if (snippet.program.body.length !== 1 || child?.type !== 'JSXElement') throw new Error('Insert one literal JSX element');
      put(get(nodes, edit.parent).node, child, edit.before, nodes);
    } else if (edit.kind === 'group') {
      if (!Array.isArray(edit.sources) || !edit.sources.length || new Set(edit.sources).size !== edit.sources.length ||
          typeof edit.id !== 'string' || !/^[a-zA-Z][\w-]{0,127}$/.test(edit.id) || nodes.has(edit.id)) throw new Error('Group needs unique sources and a new stable ID');
      const entries = edit.sources.map(s => get(nodes, s)), parent = entries[0].parent;
      if (!parent || entries.some(e => e.parent !== parent)) throw new Error('Group siblings under one parent');
      const selected = new Set(entries.map(e => e.node));
      const children = parent.children.filter(n => selected.has(n));
      const first = parent.children.indexOf(children[0]);
      const wrapper = t.jsxElement(t.jsxOpeningElement(t.jsxIdentifier('group'),
        [t.jsxAttribute(t.jsxIdentifier('id'), t.stringLiteral(edit.id))], false),
        t.jsxClosingElement(t.jsxIdentifier('group')), children);
      parent.children = parent.children.filter(n => !selected.has(n));
      parent.children.splice(first, 0, wrapper);
    } else {
      const { node, parent } = get(nodes, edit.source);
      if (edit.kind === 'translate') {
        // Reposition the entire authored motion path; an ordinary drag never
        // inserts a keyframe or replaces a track with a static value.
        for (const [property, delta] of [['x', edit.dx || 0], ['y', edit.dy || 0]]) {
          if (typeof delta !== 'number' || !Number.isFinite(delta)) throw new Error('Translation needs finite numbers');
          if (!delta) continue;
          const attributes = node.openingElement.attributes;
          const attr = attributes.find(a => a.name?.name === property);
          const read = value => value?.type === 'JSXExpressionContainer' ? read(value.expression) :
            value?.type === 'UnaryExpression' ? (value.operator === '-' ? -1 : 1) * read(value.argument) : value?.value;
          const base = attr ? read(attr.value) : 0;
          if (typeof base !== 'number') throw new Error('Position must be a numeric literal');
          if (attr) attr.value = valueNode(base + delta);
          else attributes.push(t.jsxAttribute(t.jsxIdentifier(property), valueNode(base + delta)));
          for (const track of node.children.filter(n => n.type === 'JSXElement' && n.openingElement.name.name === 'keyframeTrack')) {
            const prop = track.openingElement.attributes.find(a => a.name?.name === 'property');
            if (read(prop?.value) !== property) continue;
            for (const frame of track.children.filter(n => n.type === 'JSXElement')) {
              const value = frame.openingElement.attributes.find(a => a.name?.name === 'value');
              const before = read(value?.value);
              if (typeof before !== 'number') throw new Error('Position keyframes must be numeric');
              value.value = valueNode(before + delta);
            }
          }
        }
      } else if (edit.kind === 'set') {
        if (!edit.props || typeof edit.props !== 'object' || Array.isArray(edit.props)) throw new Error('Set requires literal properties');
        for (const [name, value] of Object.entries(edit.props)) {
          if (name === 'id' || !/^[A-Za-z][A-Za-z0-9]*$/.test(name)) throw new Error('Stable IDs cannot be changed');
          const attributes = node.openingElement.attributes;
          const existing = attributes.findIndex(a => a.name?.name === name);
          if (value === null) { if (existing >= 0) attributes.splice(existing, 1); }
          else {
            const attr = t.jsxAttribute(t.jsxIdentifier(name), valueNode(value));
            if (existing >= 0) attributes[existing] = attr; else attributes.push(attr);
          }
        }
      } else if (edit.kind === 'text') {
        if (node.openingElement.name.name !== 'text' || typeof edit.text !== 'string' || edit.text.length > 10000) throw new Error('Text edits require a text element and bounded string');
        node.children = node.children.filter(n => n.type === 'JSXElement' ||
          (n.type === 'JSXExpressionContainer' && n.expression.type === 'JSXEmptyExpression'));
        node.children.unshift(t.jsxExpressionContainer(t.stringLiteral(edit.text))); open(node);
      } else if (edit.kind === 'remove') {
        if (!parent || node.openingElement.name.name === 'scene') throw new Error('Cannot delete the stage or scene');
        parent.children.splice(parent.children.indexOf(node), 1);
      } else if (edit.kind === 'move' || edit.kind === 'duplicate') {
        if (!parent || node.openingElement.name.name === 'scene') throw new Error('Cannot move or duplicate the stage or scene');
        const destination = edit.parent ? get(nodes, edit.parent).node : parent;
        if (edit.kind === 'move') {
          let entry = nodes.get(identity(edit.parent));
          while (entry) {
            if (entry.node === node) throw new Error('Cannot move an object into its own descendants');
            entry = [...nodes.values()].find(e => e.node === entry.parent);
          }
          if (edit.before === edit.source) continue;
          parent.children.splice(parent.children.indexOf(node), 1);
          put(destination, node, edit.before, nodes);
        } else {
          const copy = t.cloneNode(node, true);
          const map = edit.id_map || {};
          if (typeof map !== 'object' || Array.isArray(map)) throw new Error('id_map must be an object');
          function rename(n) {
            if (n.type !== 'JSXElement') return;
            const attr = n.openingElement.attributes.find(a => a.name?.name === 'id');
            const old = attr.value.value || attr.value.expression?.value;
            attr.value = t.stringLiteral(map[old] || `copy-${randomUUID()}`);
            for (const child of n.children) rename(child);
          }
          rename(copy); put(destination, copy, edit.before, nodes);
        }
      }
    }
  }
  const result = babel.transformFromAstSync(ast, source, { configFile: false, babelrc: false,
    generatorOpts: { comments: true } }).code;
  validate(result);
  return result;
}
module.exports = { editSource, astOf, index, valueNode, open };
