import React, { createContext, useContext, useState, useEffect } from 'react'

type Theme = 'unraid' | 'plex' | 'dark' | 'light'

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

  const isDark = theme === 'dark' || theme === 'plex'

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme)
    localStorage.setItem('theme', newTheme)
  }

  useEffect(() => {
    const root = document.documentElement
    
    // Remove all theme classes
    root.classList.remove('theme-unraid', 'theme-plex', 'dark')
    
    // Add the current theme class
    if (theme === 'unraid') {
      root.classList.add('theme-unraid')
    } else if (theme === 'plex') {
      root.classList.add('theme-plex')
    }
    
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