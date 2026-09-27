// How the topic chart component is built (ADR 0011, ADR 0025).
//
// Vite compiles src/main.jsx and everything it imports -- React included --
// into ONE file, ../static/app/app.js, which is committed and served by Flask
// like the stylesheet. The host never runs Node (ADR 0011).
//
// Build:  npm run build     (in this folder)
// Test:   npm test

import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, relative, resolve, sep } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const HERE = import.meta.dirname
const OUT = resolve(HERE, '..', 'static', 'app')

// ------------------------------------------------------------ staleness
//
// ADR 0011's guard on committing a built file: the build writes a hash of
// everything it was built FROM beside the bundle, and tests/check_bundle.py
// recomputes the same hash from the working tree. Edit a component and forget
// to rebuild, and that check fails -- instead of the site quietly running
// code that is not in its own repository.
//
// The rule, which check_bundle.py repeats exactly:
//   every file under src/ except tests, plus package.json, package-lock.json
//   and this file; paths relative to this folder, with "/" separators,
//   sorted; for each: the path, a newline, the contents with Windows line
//   endings turned into "\n", a newline.
// Line endings are normalised because git may check a file out with CRLF on
// one machine and LF on another, and the same source must give the same hash.

function sourceFiles() {
  const files = []
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name)
      if (statSync(path).isDirectory()) walk(path)
      else if (!/\.test\.jsx?$/.test(name)) files.push(path)
    }
  }
  walk(join(HERE, 'src'))
  for (const name of ['package.json', 'package-lock.json', 'vite.config.js']) {
    files.push(join(HERE, name))
  }
  return files
    .map((path) => relative(HERE, path).split(sep).join('/'))
    .sort()
}

function sourceHash() {
  const hash = createHash('sha256')
  for (const rel of sourceFiles()) {
    const text = readFileSync(join(HERE, rel), 'utf8').replace(/\r\n/g, '\n')
    hash.update(rel + '\n')
    hash.update(text)
    hash.update('\n')
  }
  return hash.digest('hex')
}

// A plugin is an object with hooks Vite calls at points in the build;
// closeBundle runs once everything has been written.
function writeSourceHash() {
  return {
    name: 'nextcf-source-hash',
    closeBundle() {
      writeFileSync(join(OUT, 'sources.sha256'), sourceHash() + '\n')
    },
  }
}

export default defineConfig({
  plugins: [react(), writeSourceHash()],
  build: {
    outDir: OUT,
    // Only static/app/ is emptied, never static/ itself, which holds the
    // stylesheet and the fonts.
    emptyOutDir: true,
    rolldownOptions: {
      input: resolve(HERE, 'src', 'main.jsx'),
      // A fixed name, not a content hash: the template names the file, and a
      // renamed bundle would need the template edited on every build.
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'app-[name].js',
        assetFileNames: 'app-[name][extname]',
      },
    },
  },
  // Vitest reads this file too. jsdom is a browser page simulated in Node,
  // so a component can be rendered and clicked without a real browser.
  test: {
    environment: 'jsdom',
  },
})
