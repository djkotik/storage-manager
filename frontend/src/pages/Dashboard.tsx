import React, { useState, useEffect } from 'react'
import { Play, Square, HardDrive, FolderOpen, FileText, Video, RefreshCw } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import axios from 'axios'

interface ScanStatus {
  status: string
  scanning: boolean
  scan_id?: number
  start_time?: string
  end_time?: string
  total_files?: number
  total_directories?: number
  total_size?: number
  total_size_formatted?: string
  current_path?: string
  error?: string
  estimated_completion?: string
  percentage_complete?: number
  elapsed_time?: string
  estimated_duration?: string
  is_first_scan?: boolean
}

interface AnalyticsOverview {
  total_files: number
  total_directories: number
  total_size: number
  total_size_formatted: string
  top_extensions: Array<{
    extension: string
    count: number
    total_size: number
    total_size_formatted: string
  }>
  media_files: number
}

interface TopShare {
  name: string
  path: string
  size: number
  size_formatted: string
  file_count: number
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  raw: string
}

const Dashboard: React.FC = () => {
  const [scanStatus, setScanStatus] = useState<ScanStatus>({ status: 'idle', scanning: false })
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null)
  const [topShares, setTopShares] = useState<TopShare[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [scanLoading, setScanLoading] = useState(false)

  useEffect(() => {
    fetchData()
    // More frequent updates when scan is running
    const interval = setInterval(fetchData, scanStatus.scanning ? 2000 : 10000)
    return () => clearInterval(interval)
  }, [scanStatus.scanning])

  const fetchData = async () => {
    try {
      // Always fetch scan status for real-time updates
      const statusRes = await axios.get('/api/scan/status', { timeout: 5000 })
      setScanStatus(statusRes.data)
      
      // If scan is running, fetch all data more frequently
      if (statusRes.data.scanning) {
        const [analyticsRes, topSharesRes, logsRes] = await Promise.all([
          axios.get('/api/analytics/overview', { timeout: 10000 }),
          axios.get('/api/analytics/top-shares', { timeout: 15000 }),
          axios.get('/api/logs?lines=50', { timeout: 5000 })
        ])
        
        setAnalytics(analyticsRes.data)
        setTopShares(topSharesRes.data.top_shares)
        setLogs(logsRes.data.logs)
      } else {
        // Only fetch other data if not already loaded or if scan just completed
        if (!analytics) {
          try {
            const analyticsRes = await axios.get('/api/analytics/overview', { timeout: 10000 })
            setAnalytics(analyticsRes.data)
          } catch (error) {
            console.error('Error fetching analytics:', error)
          }
        }
        
        if (topShares.length === 0) {
          try {
            const topSharesRes = await axios.get('/api/analytics/top-shares', { timeout: 15000 })
            setTopShares(topSharesRes.data.top_shares)
          } catch (error) {
            console.error('Error fetching top shares:', error)
          }
        }
        
        // Fetch logs less frequently when not scanning
        try {
          const logsRes = await axios.get('/api/logs?lines=50', { timeout: 5000 })
          setLogs(logsRes.data.logs)
        } catch (error) {
          console.error('Error fetching logs:', error)
        }
      }
    } catch (error) {
      console.error('Error fetching data:', error)
    } finally {
      setLoading(false)
    }
  }

  const startScan = async () => {
    setScanLoading(true)
    try {
      await axios.post('/api/scan/start')
      await fetchData()
    } catch (error) {
      console.error('Error starting scan:', error)
    } finally {
      setScanLoading(false)
    }
  }

  const stopScan = async () => {
    try {
      await axios.post('/api/scan/stop')
      await fetchData()
    } catch (error) {
      console.error('Error stopping scan:', error)
    }
  }

  const getLogLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
        return 'text-red-500'
      case 'WARNING':
        return 'text-yellow-500'
      case 'INFO':
        return 'text-blue-500'
      default:
        return 'text-gray-500'
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Dashboard
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Overview of your unRAID storage
          </p>
        </div>
        
        {/* Scan Controls */}
        <div className="flex space-x-3">
          {scanStatus.scanning ? (
            <button
              onClick={stopScan}
              disabled={scanLoading}
              className="btn btn-danger px-4 py-2"
            >
              <Square className="h-4 w-4 mr-2" />
              Stop Scan
            </button>
          ) : (
            <button
              onClick={startScan}
              disabled={scanLoading}
              className="btn btn-primary px-4 py-2"
            >
              <Play className="h-4 w-4 mr-2" />
              Start Scan
            </button>
          )}
        </div>
      </div>

      {/* Scan Status */}
      {scanStatus.scanning && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 dark:bg-blue-900/20 dark:border-blue-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-3"></div>
              <div>
                <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                  Scan in progress...
                </p>
                {scanStatus.total_files && (
                  <p className="text-xs text-blue-700 dark:text-blue-300">
                    Processed {scanStatus.total_files.toLocaleString()} files, {scanStatus.total_directories?.toLocaleString()} directories
                  </p>
                )}
                {scanStatus.current_path && (
                  <p className="text-xs text-blue-700 dark:text-blue-300">
                    Current: {scanStatus.current_path}
                  </p>
                )}
                {scanStatus.elapsed_time && (
                  <p className="text-xs text-blue-700 dark:text-blue-300">
                    Elapsed: {scanStatus.elapsed_time}
                  </p>
                )}
                {scanStatus.estimated_completion && !scanStatus.is_first_scan && (
                  <p className="text-xs text-blue-700 dark:text-blue-300">
                    Estimated completion: {new Date(scanStatus.estimated_completion).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                {scanStatus.total_size_formatted}
              </p>
              {scanStatus.percentage_complete !== undefined && scanStatus.percentage_complete !== null && !scanStatus.is_first_scan && (
                <div className="mt-2">
                  <div className="w-32 bg-blue-200 rounded-full h-2 dark:bg-blue-700">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300" 
                      style={{ width: `${scanStatus.percentage_complete}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-blue-700 dark:text-blue-300 mt-1">
                    {scanStatus.percentage_complete}% complete
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Overview Cards */}
      {analytics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="card p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <HardDrive className="h-8 w-8 text-blue-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  Total Storage
                </p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {analytics.total_size_formatted}
                </p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <FileText className="h-8 w-8 text-green-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  Total Files
                </p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {analytics.total_files.toLocaleString()}
                </p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <FolderOpen className="h-8 w-8 text-purple-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  Directories
                </p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {analytics.total_directories.toLocaleString()}
                </p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Video className="h-8 w-8 text-red-600" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  Media Files
                </p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {analytics.media_files.toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* File Types Chart */}
        {analytics && (
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Top File Types
            </h3>
            <div className="space-y-3">
              {analytics.top_extensions.slice(0, 10).map((fileType) => (
                <div key={fileType.extension} className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-3 h-3 bg-blue-500 rounded-full mr-3"></div>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {fileType.extension || 'No extension'}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {fileType.total_size_formatted}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {fileType.count.toLocaleString()} files
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Folder Shares */}
        <div className="card p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Top Folder Shares
          </h3>
          <div className="space-y-3">
            {topShares.length > 0 ? (
              topShares.map((share) => (
                <div key={share.path} className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {share.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {share.size_formatted}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {share.file_count.toLocaleString()} files
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-gray-500">No shares found</div>
            )}
          </div>
        </div>
      </div>

      {/* System Status */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          System Status
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Scan Status</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {scanStatus.scanning ? 'Scanning...' : 'Idle'}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Last Updated</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {new Date().toLocaleTimeString()}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Data Path</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              /data
            </p>
          </div>
        </div>
      </div>

      {/* Live Logs - Full Width */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Detailed System Logs
          </h3>
          <button
            onClick={fetchData}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="bg-gray-900 text-green-400 p-4 rounded-md font-mono text-xs h-80 overflow-y-auto">
          {logs.length > 0 ? (
            logs.map((log, index) => (
              <div key={index} className="mb-2 leading-relaxed">
                <span className={getLogLevelColor(log.level)}>
                  [{log.level}]
                </span>
                <span className="text-gray-400 ml-2">
                  {log.timestamp}
                </span>
                <span className="text-white ml-2 break-words">
                  {log.message}
                </span>
              </div>
            ))
          ) : (
            <div className="text-gray-500">No logs available</div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard 