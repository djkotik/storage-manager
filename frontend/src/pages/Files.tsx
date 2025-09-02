import React, { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { ChevronRight, ChevronDown, Folder, File, HardDrive, Trash2, FileText, Image, Film, Music, Archive, Code } from 'lucide-react'
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
  elapsed_time_formatted?: string
  skip_appdata?: boolean
  appdata_inclusion_changed?: boolean
}

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
  file_count?: number
}

interface FileTree {
  tree: FileItem[]
}

const getFileIcon = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase()
  
  switch (ext) {
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'bmp':
    case 'svg':
    case 'webp':
      return <Image className="h-4 w-4 text-blue-500" />
    case 'mp4':
    case 'avi':
    case 'mkv':
    case 'mov':
    case 'wmv':
    case 'flv':
    case 'webm':
      return <Film className="h-4 w-4 text-purple-500" />
    case 'mp3':
    case 'wav':
    case 'flac':
    case 'aac':
    case 'ogg':
      return <Music className="h-4 w-4 text-green-500" />
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return <Archive className="h-4 w-4 text-orange-500" />
    case 'txt':
    case 'pdf':
    case 'doc':
    case 'docx':
      return <FileText className="h-4 w-4 text-red-500" />
    case 'js':
    case 'ts':
    case 'py':
    case 'cpp':
    case 'java':
      return <Code className="h-4 w-4 text-yellow-500" />
    default:
      return <File className="h-4 w-4 text-gray-500" />
  }
}

