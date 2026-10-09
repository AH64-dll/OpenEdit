// MIT host bundle. Vendored MPL sources stay unchanged and retain their notices.
const path = require('node:path');
const esbuild = require('esbuild');
const alias = {};
for (const name of ['runtime', 'reconciler', 'encoder', 'assets', 'jsx']) {
  alias[`@diffusionstudio/${name}`] = path.join(__dirname, 'vendor', name, 'src/index.ts');
}
esbuild.build({ entryPoints: [path.join(__dirname, 'editor-runtime.ts')], bundle: true,
  platform: 'browser', format: 'iife', target: 'chrome130', alias, conditions: ['browser'],
  write: false, banner: { js: '"use strict";' }, legalComments: 'inline', logLevel: 'silent',
}).then(result => process.stdout.write(result.outputFiles[0].text))
  .catch(error => { process.stderr.write(String(error.message)); process.exitCode = 1; });
