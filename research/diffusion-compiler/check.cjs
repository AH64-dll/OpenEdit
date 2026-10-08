// Isolated feasibility check; no upstream code is vendored or executed as a project.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const esbuild = require('esbuild');
const babel = require('@babel/core');
const presetSolid = require('babel-preset-solid');
const presetTypescript = require('@babel/preset-typescript');

(async () => {
  assert.ok(process.argv[2], 'Usage: node check.cjs /path/to/diffusionstudio-editor');
  const upstream = path.resolve(process.argv[2]);
  const commit = 'fefcde9df7198466bd7cc9f3a9d7eae1575b5b12';
  assert.equal(execFileSync('git', ['-C', upstream, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), commit, 'Use the reviewed upstream commit');
  const work = await fs.mkdtemp(path.join(__dirname, '.check-'));
  try {
    const alias = { '@diffusionstudio/jsx': path.join(upstream, 'packages/jsx/src/index.ts') };
    for (const name of ['edit', 'source']) {
      await esbuild.build({
        entryPoints: [path.join(upstream, `apps/desktop/src/${name}.ts`)],
        outfile: path.join(work, `${name}.cjs`), bundle: true, platform: 'node',
        format: 'cjs', alias, packages: 'external', nodePaths: [path.join(__dirname, 'node_modules')],
      });
    }
    const { applyEdits, stampProject } = require(path.join(work, 'edit.cjs'));
    const { sourcePlugin, canonicalizeTagsPlugin, inspectPlugin } = require(path.join(work, 'source.cjs'));
    const dir = path.join(work, 'fixture');
    await fs.mkdir(dir, { recursive: true });
    const entry = path.join(dir, 'index.tsx');
    await fs.writeFile(entry, `export default function Project() {
      return <stage id="stage"><scene id="scene" width={1920} height={1080} active>
        <video id="clip1" src="media/clip.mp4" start={0} sourceIn={1} sourceOut={6} />
        <text id="title1" start={0} end={2}>Hello</text>
      </scene></stage>;
    }\n`);
    await stampProject({ dir });
    const before = await fs.readFile(entry, 'utf8');
    const result = await applyEdits({ dir }, [
      { kind: 'set', source: 'index.tsx:clip1', props: { start: 3, sourceIn: 2, sourceOut: 7 } },
      { kind: 'set', source: 'index.tsx:title1', props: {}, text: 'Updated title' },
    ]);
    assert.equal(result.error, undefined);
    assert.deepEqual(result.skipped, []);
    const after = await fs.readFile(entry, 'utf8');
    assert.notEqual(after, before);
    assert.match(after, /id="clip1"/);
    assert.match(after, /start=\{3\}/);
    assert.match(after, /sourceIn=\{2\}/);
    assert.match(after, /sourceOut=\{7\}/);
    assert.match(after, /Updated title/);
    const transformed = await babel.transformAsync(after, {
      filename: entry, babelrc: false, configFile: false,
      plugins: [[sourcePlugin, { file: 'index.tsx' }], canonicalizeTagsPlugin, [inspectPlugin, { file: 'index.tsx' }]],
      presets: [[presetSolid, { generate: 'universal', moduleName: '@diffusionstudio/jsx' }], [presetTypescript, { onlyRemoveTypeImports: true }]],
    });
    assert.match(transformed.code, /index\.tsx:clip1/);
    const compiled = await esbuild.transform(transformed.code, { format: 'cjs', target: 'chrome130' });
    assert.match(compiled.code, /module\.exports/);
    assert.doesNotMatch(compiled.code, /<video/);
    console.log(JSON.stringify({
      upstream_commit: commit,
      edit_result: result, source_mapping_preserved: true, jsx_compilation: true,
      source_writeback: true, rendered_media: false,
    }, null, 2));
  } finally {
    await fs.rm(work, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
