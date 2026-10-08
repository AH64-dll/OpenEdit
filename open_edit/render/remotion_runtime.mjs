/* Optional pinned runtime. Existing project dependencies retain precedence. */
import {createRequire} from 'node:module';
import {dirname, resolve} from 'node:path';

export function remotionRuntime(projectRoot) {
  const compatibility = process.env.OPEN_EDIT_REMOTION_PACKAGE;
  const locations = [
    resolve(projectRoot, 'package.json'),
    import.meta.url, // older source installations with root node_modules
    compatibility ? resolve(compatibility, 'package.json') : new URL('../integrations/remotion/package.json', import.meta.url),
  ];
  for (const location of locations) {
    const require = createRequire(location);
    try {
      const bundler = require('@remotion/bundler');
      const renderer = require('@remotion/renderer');
      const modules = dirname(dirname(require.resolve('remotion/package.json')));
      return {
        ...bundler, ...renderer,
        webpackOverride: config => ({ ...config, resolve: {
          ...config.resolve, modules: [...(config.resolve?.modules || ['node_modules']), modules],
        } }),
      };
    } catch (error) {
      if (error.code !== 'MODULE_NOT_FOUND') throw error;
    }
  }
  throw new Error('Legacy Remotion is optional. Install it with: open_edit setup legacy-remotion');
}
