import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  HardDrive, 
  FolderOpen, 
  Video, 
  BarChart3, 
  Copy, 
  Settings, 
  Menu, 
  Sun, 
  Moon, 
  Palette,
  X,
  FileText
} from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'
import axios from 'axios'

interface LayoutProps {
  children: React.ReactNode
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [version, setVersion] = useState('1.4.1')
  const [availableThemes, setAvailableThemes] = useState([
    { name: 'unRAID', value: 'unraid' },
    { name: 'Plex', value: 'plex' },
    { name: 'Dark', value: 'dark' },
    { name: 'Light', value: 'light' },
  ])
  const location = useLocation()
  const { theme, setTheme, isDark } = useTheme()

  const navigation = [
    { name: 'Dashboard', href: '/', icon: HardDrive },
    { name: 'Usage Explorer', href: '/files', icon: FolderOpen },
    { name: 'Files', href: '/media', icon: FileText },
    { name: 'Analytics', href: '/analytics', icon: BarChart3 },
    { name: 'Duplicates', href: '/duplicates', icon: Copy },
    { name: 'Settings', href: '/settings', icon: Settings },
  ]

  // Fetch settings and sync theme
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await axios.get('/api/settings')
        const settings = response.data
        console.log('Fetched settings:', settings) // Debug log
        
        // Update available themes from backend
        if (settings.themes && Array.isArray(settings.themes)) {
          const themes = settings.themes.map((themeValue: string) => ({
            name: themeValue.charAt(0).toUpperCase() + themeValue.slice(1),
            value: themeValue
          }))
          setAvailableThemes(themes)
          console.log('Updated available themes:', themes) // Debug log
        }
        
        // Sync theme with backend
        if (settings.theme && settings.theme !== theme) {
          setTheme(settings.theme)
        }
      } catch (error) {
        console.error('Error fetching settings:', error)
      }
    }
    
    const fetchVersion = async () => {
      try {
        const response = await axios.get('/api/version')
        setVersion(response.data.version)
      } catch (error) {
        console.error('Error fetching version:', error)
      }
    }
    
    fetchSettings()
    fetchVersion()
  }, [theme, setTheme])

  const handleThemeChange = async (newTheme: string) => {
    try {
      console.log('Changing theme to:', newTheme) // Debug log
      // Update backend settings
      await axios.post('/api/settings', { theme: newTheme })
      // Update local theme
      setTheme(newTheme as any)
    } catch (error) {
      console.error('Error updating theme:', error)
    }
  }

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-50 lg:hidden ${sidebarOpen ? 'block' : 'hidden'}`}>
        <div className="fixed inset-0 bg-gray-600 bg-opacity-75" onClick={() => setSidebarOpen(false)} />
        <div className="fixed inset-y-0 left-0 flex w-64 flex-col bg-white dark:bg-gray-800">
          <div className="flex h-16 items-center justify-between px-4">
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                Storage Analyzer
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">v{version}</p>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X className="h-6 w-6" />
            </button>
          </div>
          <nav className="flex-1 space-y-1 px-2 py-4">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`group flex items-center px-2 py-2 text-sm font-medium rounded-md ${
                    isActive
                      ? 'bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white'
                  }`}
                  onClick={() => setSidebarOpen(false)}
                >
                  <item.icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:flex lg:w-64 lg:flex-col lg:fixed lg:inset-y-0">
        <div className="flex flex-col flex-grow bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
          <div className="flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-700">
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                Storage Analyzer
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">v{version}</p>
            </div>
          </div>
          <nav className="flex-1 space-y-1 px-2 py-4">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`group flex items-center px-2 py-2 text-sm font-medium rounded-md ${
                    isActive
                      ? 'bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white'
                  }`}
                >
                  <item.icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              )
            })}
          </nav>
          
          {/* Theme selector */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Theme
              </span>
              <div className="flex items-center space-x-2">
                {isDark ? (
                  <Sun className="h-4 w-4 text-gray-400" />
                ) : (
                  <Moon className="h-4 w-4 text-gray-400" />
                )}
                <select
                  value={theme}
                  onChange={(e) => handleThemeChange(e.target.value)}
                  className="text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {availableThemes.map((themeOption) => (
                    <option key={themeOption.value} value={themeOption.value}>
                      {themeOption.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64 flex flex-col flex-1">
        {/* Top bar */}
        <div className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b border-gray-200 bg-white px-4 shadow-sm dark:border-gray-700 dark:bg-gray-800 sm:gap-x-6 sm:px-6 lg:px-8">
          <button
            type="button"
            className="-m-2.5 p-2.5 text-gray-700 lg:hidden dark:text-gray-300"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </button>

          <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
            <div className="flex flex-1"></div>
            <div className="flex items-center gap-x-4 lg:gap-x-6">
              {/* Theme toggle for mobile */}
              <div className="lg:hidden flex items-center space-x-2">
                <Palette className="h-4 w-4 text-gray-400" />
                <select
                  value={theme}
                  onChange={(e) => handleThemeChange(e.target.value)}
                  className="text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {availableThemes.map((themeOption) => (
                    <option key={themeOption.value} value={themeOption.value}>
                      {themeOption.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="py-6">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Layout 