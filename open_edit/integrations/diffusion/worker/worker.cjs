// MIT: OpenEdit's adapter. vendor/ contains separately licensed MPL-2.0 source.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const esbuild = require('esbuild');
const babel = require('@babel/core');
const presetSolid = require('babel-preset-solid');
const presetTypescript = require('@babel/preset-typescript');
const MAX_SOURCE = 512 * 1024;

function upstream(name) {
  const result = esbuild.buildSync({
    entryPoints: [path.join(__dirname, 'vendor/desktop', `${name}.ts`)],
    bundle: true, platform: 'node', format: 'cjs', packages: 'external', write: false,
    alias: { '@diffusionstudio/jsx': path.join(__dirname, 'vendor/jsx/index.ts') },
    legalComments: 'inline', logLevel: 'silent',
  });
  const compiledModule = { exports: {} };
  // Only the pinned vendored module is evaluated. Project JSX is parsed and
  // transformed below; it is never evaluated and cannot load project plugins.
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, compiledModule, compiledModule.exports);
  return compiledModule.exports;
}

function literal(value) {
  if (!value) return true;
  if (value.type === 'StringLiteral' || value.type === 'NumericLiteral' || value.type === 'BooleanLiteral') return value.value;
  if (value.type === 'JSXExpressionContainer') return literal(value.expression);
  if (value.type === 'UnaryExpression' && ['-', '+'].includes(value.operator) && value.argument.type === 'NumericLiteral') {
    return (value.operator === '-' ? -1 : 1) * value.argument.value;
  }
  throw new Error('Only literal JSX properties are supported; expressions and spreads are not supported');
}

function element(node, tag, allowed) {
  if (node?.type !== 'JSXElement' || node.openingElement.name.type !== 'JSXIdentifier' || node.openingElement.name.name !== tag) {
    throw new Error(`Expected a <${tag}> element`);
  }
  const props = {};
  for (const attr of node.openingElement.attributes) {
    if (attr.type !== 'JSXAttribute' || attr.name.type !== 'JSXIdentifier' || !allowed.includes(attr.name.name)) {
      throw new Error(`Unsupported property on <${tag}>`);
    }
    if (Object.hasOwn(props, attr.name.name)) throw new Error(`Duplicate property ${attr.name.name}`);
    props[attr.name.name] = literal(attr.value);
  }
  if (typeof props.id !== 'string' || !props.id) throw new Error(`Every <${tag}> needs a stable string id`);
  const children = node.children.filter(n => n.type !== 'JSXText' || n.value.trim());
  return { props, children };
}

function parse(source) {
  const ast = babel.parseSync(source, { filename: 'index.tsx', configFile: false, babelrc: false, parserOpts: { plugins: ['jsx', 'typescript'] } });
  const decl = ast.program.body[0];
  if (ast.program.body.length !== 1 || decl.type !== 'ExportDefaultDeclaration' || decl.declaration.type !== 'FunctionDeclaration') {
    throw new Error('Use the exported default function from the authoring view; other statements/imports are unsupported');
  }
  const fn = decl.declaration;
  if (fn.async || fn.generator || fn.params.length || fn.body.body.length !== 1 || fn.body.body[0].type !== 'ReturnStatement') {
    throw new Error('The authoring function must return one literal JSX stage');
  }
  const stage = element(fn.body.body[0].argument, 'stage', ['id']);
  if (stage.children.length !== 1) throw new Error('Exactly one scene is supported');
  const scene = element(stage.children[0], 'scene', ['id', 'width', 'height', 'active']);
  const ids = new Set([stage.props.id]);
  const unique = id => { if (ids.has(id)) throw new Error(`Duplicate element id: ${id}`); ids.add(id); };
  unique(scene.props.id);
  const tracks = scene.children.map(node => {
    const group = element(node, 'group', ['id']); unique(group.props.id);
    const clips = group.children.map(child => {
      const tag = child?.openingElement?.name?.name;
      if (!['video', 'audio', 'image'].includes(tag)) throw new Error('Only video, audio and image clips are supported in the media authoring view');
      const {props, children} = element(child, tag, ['id', 'src', 'start', 'sourceIn', 'sourceOut', 'playbackRate', 'volume']);
      if (children.length) throw new Error('Media elements cannot contain graphics or effects in this authoring view');
      unique(props.id);
      return { tag, ...props };
    });
    return { id: group.props.id, clips };
  });
  return { stage: stage.props, scene: scene.props, tracks };
}

