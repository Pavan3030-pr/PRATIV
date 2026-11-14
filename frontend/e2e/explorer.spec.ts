import { expect, test } from '@playwright/test'

test('search, open a company and check a sourced fact', async ({ page }) => {
  await page.goto('/#/explore')
  await expect(page.getByRole('heading', { name: /Find a company/ })).toBeVisible()

  await page.getByRole('searchbox').fill('DNB')
  await page.getByRole('link', { name: /DNB BANK ASA/ }).first().click()

  await expect(page.getByRole('heading', { name: 'DNB BANK ASA', level: 1 })).toBeVisible()
  await expect(page.getByText('Facts and their sources')).toBeVisible()
  await expect(page.getByRole('button', { name: /check source/i }).first()).toBeVisible()
  await expect(page.getByText(/Not published \(never estimated\)|Latest annual accounts/).first()).toBeVisible()
})

test('how it works names the sources and the limits', async ({ page }) => {
  await page.goto('/#/explore')
  await page.getByRole('link', { name: 'How it works' }).click()
  await expect(page.getByRole('heading', { name: 'How this works' })).toBeVisible()
  await expect(page.getByText(/Registered address|Enhetsregisteret/).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Known limits' })).toBeVisible()
})

test('a company outside the dataset is read live from the register', async ({ page }) => {
  const entity = {
    organisasjonsnummer: '982463718',
    navn: 'TELENOR ASA',
    organisasjonsform: { kode: 'ASA' },
    stiftelsesdato: '1996-11-07',
    antallAnsatte: 9000,
    naeringskode1: { beskrivelse: 'Trådløs telekommunikasjon' },
    forretningsadresse: { adresse: ['Snarøyveien 30'], postnummer: '1360', poststed: 'FORNEBU', land: 'Norge' },
  }
  // Keep the test independent of what the committed crawl happens to contain.
  await page.route('**/explore/index.json', (route) =>
    route.fulfill({ json: [['984851006', 'DNB BANK ASA', 'Oslo', 'ASA', 'Banker', 1, 1]] }),
  )
  await page.route('**/data.brreg.no/**', (route) => {
    const url = route.request().url()
    if (url.includes('?navn=')) return route.fulfill({ json: { _embedded: { enheter: [entity] } } })
    if (url.endsWith('/982463718')) return route.fulfill({ json: entity })
    return route.fulfill({ status: 404, body: 'not found' })
  })

  await page.goto('/#/explore')
  await page.getByRole('searchbox').fill('telenor')
  await expect(page.getByText(/Found in Enhetsregisteret/)).toBeVisible()
  await page.getByRole('link', { name: /TELENOR ASA/ }).first().click()

  await expect(page.getByRole('heading', { name: 'TELENOR ASA', level: 1 })).toBeVisible()
  await expect(page.getByText('Registry only')).toBeVisible()
  await expect(page.getByText('Trådløs telekommunikasjon')).toBeVisible()
  await expect(page.getByRole('link', { name: /Official record/ })).toHaveAttribute(
    'href',
    'https://data.brreg.no/enhetsregisteret/api/enheter/982463718',
  )
})

test('compare two companies field by field', async ({ page }) => {
  await page.goto('/#/explore/compare/984851006/923609016')
  await expect(page.getByRole('heading', { name: 'Compare' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'DNB BANK ASA' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'EQUINOR ASA' })).toBeVisible()
  await expect(page.getByText(/Every value links to its source/)).toBeVisible()
})

test('a company page exposes job postings when the dataset has them', async ({ page }) => {
  await page.goto('/#/explore/c/980656616')
  await expect(page.getByRole('heading', { name: 'BYGGMAKKER HANDEL AS', level: 1 })).toBeVisible()
  await expect(page.getByText('Open roles on the company site')).toBeVisible()
  await expect(page.getByRole('link', { name: /søker regional salgssjef/ })).toBeVisible()
})
