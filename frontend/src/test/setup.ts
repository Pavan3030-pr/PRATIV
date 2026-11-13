import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.location.hash = ''
  sessionStorage.clear()
})

// jsdom does not implement scrolling; the explorer calls it after navigation.
window.scrollTo = () => {}
