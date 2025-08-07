import React, { useState, useEffect } from 'react'
import { ChevronRight, ChevronDown, Folder, File, HardDrive } from 'lucide-react'
import axios from 'axios'

interface FileItem {
  id: number
  path: string
  name: string
  size: number
  size_formatted: string
  is_directory: boolean
  extension?: string
  modified_time?: string
  permissions?: string
  children?: FileItem[]
  files?: FileItem[]
  file_count?: number
}

interface FileTree {
  tree: FileItem[]
}

const Files: React.FC = () => {
  const [fileTree, setFileTree] = useState<FileItem[]>([])
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)
  const [loadingChildren, setLoadingChildren] = useState<Set<number>>(new Set())
  const [loadingFiles, setLoadingFiles] = useState<Set<number>>(new Set())

  useEffect(() => {
    fetchFileTree()
  }, [])

  const fetchFileTree = async () => {
    try {
      setLoading(true)
      const response = await axios.get('/api/files/tree')
      setFileTree(response.data.tree)
    } catch (error) {
      console.error('Error fetching file tree:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchDirectoryChildren = async (directoryId: number, directoryPath: string) => {
    try {
      setLoadingChildren(prev => new Set(prev).add(directoryId))
      const response = await axios.get(`/api/files/tree/${directoryId}`)
      
      // Update the file tree to include the children
      setFileTree(prevTree => {
        const updateTree = (items: FileItem[]): FileItem[] => {
          return items.map(item => {
            if (item.id === directoryId) {
              return {
                ...item,
                children: response.data.children
              }
            }
            return item
          })
        }
        return updateTree(prevTree)
      })
    } catch (error) {
      console.error('Error fetching directory children:', error)
    } finally {
      setLoadingChildren(prev => {
        const newSet = new Set(prev)
        newSet.delete(directoryId)
        return newSet
      })
    }
  }

  const fetchDirectoryFiles = async (directoryId: number, directoryPath: string) => {
    try {
      setLoadingFiles(prev => new Set(prev).add(directoryId))
      const response = await axios.get(`/api/files/tree/${directoryId}/files`)
      
      // Update the file tree to include the files
      setFileTree(prevTree => {
        const updateTree = (items: FileItem[]): FileItem[] => {
          return items.map(item => {
            if (item.id === directoryId) {
              return {
                ...item,
                files: response.data.files
              }
            }
            return item
          })
        }
        return updateTree(prevTree)
      })
    } catch (error) {
      console.error('Error fetching directory files:', error)
    } finally {
      setLoadingFiles(prev => {
        const newSet = new Set(prev)
        newSet.delete(directoryId)
        return newSet
      })
    }
  }

  const toggleFolder = async (item: FileItem) => {
    const isExpanded = expandedFolders.has(item.path)
    const newExpanded = new Set(expandedFolders)
    
    if (isExpanded) {
      newExpanded.delete(item.path)
    } else {
      newExpanded.add(item.path)
      // Fetch children if not already loaded
      if (!item.children || item.children.length === 0) {
        await fetchDirectoryChildren(item.id, item.path)
      }
      // Fetch files if not already loaded
      if (!item.files || item.files.length === 0) {
        await fetchDirectoryFiles(item.id, item.path)
      }
    }
    setExpandedFolders(newExpanded)
  }

  const renderFileItem = (item: FileItem, level: number = 0) => {
    const isExpanded = expandedFolders.has(item.path)
    const hasChildren = item.children && item.children.length > 0
    const hasFiles = item.files && item.files.length > 0
    const isLoading = loadingChildren.has(item.id)
    const isLoadingFiles = loadingFiles.has(item.id)

    return (
      <div key={item.id} className="select-none">
        <div
          className={`flex items-center py-1 px-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer ${
            selectedFile?.id === item.id ? 'bg-blue-100 dark:bg-blue-900' : ''
          }`}
          style={{ paddingLeft: `${level * 20 + 8}px` }}
          onClick={() => {
            if (item.is_directory) {
              toggleFolder(item)
            } else {
              setSelectedFile(item)
            }
          }}
        >
          {item.is_directory ? (
            <>
              <button
                className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                onClick={(e) => {
                  e.stopPropagation()
                  toggleFolder(item)
                }}
              >
                {isLoading ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                ) : isExpanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </button>
              <Folder className="h-4 w-4 text-blue-500 mr-2" />
            </>
          ) : (
            <File className="h-4 w-4 text-gray-500 mr-2 ml-6" />
          )}
          
          <span className="flex-1 text-sm font-medium text-gray-900 dark:text-white">
            {item.name}
          </span>
          
          <span className="text-xs text-gray-500 dark:text-gray-400 mr-2">
            {item.size_formatted}
          </span>
          
          {item.file_count && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({item.file_count} files)
            </span>
          )}
        </div>
        
        {item.is_directory && isExpanded && (
          <div>
            {/* Show loading indicator for files */}
            {isLoadingFiles && (
              <div className="flex items-center py-1 px-2" style={{ paddingLeft: `${(level + 1) * 20 + 8}px` }}>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Loading files...</span>
              </div>
            )}
            
            {/* Show files */}
            {hasFiles && item.files!.map(file => renderFileItem(file, level + 1))}
            
            {/* Show child directories */}
            {hasChildren && item.children!.map(child => renderFileItem(child, level + 1))}
          </div>
        )}
      </div>
    )
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
            Usage Explorer
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Explore your storage structure and space usage
          </p>
        </div>
        
        <button
          onClick={fetchFileTree}
          className="btn btn-secondary px-4 py-2"
        >
          <HardDrive className="h-4 w-4 mr-2" />
          Refresh
        </button>
      </div>

      {/* Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* File Tree */}
        <div className="lg:col-span-2">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Storage Structure
            </h3>
            
            {fileTree.length === 0 ? (
              <div className="text-center py-8">
                <Folder className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500 dark:text-gray-400">
                  No files found. Start a scan to populate the file tree.
                </p>
              </div>
            ) : (
              <div className="border border-gray-200 dark:border-gray-700 rounded-md">
                {fileTree.map(item => renderFileItem(item))}
              </div>
            )}
          </div>
        </div>

        {/* File Details */}
        <div className="lg:col-span-1">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              File Details
            </h3>
            
            {selectedFile ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Name</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {selectedFile.name}
                  </p>
                </div>
                
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Path</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white break-all">
                    {selectedFile.path}
                  </p>
                </div>
                
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Size</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {selectedFile.size_formatted}
                  </p>
                </div>
                
                {selectedFile.file_count && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Files</p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {selectedFile.file_count}
                    </p>
                  </div>
                )}
                
                {selectedFile.extension && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Extension</p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {selectedFile.extension}
                    </p>
                  </div>
                )}
                
                {selectedFile.modified_time && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Modified</p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {new Date(selectedFile.modified_time).toLocaleString()}
                    </p>
                  </div>
                )}
                
                {selectedFile.permissions && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Permissions</p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {selectedFile.permissions}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <File className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500 dark:text-gray-400">
                  Select a file to view details
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Files 