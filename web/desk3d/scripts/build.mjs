import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as esbuild from 'esbuild';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');
const dev = join(root, '.dev');
const serve = process.argv.includes('--serve');

const template = await readFile(join(root, 'src/index.html'), 'utf8');
const css = await readFile(join(root, 'src/styles.css'), 'utf8');

const shared = {
  entryPoints: [join(root, 'src/main.js')],
  bundle: true,
  format: 'esm',
  target: 'es2022',
  legalComments: 'none',
};

const flagIndex = process.argv.indexOf('--gateway-out');
const gatewayOut = flagIndex > -1 ? process.argv[flagIndex + 1] : null;

const bundle = async ({ hosted = false, gateway = false } = {}) => {
  const result = await esbuild.build({
    ...shared,
    write: false,
    minify: !process.env.DESK_DEBUG,
    define: { __DESK_HOSTED__: String(hosted), __DESK_GATEWAY__: String(gateway) },
  });
  return result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
};

const fill = (script) => template.replace('/*STYLE*/', () => css).replace('/*SCRIPT*/', () => script);

const documentFrom = (fragment) => {
  const split = fragment.indexOf('<div class="app"');
  const head = fragment.slice(0, split);
  const body = fragment.slice(split);
  return `<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<link rel="icon" href="data:,">\n${head}</head>\n<body>\n${body}</body>\n</html>\n`;
};

if (serve) {
  await mkdir(dev, { recursive: true });
  const page = documentFrom(template.replace('/*STYLE*/', () => css).replace('<script type="module">/*SCRIPT*/</script>', '<script type="module" src="./main.js"></script>'));
  await writeFile(join(dev, 'index.html'), page);
  const ctx = await esbuild.context({
    ...shared,
    outdir: dev,
    sourcemap: true,
    define: { __DESK_HOSTED__: 'false', __DESK_GATEWAY__: 'false' },
  });
  await ctx.watch();
  const { hosts, port } = await ctx.serve({ servedir: dev, port: Number(process.env.PORT) || 5173 });
  console.log(`desk3d dev server on http://${hosts[0]}:${port}`);
} else {
  await mkdir(dist, { recursive: true });
  const [live, hosted, gateway] = await Promise.all([bundle(), bundle({ hosted: true }), bundle({ gateway: true })]);
  const gatewayPage = documentFrom(fill(gateway));
  await writeFile(join(dist, 'desk3d.html'), documentFrom(fill(live)));
  await writeFile(join(dist, 'desk3d.artifact.html'), fill(hosted));
  await writeFile(join(dist, 'desk3d.gateway.html'), gatewayPage);
  console.log('Built dist/desk3d.html, dist/desk3d.artifact.html and dist/desk3d.gateway.html');
  if (gatewayOut) {
    const target = resolve(root, gatewayOut);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, gatewayPage);
    console.log(`Wrote the gateway page to ${target}`);
  }
}
