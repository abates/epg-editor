import type { Component } from 'svelte'

export interface ModalCallbacks {
  onClose?: () => void
  onClosed?: () => void
  onOpen?: () => void
  onOpened?: () => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComponent = Component<any>

export class ModalContext {
  isOpen = $state(false)
  component: AnyComponent | null = $state(null)
  props: Record<string, unknown> = $state({})
  callbacks: ModalCallbacks = $state({})

  open(
    component: AnyComponent,
    props: Record<string, unknown> = {},
    callbacks: ModalCallbacks = {}
  ) {
    this.callbacks = { ...this.callbacks, ...callbacks }
    this.callbacks.onOpen?.()
    this.component = component
    this.props = props
    this.isOpen = true
    this.callbacks.onOpened?.()
  }

  close(callbacks: ModalCallbacks = {}) {
    this.callbacks = { ...this.callbacks, ...callbacks }
    this.callbacks.onClose?.()
    this.isOpen = false
    this.component = null
    this.callbacks.onClosed?.()
  }
}

export const MODAL_KEY = 'modal'