function validateEdits(edits) {
  if (!Array.isArray(edits) || edits.length > 1000) throw new Error('edits must be a list of at most 1000 source edits');
  const clipSource = s => typeof s === 'string' && /^index\.tsx:c-[^:]+$/.test(s);
  const trackSource = s => typeof s === 'string' && /^index\.tsx:t-[^:]+$/.test(s);
  for (const edit of edits) {
    if (!edit || !clipSource(edit.source)) throw new Error('Source edits must address clip IDs in index.tsx');
    const keys = edit.kind === 'set' ? ['kind', 'source', 'props'] : edit.kind === 'move' ? ['kind', 'source', 'parent', 'before'] : ['kind', 'source'];
    if (!['set', 'remove', 'move'].includes(edit.kind) || Object.keys(edit).some(k => !keys.includes(k))) throw new Error('Supported source edits are set, remove and move');
    if (edit.kind === 'set') {
      if (!edit.props || Array.isArray(edit.props) || typeof edit.props !== 'object') throw new Error('set requires a props object');
      for (const [key, value] of Object.entries(edit.props)) {
        if (!['start', 'sourceIn', 'sourceOut', 'playbackRate', 'volume', 'src'].includes(key) || (typeof value !== 'number' && typeof value !== 'string')) throw new Error(`Unsupported source property: ${key}`);
      }
    }
    if (edit.kind === 'move' && (!trackSource(edit.parent) || (edit.before !== undefined && !clipSource(edit.before)))) throw new Error('move requires an existing track parent and optional clip anchor');
  }
}

(async () => {
  let input = '';
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 2 * MAX_SOURCE) throw new Error('Worker request too large');
  }
  const request = JSON.parse(input);
  if (typeof request.source !== 'string' || Buffer.byteLength(request.source) > MAX_SOURCE) throw new Error('JSX source exceeds 512 KiB');
  parse(request.source);
  let source = request.source;
  if (request.edits !== undefined) {
    validateEdits(request.edits);
    // Work only on a temporary canonical view. The Python host commits IR
    // after the whole rewritten source has parsed and compiled successfully.
    const entry = path.join(process.cwd(), 'index.tsx');
    await fs.writeFile(entry, source, 'utf8');
    const { applyEdits } = upstream('edit');
    const result = await applyEdits({ dir: process.cwd() }, request.edits);
    if (result.error || result.skipped.length) throw new Error(result.error || `Source edits could not be applied: ${result.skipped.join(', ')}`);
    source = await fs.readFile(entry, 'utf8');
  }
  const document = parse(source);
  const { sourcePlugin, canonicalizeTagsPlugin, inspectPlugin } = upstream('source');
  const transformed = await babel.transformAsync(source, {
    filename: 'index.tsx', configFile: false, babelrc: false,
    plugins: [[sourcePlugin, { file: 'index.tsx' }], canonicalizeTagsPlugin, [inspectPlugin, { file: 'index.tsx' }]],
    presets: [[presetSolid, { generate: 'universal', moduleName: '@diffusionstudio/jsx' }], [presetTypescript, { onlyRemoveTypeImports: true }]],
  });
  const compiled = await esbuild.transform(transformed.code, { format: 'cjs', target: 'chrome130' });
  process.stdout.write(JSON.stringify({ ok: true, protocol: 1, document, compiled_hash: crypto.createHash('sha256').update(compiled.code).digest('hex') }));
})().catch(error => { process.stdout.write(JSON.stringify({ ok: false, error: String(error.message).split('\n')[0].slice(0, 300) })); process.exitCode = 1; });
