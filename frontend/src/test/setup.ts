import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

// jsdom does not implement the native modal APIs; real focus containment is
// verified in the browser acceptance run.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '')
  this.querySelector<HTMLElement>('button, input, select, textarea')?.focus()
}
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open')
}
