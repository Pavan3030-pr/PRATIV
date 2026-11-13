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
