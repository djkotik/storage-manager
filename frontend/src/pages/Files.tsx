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
}

interface FileTree {
  tree: FileItem[]
}

const Files: React.FC = () => {
  const [fileTree, setFileTree] = useState<FileItem[]>([])
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)

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

  const toggleFolder = (folderPath: string) => {
    const newExpanded = new Set(expandedFolders)
    if (newExpanded.has(folderPath)) {
      newExpanded.delete(folderPath)
    } else {
      newExpanded.add(folderPath)
    }
    setExpandedFolders(newExpanded)
  }

  const renderFileItem = (item: FileItem, level: number = 0) => {
    const isExpanded = expandedFolders.has(item.path)
    const hasChildren = item.children && item.children.length > 0

    return (
      <div key={item.id} className="select-none">
        <div
          className={`flex items-center py-1 px-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer ${
            selectedFile?.id === item.id ? 'bg-blue-100 dark:bg-blue-900' : ''
          }`}
          style={{ paddingLeft: `${level * 20 + 8}px` }}
          onClick={() => {
            if (item.is_directory) {
              toggleFolder(item.path)
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
                  toggleFolder(item.path)
                }}
              >
                {isExpanded ? (
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
          
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {item.size_formatted}
          </span>
        </div>
        
        {item.is_directory && isExpanded && hasChildren && (
          <div>
            {item.children!.map(child => renderFileItem(child, level + 1))}
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
            Files
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Browse your storage structure
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