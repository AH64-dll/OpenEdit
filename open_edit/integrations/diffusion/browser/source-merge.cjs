// MIT. Invert one request's semantic delta while retaining unrelated later edits.
const babel = require('@babel/core');
const { astOf, index, valueNode, open } = require('./source-edit.cjs');
const t = babel.types;
function literal(n) {
  if (!n) return true;
  if (n.type === 'JSXExpressionContainer') return literal(n.expression);
  if (n.type === 'UnaryExpression') return (n.operator === '-' ? -1 : 1) * literal(n.argument);
  if (n.type === 'ObjectExpression') return Object.fromEntries(n.properties.map(p => [p.key.name || p.key.value, literal(p.value)]));
  if (n.type === 'ArrayExpression') return n.elements.map(literal);
  return n.value;
}
const idOf = n => { if (!n) return null; const a = n.openingElement.attributes.find(a => a.name?.name === 'id'); return literal(a?.value); };
const children = n => n.children.filter(c => c.type === 'JSXElement').map(idOf);
const attrs = n => Object.fromEntries(n.openingElement.attributes.map(a => [a.name.name, literal(a.value)]));
const text = n => n.children.filter(c => c.type === 'JSXText' || (c.type === 'JSXExpressionContainer' && c.expression.type !== 'JSXEmptyExpression'))
  .map(c => c.type === 'JSXText' ? c.value.replace(/\s+/g, ' ').trim() : literal(c)).filter(Boolean).join('');
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]));
  return value;
}
const equal = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const summary = n => ({ tag: n.openingElement.name.name, attrs: attrs(n), text: text(n), children: n.children.filter(c => c.type === 'JSXElement').map(summary) });
function inverseSource(before, after, current, validate) {
  for (const source of [before, after, current]) validate(source);
  if (before === after) return { source: current, conflicts: [] };
  const ba = astOf(before), aa = astOf(after), ca = astOf(current);
  const bi = index(ba), ai = index(aa), ci = index(ca), conflicts = [];
  const conflict = (id, field, reason = 'Later work changed the same property') => conflicts.push({ object_id: id, field, reason });
  const invert = (id, field, b, a, c, write) => {
    if (equal(b, a) || equal(b, c)) return;
    if (equal(c, a)) write(b); else conflict(id, field);
  };
  const created = new Set([...ai.keys()].filter(id => !bi.has(id)));
  const removed = new Set([...bi.keys()].filter(id => !ai.has(id)));
  for (const id of removed) {
    const b = bi.get(id), c = ci.get(id);
    if (b.parent && removed.has(idOf(b.parent))) continue;
    if (c) { if (!equal(summary(b.node), summary(c.node))) conflict(id, 'existence'); continue; }
    const parent = index(ca).get(idOf(b.parent))?.node;
    if (!parent) { conflict(id, 'parent', 'The original parent was removed by later work'); continue; }
    const restored = t.cloneNode(b.node, true);
    const prune = node => { node.children = node.children.filter(n => n.type !== 'JSXElement' || !ai.has(idOf(n))); for (const child of node.children.filter(n => n.type === 'JSXElement')) prune(child); };
    prune(restored);
    const keys = []; const collect = node => { keys.push(idOf(node)); for (const child of node.children.filter(n => n.type === 'JSXElement')) collect(child); }; collect(restored);
    if (keys.some(key => index(ca).has(key))) { conflict(id, 'existence', 'A stable ID is now used by another object'); continue; }
    const siblings = children(b.parent), next = siblings.slice(siblings.indexOf(id) + 1).map(key => index(ca).get(key)).find(e => e?.parent === parent);
    parent.children.splice(next ? parent.children.indexOf(next.node) : parent.children.length, 0, restored); open(parent);
  }
  for (const [id, b] of bi) {
    const a = ai.get(id); if (!a) continue;
    const c = index(ca).get(id);
    if (!c) { if (!equal(summary(b.node), summary(a.node))) conflict(id, 'existence', 'An edited object was removed by later work'); continue; }
    invert(id, 'type', b.node.openingElement.name.name, a.node.openingElement.name.name, c.node.openingElement.name.name, () => conflict(id, 'type', 'Changing an element type requires a manual resolution'));
    const bp = attrs(b.node), ap = attrs(a.node), cp = attrs(c.node);
    for (const key of new Set([...Object.keys(bp), ...Object.keys(ap)])) {
      if (key === 'id') continue;
      invert(id, key, bp[key], ap[key], cp[key], value => {
        const list = c.node.openingElement.attributes, i = list.findIndex(attr => attr.name?.name === key);
        if (value === undefined) { if (i >= 0) list.splice(i, 1); }
        else { const attr = t.jsxAttribute(t.jsxIdentifier(key), valueNode(value)); if (i >= 0) list[i] = attr; else list.push(attr); }
      });
    }
    invert(id, 'text', text(b.node), text(a.node), text(c.node), value => {
      c.node.children = c.node.children.filter(n => n.type === 'JSXElement' || (n.type === 'JSXExpressionContainer' && n.expression.type === 'JSXEmptyExpression'));
      if (value) c.node.children.unshift(t.jsxExpressionContainer(t.stringLiteral(value))); open(c.node);
    });
    const parentId = e => e.parent ? idOf(e.parent) : null;
    invert(id, 'parent', parentId(b), parentId(a), parentId(c), value => {
      const parent = index(ca).get(value)?.node;
      if (!parent || !c.parent) return conflict(id, 'parent', 'The original parent no longer exists');
      c.parent.children.splice(c.parent.children.indexOf(c.node), 1); parent.children.push(c.node); open(parent);
    });
    // Reorder only the surviving siblings affected by the request. New siblings
    // retain their slots and properties; conflicting later reorder is explicit.
    const common = new Set(children(b.node).filter(key => children(a.node).includes(key)));
    const bc = children(b.node).filter(key => common.has(key)), ac = children(a.node).filter(key => common.has(key));
    const currentChildren = children(c.node).filter(key => common.has(key));
    invert(id, 'order', bc, ac, currentChildren, () => {
      const nodes = new Map(c.node.children.filter(n => n.type === 'JSXElement').map(n => [idOf(n), n])); let i = 0;
      c.node.children = c.node.children.map(n => n.type === 'JSXElement' && common.has(idOf(n)) ? nodes.get(bc[i++]) : n);
    });
  }
  for (const id of created) {
    const a = ai.get(id), c = index(ca).get(id);
    if (a.parent && created.has(idOf(a.parent))) continue;
    if (!c) continue;
    const expected = t.cloneNode(a.node, true);
    const prune = node => { node.children = node.children.filter(n => n.type !== 'JSXElement' || !bi.has(idOf(n))); for (const child of node.children.filter(n => n.type === 'JSXElement')) prune(child); }; prune(expected);
    if (!c.parent || !equal(summary(expected), summary(c.node)) || idOf(a.parent) !== idOf(c.parent)) { conflict(id, 'existence', 'Later work depends on an object created by this request'); continue; }
    c.parent.children.splice(c.parent.children.indexOf(c.node), 1);
  }
  if (conflicts.length) return { source: current, conflicts };
  const source = babel.transformFromAstSync(ca, current, { configFile: false, babelrc: false, generatorOpts: { comments: true } }).code;
  validate(source); return { source, conflicts: [] };
}
module.exports = { inverseSource };
