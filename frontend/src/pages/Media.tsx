import React, { useState, useEffect } from 'react'
import { Search, Filter, File, Folder, Calendar, FileText, Image, Film, Music, Archive, Code } from 'lucide-react'
import axios from 'axios'

interface FileRecord {
  id: number
  path: string
  name: string
  size: number
  size_formatted: string
  is_directory: boolean
  extension: string
  modified_time: string
  parent_path: string
}

const Media: React.FC = () => {
  const [files, setFiles] = useState<FileRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [fileType, setFileType] = useState('')
  const [modifiedSince, setModifiedSince] = useState('')
  const [scanStatus, setScanStatus] = useState<any>(null)
  const [viewMode, setViewMode] = useState<'normal' | 'compact'>('normal')

  useEffect(() => {
    fetchFiles()
    fetchScanStatus()
  }, [currentPage, search, fileType, modifiedSince])

  const fetchScanStatus = async () => {
    try {
      const response = await axios.get('/api/scan/status')
      setScanStatus(response.data)
    } catch (error) {
      console.error('Error fetching scan status:', error)
    }
  }

  const fetchFiles = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        per_page: '50',
        search: search,
        type: fileType,
        modified_since: modifiedSince,
      })

      const response = await axios.get(`/api/files?${params}`)
      setFiles(response.data.files)
      setTotalPages(response.data.pages)
    } catch (error) {
      console.error('Error fetching files:', error)
    } finally {
      setLoading(false)
    }
  }

  const getFileIcon = (isDirectory: boolean, extension: string) => {
    if (isDirectory) {
      return <Folder className="h-5 w-5 text-blue-500" />
    }
    
    const ext = extension.toLowerCase()
    
    switch (ext) {
      case '.jpg':
      case '.jpeg':
      case '.png':
      case '.gif':
      case '.bmp':
      case '.svg':
      case '.webp':
      case '.tiff':
        return <Image className="h-5 w-5 text-blue-500" />
      case '.mp4':
      case '.avi':
      case '.mkv':
      case '.mov':
      case '.wmv':
      case '.flv':
      case '.webm':
      case '.m4v':
      case '.ts':
      case '.mts':
        return <Film className="h-5 w-5 text-purple-500" />
      case '.mp3':
      case '.wav':
      case '.flac':
      case '.aac':
      case '.ogg':
      case '.m4a':
      case '.wma':
        return <Music className="h-5 w-5 text-green-500" />
      case '.zip':
      case '.rar':
      case '.7z':
      case '.tar':
      case '.gz':
        return <Archive className="h-5 w-5 text-orange-500" />
      case '.txt':
      case '.pdf':
      case '.doc':
      case '.docx':
      case '.rtf':
        return <FileText className="h-5 w-5 text-red-500" />
      case '.js':
      case '.ts':
      case '.py':
      case '.cpp':
      case '.java':
      case '.html':
      case '.css':
        return <Code className="h-5 w-5 text-yellow-500" />
      default:
        return <File className="h-5 w-5 text-gray-500" />
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Files
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Browse and manage your files
        </p>
      </div>

      {/* Scan Status Notification */}
      {scanStatus?.scanning && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 dark:bg-blue-900/20 dark:border-blue-800">
          <div className="flex items-center">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-3"></div>
            <div>
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                Scan in progress...
              </p>
              <p className="text-xs text-blue-700 dark:text-blue-300">
                File data will be available once the scan completes. Currently processing: {scanStatus.total_files?.toLocaleString() || 0} files
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Filters and View Controls */}
      <div className="card p-6">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
          {/* Search with Filter Button */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Search
            </label>
            <div className="flex space-x-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search files..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <button
                onClick={fetchFiles}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 whitespace-nowrap"
              >
                <Filter className="h-4 w-4" />
              </button>
            </div>
          </div>
          
          {/* Type Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Type
            </label>
            <select
              value={fileType}
              onChange={(e) => setFileType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Types</option>
              <option value="file">Files Only</option>
              <option value="directory">Directories Only</option>
            </select>
          </div>
          
          {/* Modified Since Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Modified Since
            </label>
            <select
              value={modifiedSince}
              onChange={(e) => setModifiedSince(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Any Time</option>
              <option value="today">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="year">This Year</option>
              <option value="last_year">Last Year</option>
              <option value="older_1_year">Older Than 1 Year</option>
              <option value="older_5_years">Older Than 5 Years</option>
            </select>
          </div>
          
          {/* View Mode Controls */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              View Mode
            </label>
            <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
              <button
                onClick={() => setViewMode('normal')}
                className={`flex-1 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  viewMode === 'normal'
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                Normal
              </button>
              <button
                onClick={() => setViewMode('compact')}
                className={`flex-1 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  viewMode === 'compact'
                    ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                Compact
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Files Grid - Responsive with view mode options */}
      <div className={`grid gap-4 ${
        viewMode === 'normal' 
          ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-2' 
          : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5'
      }`}>
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="flex items-center justify-between mb-3">
                <div className="h-5 w-5 bg-gray-300 dark:bg-gray-600 rounded"></div>
                <div className="h-4 w-12 bg-gray-300 dark:bg-gray-600 rounded"></div>
              </div>
              <div className="h-4 bg-gray-300 dark:bg-gray-600 rounded mb-2"></div>
              <div className="space-y-1">
                <div className="h-3 bg-gray-300 dark:bg-gray-600 rounded"></div>
                <div className="h-3 bg-gray-300 dark:bg-gray-600 rounded"></div>
                <div className="h-3 bg-gray-300 dark:bg-gray-600 rounded"></div>
              </div>
            </div>
          ))
        ) : files.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <File className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">No files found</p>
          </div>
        ) : (
          files.map((file) => (
            <div 
              key={file.id} 
              className="card p-4 hover:shadow-lg transition-all duration-200 hover:scale-[1.02] group cursor-pointer relative"
              title={`${file.name}\nPath: ${file.path}\nSize: ${file.size_formatted}\nModified: ${formatDate(file.modified_time)}`}
            >
              {/* Hover tooltip */}
              <div className="opacity-0 group-hover:opacity-100 absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-4 py-3 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-xs rounded-lg shadow-xl border border-gray-200 dark:border-gray-600 pointer-events-none transition-opacity duration-200 z-20 max-w-sm">
                <div className="space-y-2">
                  <div className="font-semibold text-sm border-b border-gray-200 dark:border-gray-600 pb-1">{file.name}</div>
                  <div className="text-gray-600 dark:text-gray-300">
                    <span className="font-medium">Path:</span> {file.path}
                  </div>
                  <div className="text-gray-600 dark:text-gray-300">
                    <span className="font-medium">Size:</span> {file.size_formatted}
                  </div>
                  <div className="text-gray-600 dark:text-gray-300">
                    <span className="font-medium">Modified:</span> {formatDate(file.modified_time)}
                  </div>
                </div>
                <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-white dark:border-t-gray-800"></div>
              </div>
              
              <div className="flex items-center justify-between mb-3">
                {getFileIcon(file.is_directory, file.extension)}
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                  {file.is_directory ? 'DIR' : file.extension?.toUpperCase() || 'FILE'}
                </span>
              </div>
              
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2 text-sm leading-tight line-clamp-2">
                {file.name}
              </h3>
              
              <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                <p className="truncate">
                  <span className="font-medium">Path:</span> {file.path}
                </p>
                <p>
                  <span className="font-medium">Size:</span> {file.size_formatted}
                </p>
                <p>
                  <span className="font-medium">Modified:</span> {formatDate(file.modified_time)}
                </p>
              </div>
              
              <div className="mt-3 pt-2 border-t border-gray-200 dark:border-gray-600">
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  <span className="font-medium">Parent:</span> {file.parent_path}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
            disabled={currentPage === 1}
            className="btn btn-secondary px-3 py-1 text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-700 dark:text-gray-300">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
            disabled={currentPage === totalPages}
            className="btn btn-secondary px-3 py-1 text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

export default Media 