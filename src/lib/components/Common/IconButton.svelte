<script lang="ts">
  import type { HTMLButtonAttributes } from 'svelte/elements'
  import * as Icon from '$lib/icons'

  type Props = {
    title: string
    iconName: keyof typeof Icon
    variant?: string
    size?: number
    onClick?: (event: MouseEvent) => void
    disabled?: boolean
    iconSize?: number
  } & HTMLButtonAttributes

  const {
    variant = 'default',
    size = 40,
    iconName,
    iconSize = 20,
    onClick = () => {},
    disabled = false,
    title,
    ...restProps
  }: Props = $props()

  function getClasses() {
    let classes =
      'rounded-lg text-sm flex items-center justify-center cursor-pointer shrink-0 text-gray-400'

    if (variant === 'dark') classes += ' hover:bg-primary-750'
    else if (variant === 'light') classes += ' hover:bg-gray-100'
    else if (variant === 'overlay') classes += ' hover:bg-white/10'
    else classes += ' hover:bg-gray-100 dark:hover:bg-primary-750'

    return classes
  }

  const IconComponent = $derived(Icon[iconName])
</script>

<button
  {...restProps}
  type="button"
  class={getClasses()}
  style:width={`${size}px`}
  style:height={`${size}px`}
  onclick={onClick}
  {title}
  {disabled}
  aria-label={title}
>
  <IconComponent size={iconSize} />
</button>
