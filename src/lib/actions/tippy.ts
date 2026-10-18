import tippyJs, { type Props } from 'tippy.js'
import 'tippy.js/dist/tippy.css'

export function tippy(node: HTMLElement, options: Partial<Props>) {
  options = {
    allowHTML: true,
    interactive: true,
    appendTo: () => document.body,
    onCreate(instance) {
      const box = instance.popper.querySelector('.tippy-box') as HTMLElement
      if (box) {
        box.style.backgroundColor = '#3d485e'
        box.style.color = '#fff'
        box.style.fontSize = '14px'
        box.style.borderRadius = '0.375rem'
        box.style.padding = '2px 2px'
      }
      const arrow = instance.popper.querySelector('.tippy-arrow') as HTMLElement
      if (arrow) {
        arrow.style.color = '#3d485e'
      }
    },
    ...options
  }

  const instance = tippyJs(node, options)

  return {
    update(newOptions: Partial<Props>) {
      instance.setProps(newOptions)
    },
    destroy() {
      instance.destroy()
    }
  }
}