const Files: React.FC = () => {
  const location = useLocation()
  const [fileTree, setFileTree] = useState<FileItem[]>([])
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)
  const [loadingChildren, setLoadingChildren] = useState<Set<number>>(new Set())
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [scanStatus, setScanStatus] = useState<ScanStatus>({ status: 'idle', scanning: false })
  const [maxItemsPerFolder, setMaxItemsPerFolder] = useState<string>('100')

  useEffect(() => {
    fetchFileTree()
    fetchScanStatus()
    fetchSettings()
    // Poll scan status every 5 seconds
    const interval = setInterval(fetchScanStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  // Handle expand parameter from URL
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search)
    const expandPath = searchParams.get('expand')
    
    if (expandPath && fileTree.length > 0) {
      console.log('URL expand parameter detected:', expandPath)
      console.log('Current file tree:', fileTree)
      // Auto-expand the folder path
      autoExpandPath(expandPath)
    }
  }, [location.search, fileTree])

  const autoExpandPath = async (targetPath: string) => {
    try {
      console.log('Auto-expanding path:', targetPath)
      
      // Find the target path in the file tree and expand it
      const expandPathRecursively = async (items: FileItem[], currentPath: string = ''): Promise<boolean> => {
        for (const item of items) {
          const itemPath = currentPath ? `${currentPath}/${item.name}` : item.name
          
          console.log('Checking item:', item.name, 'path:', itemPath, 'target:', targetPath)
          
          // Normalize paths for comparison (remove leading/trailing slashes and normalize separators)
          const normalizePath = (path: string) => path.replace(/^\/+|\/+$/g, '').replace(/\\/g, '/')
          const normalizedItemPath = normalizePath(itemPath)
          const normalizedItemDbPath = normalizePath(item.path)
          const normalizedTargetPath = normalizePath(targetPath)
          
          console.log('Path comparison:', {
            normalizedItemPath,
            normalizedItemDbPath,
            normalizedTargetPath,
            itemPath,
            itemPath: item.path,
            targetPath
          })
          
          // Check multiple path formats for better matching
          if (normalizedItemPath === normalizedTargetPath || 
              normalizedItemDbPath === normalizedTargetPath ||
              normalizedItemPath.endsWith(normalizedTargetPath) ||
              normalizedItemDbPath.endsWith(normalizedTargetPath) ||
              normalizedTargetPath.endsWith(normalizedItemPath) ||
              normalizedTargetPath.endsWith(normalizedItemDbPath)) {
            
            console.log('Found matching path:', item.path)
            
            // Found the target path, expand it
            if (item.is_directory && !expandedFolders.has(item.id.toString())) {
              console.log('Expanding directory:', item.name)
              await fetchDirectoryChildren(item.id, item.path)
              setExpandedFolders(prev => new Set(prev).add(item.id.toString()))
            }
            return true
          }
          
          // Recursively search in children
          if (item.children && item.is_directory) {
            if (await expandPathRecursively(item.children, itemPath)) {
              // If found in children, expand the parent
              if (!expandedFolders.has(item.id.toString())) {
                console.log('Expanding parent directory:', item.name)
                await fetchDirectoryChildren(item.id, item.path)
                setExpandedFolders(prev => new Set(prev).add(item.id.toString()))
              }
              return true
            }
          }
        }
        return false
      }
      
      const result = await expandPathRecursively(fileTree)
      if (!result) {
        console.log('Path not found in tree, attempting alternative search')
        // Try to find by partial path matching
        await findAndExpandByPartialPath(targetPath)
      }
    } catch (error) {
      console.error('Error auto-expanding path:', error)
    }
  }

  const findAndExpandByPartialPath = async (targetPath: string) => {
    try {
      // Extract the parent directory path from the target path
      const parentDir = targetPath.split('/').slice(0, -1).join('/')
      console.log('Looking for parent directory:', parentDir)
      
      // Search for directories that contain the parent path
      const searchRecursively = async (items: FileItem[]): Promise<boolean> => {
        for (const item of items) {
          if (item.is_directory) {
            // Normalize paths for comparison
            const normalizePath = (path: string) => path.replace(/^\/+|\/+$/g, '').replace(/\\/g, '/')
            const normalizedItemPath = normalizePath(item.path)
            const normalizedParentDir = normalizePath(parentDir)
            
            console.log('Partial path comparison:', {
              normalizedItemPath,
              normalizedParentDir,
              itemPath: item.path,
              parentDir
            })
            
            if (normalizedItemPath === normalizedParentDir || 
                normalizedItemPath.endsWith(normalizedParentDir) || 
                normalizedParentDir.endsWith(normalizedItemPath)) {
              console.log('Found parent directory by partial match:', item.path)
              if (!expandedFolders.has(item.id.toString())) {
                await fetchDirectoryChildren(item.id, item.path)
                setExpandedFolders(prev => new Set(prev).add(item.id.toString()))
              }
              return true
            }
            
            if (item.children) {
              if (await searchRecursively(item.children)) {
                if (!expandedFolders.has(item.id.toString())) {
                  await fetchDirectoryChildren(item.id, item.path)
                  setExpandedFolders(prev => new Set(prev).add(item.id.toString()))
                }
                return true
              }
            }
          }
        }
        return false
      }
      
      await searchRecursively(fileTree)
    } catch (error) {
      console.error('Error in partial path search:', error)
    }
  }

  const fetchScanStatus = async () => {
    try {
      const response = await axios.get('/api/scan/status')
      setScanStatus(response.data)
    } catch (error) {
      console.error('Error fetching scan status:', error)
    }
  }

  const fetchSettings = async () => {
    try {
      const response = await axios.get('/api/settings')
      setMaxItemsPerFolder(response.data.max_items_per_folder || '100')
    } catch (error) {
      console.error('Error fetching settings:', error)
    }
  }

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
      
      // Update the file tree to include the children (both files and directories)
      setFileTree(prevTree => {
        const updateTree = (items: FileItem[]): FileItem[] => {
          return items.map(item => {
            if (item.id === directoryId) {
              return {
                ...item,
                children: response.data.children
              }
            }
            // Recursively update nested children
            if (item.children) {
              return {
                ...item,
                children: updateTree(item.children)
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

  const toggleFolder = async (item: FileItem) => {
    const isExpanded = expandedFolders.has(item.id.toString())
    const newExpanded = new Set(expandedFolders)
    
    if (isExpanded) {
      newExpanded.delete(item.id.toString())
    } else {
      newExpanded.add(item.id.toString())
      // Fetch children if not already loaded
      if (!item.children || item.children.length === 0) {
        await fetchDirectoryChildren(item.id, item.path)
      }
    }
    setExpandedFolders(newExpanded)
  }

  const handleDelete = async () => {
    if (!selectedFile) return
    
    try {
      setDeleting(true)
      await axios.post(`/api/files/${selectedFile.id}/delete`)
      
      // Remove the deleted item from the tree
      setFileTree(prevTree => {
        const removeFromTree = (items: FileItem[]): FileItem[] => {
          return items.filter(item => {
            if (item.id === selectedFile.id) {
              return false
            }
            if (item.children) {
              item.children = removeFromTree(item.children)
            }
            return true
          })
        }
        return removeFromTree(prevTree)
      })
      
      setSelectedFile(null)
      setShowDeleteConfirm(false)
      
      // Show success message
      alert(`Successfully deleted ${selectedFile.name}`)
      
    } catch (error) {
      console.error('Error deleting file:', error)
      alert('Failed to delete file. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const renderFileItem = (item: FileItem, level: number = 0) => {
    const isExpanded = expandedFolders.has(item.id.toString())
    const hasChildren = item.children && item.children.length > 0
    const isLoading = loadingChildren.has(item.id)

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
            <div className="ml-6 mr-2">
              {getFileIcon(item.name)}
            </div>
          )}
          
          <span 
            className="flex-1 text-sm font-medium text-gray-900 dark:text-white truncate"
            title={`${item.name} (${item.path})`}
          >
            {item.name}
          </span>
          
          <span className="text-xs text-gray-500 dark:text-gray-400 mr-2">
            {item.size_formatted}
          </span>
          
          {item.file_count && item.is_directory && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({item.file_count} files)
            </span>
          )}
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
              {maxItemsPerFolder !== '100' && ` - Limited to ${maxItemsPerFolder} largest items per folder as per Settings`}
            </h3>

            {/* Scan Status Indicator */}
            {scanStatus.scanning ? (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 dark:bg-blue-900/20 dark:border-blue-800">
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    Scan in progress... Directory structure updates as files are discovered.
                  </p>
                </div>
              </div>
            ) : (
              (scanStatus.status === 'idle' || scanStatus.status === 'completed') && scanStatus.start_time && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 dark:bg-green-900/20 dark:border-green-800">
                  <p className="text-sm text-green-800 dark:text-green-200">
                    ✅ Showing structure from latest scan (started {new Date(scanStatus.start_time).toLocaleString()})
                  </p>
                </div>
              )
            )}
            
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
          <div className="card p-6 sticky top-4">
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
                
                {selectedFile.file_count && selectedFile.is_directory && (
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
                
                {/* Delete Button */}
                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={deleting}
                    className="btn btn-danger w-full flex items-center justify-center"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    {deleting ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
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

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && selectedFile && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Confirm Delete
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to delete "{selectedFile.name}"? This action cannot be undone.
            </p>
            <div className="flex space-x-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="btn btn-secondary flex-1"
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="btn btn-danger flex-1"
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Files 