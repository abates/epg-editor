class DarkModeManager {
  isActive = $state(false)

  init() {
    const isDark =
      localStorage.theme === 'dark' ||
      (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)

    this.isActive = isDark
    this.applyTheme()
  }

  toggle() {
    this.isActive = !this.isActive
    this.applyTheme()
  }

  applyTheme() {
    if (this.isActive) {
      document.documentElement.classList.add('dark')
      localStorage.theme = 'dark'
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.theme = 'light'
    }
  }
}

export const darkMode = new DarkModeManager()
