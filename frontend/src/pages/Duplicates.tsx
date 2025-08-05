import React, { useState, useEffect } from 'react'
import { Trash2, AlertTriangle, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import axios from 'axios'

interface DuplicateFile {
  id: number
  name: string
  path: string
  size: number
  size_formatted: string
  is_primary: boolean
  is_deleted: boolean
}

interface DuplicateGroup {
  id: number
  hash: string
  size: number
  size_formatted: string
  file_count: number
  total_size: number
  total_size_formatted: string
  files: DuplicateFile[]
}

const Duplicates: React.FC = () => {
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set())
  const [deletingFiles, setDeletingFiles] = useState<Set<number>>(new Set())

  useEffect(() => {
    fetchDuplicates()
  }, [])

  const fetchDuplicates = async () => {
    try {
      setLoading(true)
      const response = await axios.get('/api/duplicates')
      setDuplicates(response.data.duplicates)
    } catch (error) {
      console.error('Error fetching duplicates:', error)
    } finally {
      setLoading(false)
    }
  }

  const toggleGroup = (groupId: number) => {
    const newExpanded = new Set(expandedGroups)
    if (newExpanded.has(groupId)) {
      newExpanded.delete(groupId)
    } else {
      newExpanded.add(groupId)
    }
    setExpandedGroups(newExpanded)
  }

  const deleteFile = async (groupId: number, fileId: number) => {
    if (!confirm('Are you sure you want to delete this duplicate file? This action cannot be undone.')) {
      return
    }

    try {
      setDeletingFiles(prev => new Set(prev).add(fileId))
      await axios.post(`/api/duplicates/${groupId}/delete/${fileId}`)
      await fetchDuplicates() // Refresh the list
    } catch (error) {
      console.error('Error deleting duplicate file:', error)
      alert('Failed to delete file. Please try again.')
    } finally {
      setDeletingFiles(prev => {
        const newSet = new Set(prev)
        newSet.delete(fileId)
        return newSet
      })
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
            Duplicates
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Find and manage duplicate files
          </p>
        </div>
        
        <button
          onClick={fetchDuplicates}
          className="btn btn-secondary px-4 py-2"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Duplicates List */}
      {duplicates.length === 0 ? (
        <div className="card p-8 text-center">
          <AlertTriangle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No duplicates found
          </h3>
          <p className="text-gray-600 dark:text-gray-400">
            Run a scan to detect duplicate files in your storage.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {duplicates.map((group) => (
            <div key={group.id} className="card p-4">
              {/* Group Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <button
                    onClick={() => toggleGroup(group.id)}
                    className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {expandedGroups.has(group.id) ? (
                      <ChevronDown className="h-5 w-5" />
                    ) : (
                      <ChevronRight className="h-5 w-5" />
                    )}
                  </button>
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-white">
                      {group.file_count} duplicate files
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Hash: {group.hash.substring(0, 16)}...
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    {group.total_size_formatted}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {group.size_formatted} each
                  </p>
                </div>
              </div>

              {/* Group Files */}
              {expandedGroups.has(group.id) && (
                <div className="mt-4 space-y-2">
                  {group.files.map((file) => (
                    <div
                      key={file.id}
                      className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-md"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {file.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {file.path}
                        </p>
                      </div>
                      <div className="flex items-center space-x-3">
                        <span className="text-sm text-gray-500 dark:text-gray-400">
                          {file.size_formatted}
                        </span>
                        {file.is_primary && (
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                            Primary
                          </span>
                        )}
                        {!file.is_deleted && (
                          <button
                            onClick={() => deleteFile(group.id, file.id)}
                            disabled={deletingFiles.has(file.id)}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50"
                            title="Delete duplicate"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                        {file.is_deleted && (
                          <span className="text-xs text-gray-400">Deleted</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default Duplicates 