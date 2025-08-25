import React, { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Database, AlertTriangle, Save, RefreshCw } from 'lucide-react'
import axios from 'axios'

interface AppSettings {
  data_path: string
  scan_time: string
  max_scan_duration: number
  max_items_per_folder: number

  skip_appdata: boolean
  themes: string[]
}

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)
  const [scanTime, setScanTime] = useState('01:00')
  const [maxScanDuration, setMaxScanDuration] = useState(6)
  const [maxItemsPerFolder, setMaxItemsPerFolder] = useState(100)

  const [skipAppdata, setSkipAppdata] = useState(true)

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    setLoading(true)
    try {
      const response = await axios.get('/api/settings')
      setSettings(response.data)
      setScanTime(response.data.scan_time)
      setMaxScanDuration(response.data.max_scan_duration)
      setMaxItemsPerFolder(response.data.max_items_per_folder || 100)

      setSkipAppdata(response.data.skip_appdata !== false) // Default to true
    } catch (error) {
      console.error('Error fetching settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const saveSettings = async () => {
    setSaving(true)
    try {
      await axios.post('/api/settings', {
        scan_time: scanTime,
        max_scan_duration: maxScanDuration,
        max_items_per_folder: maxItemsPerFolder,

        skip_appdata: skipAppdata,
      })
      // Show success message
      alert('Settings saved successfully!')
    } catch (error) {
      console.error('Error saving settings:', error)
      alert('Error saving settings')
    } finally {
      setSaving(false)
    }
  }

  const resetDatabase = async () => {
    if (!confirm('Are you sure you want to reset the database? This will delete all scan data and cannot be undone.')) {
      return
    }

    setResetLoading(true)
    try {
      await axios.post('/api/database/reset')
      alert('Database reset successfully!')
    } catch (error) {
      console.error('Error resetting database:', error)
      alert('Error resetting database')
    } finally {
      setResetLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Settings
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Configure application settings
        </p>
      </div>

      {/* General Settings */}
      <div className="card p-6">
        <div className="flex items-center mb-4">
          <SettingsIcon className="h-5 w-5 text-gray-500 mr-2" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            General Settings
          </h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Data Path
            </label>
            <input
              type="text"
              value={settings?.data_path || '/data'}
              disabled
              className="input bg-gray-100 dark:bg-gray-700"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Path to scan for files (read-only)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Daily Scan Time
            </label>
            <input
              type="time"
              value={scanTime}
              onChange={(e) => setScanTime(e.target.value)}
              className="input"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Time for automatic daily scans
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Max Scan Duration (hours)
            </label>
            <input
              type="number"
              min="1"
              max="24"
              value={maxScanDuration}
              onChange={(e) => setMaxScanDuration(Number(e.target.value))}
              className="input"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Maximum time to allow scans to run
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Max Largest Items per Folder
            </label>
            <input
              type="number"
              min="1"
              max="1000"
              value={maxItemsPerFolder}
              onChange={(e) => setMaxItemsPerFolder(Number(e.target.value))}
              className="input"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Maximum number of largest items to show within a folder in Usage Explorer
            </p>
          </div>



          <div>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={skipAppdata}
                onChange={(e) => setSkipAppdata(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Skip Appdata Directory
              </span>
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Skip scanning the /appdata directory (contains thousands of Docker container files)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Available Themes
            </label>
            <div className="flex flex-wrap gap-2">
              {settings?.themes.map((theme) => (
                <span
                  key={theme}
                  className="px-2 py-1 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 rounded"
                >
                  {theme}
                </span>
              ))}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Available theme options
            </p>
          </div>
        </div>

        <div className="mt-6">
          <button
            onClick={saveSettings}
            disabled={saving}
            className="btn btn-primary px-4 py-2"
          >
            <Save className="h-4 w-4 mr-2" />
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Database Management */}
      <div className="card p-6">
        <div className="flex items-center mb-4">
          <Database className="h-5 w-5 text-red-500 mr-2" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Database Management
          </h3>
        </div>
        
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 dark:bg-yellow-900/20 dark:border-yellow-800 mb-4">
          <div className="flex">
            <AlertTriangle className="h-5 w-5 text-yellow-400 mr-2 mt-0.5" />
            <div>
              <h4 className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                Warning
              </h4>
              <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-1">
                Resetting the database will permanently delete all scan history, file records, and media metadata. 
                This action cannot be undone.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <button
            onClick={resetDatabase}
            disabled={resetLoading}
            className="btn btn-danger px-4 py-2"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${resetLoading ? 'animate-spin' : ''}`} />
            {resetLoading ? 'Resetting...' : 'Reset Database'}
          </button>
          
          <p className="text-sm text-gray-500 dark:text-gray-400">
            This will clear all data and start fresh
          </p>
        </div>
      </div>

      {/* System Information */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          System Information
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Application Version</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">1.0.0</p>
          </div>
          
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Database Type</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">SQLite</p>
          </div>
          
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Backend Framework</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">Flask (Python)</p>
          </div>
          
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Frontend Framework</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">React + TypeScript</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Settings 