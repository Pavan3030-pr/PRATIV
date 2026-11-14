import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

/**
 * Accessibility is measured, not assumed: every explorer page is scanned by axe and no serious or
 * critical violation may remain. Moderate/minor notes are printed but do not fail the build.
 */
const pages = [
  { name: 'home', url: '/#/explore', ready: 'Find a company. See where every fact came from.' },
  { name: 'company', url: '/#/explore/c/980656616', ready: 'BYGGMAKKER HANDEL AS' },
  { name: 'compare', url: '/#/explore/compare/980656616/819731322', ready: 'Compare' },
  { name: 'about', url: '/#/explore/about', ready: 'How this works' },
]

for (const page of pages) {
  test(`${page.name} has no serious or critical axe violations`, async ({ page: tab }) => {
    await tab.goto(page.url)
    await expect(tab.getByRole('heading', { name: page.ready, level: 1 })).toBeVisible()

    const results = await new AxeBuilder({ page: tab }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    const report = blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s) — ${v.help}`)
    expect(blocking, report.join('\n')).toEqual([])

    const notable = results.violations.filter((v) => v.impact !== 'serious' && v.impact !== 'critical')
    if (notable.length) console.log(`${page.name} advisory:`, notable.map((v) => `${v.id}: ${v.nodes.length}`).join(', '))
  })
}
