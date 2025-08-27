import React, { createContext, useContext, useState, useEffect } from 'react'

type Theme = 'unraid' | 'plex' | 'emby' | 'jellyfin' | 'dark' | 'light' | 'dark-lime'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  isDark: boolean
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

interface ThemeProviderProps {
  children: React.ReactNode
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme')
    return (saved as Theme) || 'unraid'
  })

  const isDark = theme === 'dark' || theme === 'plex' || theme === 'emby' || theme === 'jellyfin' || theme === 'dark-lime'

  const setTheme = (newTheme: Theme) => {
    console.log('Setting theme to:', newTheme) // Debug log
    setThemeState(newTheme)
    localStorage.setItem('theme', newTheme)
  }

  useEffect(() => {
    const root = document.documentElement
    console.log('Applying theme:', theme) // Debug log
    
    // Remove all theme classes
    root.classList.remove('theme-unraid', 'theme-plex', 'theme-emby', 'theme-jellyfin', 'theme-dark', 'theme-light', 'dark')
    
    // Add the current theme class
    root.classList.add(`theme-${theme}`)
    
    // Add dark class for dark themes
    if (isDark) {
      root.classList.add('dark')
    }
  }, [theme, isDark])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isDark }}>
      {children}
    </ThemeContext.Provider>
  )
} 