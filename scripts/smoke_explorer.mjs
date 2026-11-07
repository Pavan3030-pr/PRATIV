#!/usr/bin/env node
// Smoke test for the public explorer.
//   node scripts/smoke_explorer.mjs            -> checks the generated data (and frontend/dist if built)
//   node scripts/smoke_explorer.mjs https://prativ.vercel.app   -> also checks the deployed site
import { readFileSync, readdirSync, existsSync } from 'node:fs'

let failed = 0
const ok = (cond, msg) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) failed++ }

const dir = 'frontend/public/explore'
const index = JSON.parse(readFileSync(`${dir}/index.json`, 'utf8'))
const files = readdirSync(`${dir}/c`)
ok(index.length >= 1000, `index has ${index.length} companies (need >= 1000)`)
ok(files.length === index.length, `profile files (${files.length}) match index rows (${index.length})`)

let badUrl = 0, badDate = 0, badPath = 0, noFacts = 0, wrongCompany = 0
for (const row of index) {
  const d = JSON.parse(readFileSync(`${dir}/c/${row[0]}.json`, 'utf8'))
  if (!d.facts.length) noFacts++
  if (d.n !== row[0]) wrongCompany++
  for (const f of d.facts) {
    const u = f.u ?? d.base
    const web = /^(website|social_|news_)/.test(f.k)   // verified facts from the company's own site
    if (web ? !u.startsWith('https://') : !(u.startsWith('https://data.brreg.no/') && u.includes(row[0]))) badUrl++
    if (!f.t) badDate++
    if (!f.p) badPath++
  }
}
ok(noFacts === 0, `every company has facts (${noFacts} without)`)
ok(wrongCompany === 0, `every file belongs to its own org number (${wrongCompany} mismatched)`)
ok(badUrl === 0, `every fact links to a valid source (Brreg for registry facts) (${badUrl} bad)`)
ok(badDate === 0, `every fact has a retrieval date (${badDate} missing)`)
ok(badPath === 0, `every fact names its source field (${badPath} missing)`)

if (existsSync('frontend/dist/index.html')) {
  ok(existsSync('frontend/dist/explore/index.json'), 'build output contains explore/index.json')
  const jsFiles = readdirSync('frontend/dist/assets').filter((f) => f.endsWith('.js'))
  const bundle = jsFiles.map((f) => readFileSync(`frontend/dist/assets/${f}`, 'utf8')).join('')
  ok(bundle.includes('Find a company. See where every fact came from.'), 'built bundle contains the explorer page')
} else {
  console.log('SKIP  frontend/dist not built yet')
}

const base = process.argv[2]?.replace(/\/$/, '')
if (base) {
  const sample = index[0][0]
  for (const [path, test] of [
    ['/', (r, t) => r.ok && t.includes('<div id="root">')],
    ['/explore/index.json', (r, t) => r.ok && Array.isArray(JSON.parse(t))],
    [`/explore/c/${sample}.json`, (r, t) => r.ok && JSON.parse(t).n === sample],
  ]) {
    try {
      const r = await fetch(base + path)
      const t = await r.text()
      ok(test(r, t), `${base}${path} -> ${r.status}`)
    } catch (e) { ok(false, `${base}${path} failed: ${e.message}`) }
  }
  try {
    const r = await fetch(`https://data.brreg.no/enhetsregisteret/api/enheter/${sample}`, { headers: { Origin: base } })
    ok(r.ok && r.headers.get('access-control-allow-origin') !== null, 'Brreg allows browser requests (Check source will work)')
  } catch (e) { ok(false, `Brreg check failed: ${e.message}`) }
}
console.log(failed ? `\n${failed} check(s) failed` : '\nAll checks passed')
process.exit(failed ? 1 : 0)
