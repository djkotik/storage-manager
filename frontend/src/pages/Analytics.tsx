import React, { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import axios from 'axios'

interface StorageHistory {
  date: string
  total_size: number
  total_size_formatted: string
  file_count: number
  directory_count: number
}

interface AnalyticsData {
  history: StorageHistory[]
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D']

const Analytics: React.FC = () => {
  const [history, setHistory] = useState<StorageHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  useEffect(() => {
    fetchHistory()
  }, [days])

  const fetchHistory = async () => {
    setLoading(true)
    try {
      const response = await axios.get(`/api/analytics/history?days=${days}`)
      setHistory(response.data.history)
    } catch (error) {
      console.error('Error fetching history:', error)
    } finally {
      setLoading(false)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Analytics
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Storage usage trends and statistics
          </p>
        </div>
        
        <div>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="input"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
      </div>

      {/* Storage Usage Chart */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Storage Usage Over Time
        </h3>
        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : history.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
            No data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="date" 
                tickFormatter={formatDate}
                stroke="#9CA3AF"
              />
              <YAxis 
                tickFormatter={formatBytes}
                stroke="#9CA3AF"
              />
              <Tooltip 
                formatter={(value: number) => [formatBytes(value), 'Storage Used']}
                labelFormatter={formatDate}
              />
              <Line 
                type="monotone" 
                dataKey="total_size" 
                stroke="#3B82F6" 
                strokeWidth={2}
                dot={{ fill: '#3B82F6', strokeWidth: 2, r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Statistics Grid */}
      {history.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="card p-6">
            <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Current Storage
            </h4>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {history[history.length - 1]?.total_size_formatted || '0 B'}
            </p>
          </div>
          
          <div className="card p-6">
            <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Total Files
            </h4>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {history[history.length - 1]?.file_count.toLocaleString() || '0'}
            </p>
          </div>
          
          <div className="card p-6">
            <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Total Directories
            </h4>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {history[history.length - 1]?.directory_count.toLocaleString() || '0'}
            </p>
          </div>
        </div>
      )}

      {/* Recent History Table */}
      <div className="card">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent History
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Storage Used
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Files
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Directories
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
              {history.slice(-10).reverse().map((record, index) => (
                <tr key={index} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                    {formatDate(record.date)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                    {record.total_size_formatted}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {record.file_count.toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {record.directory_count.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default Analytics 