import React, { useState, useEffect } from 'react'
import { Search, Filter, Video, Film, Tv, Music } from 'lucide-react'
import axios from 'axios'

interface MediaFile {
  id: number
  file_id: number
  path: string
  name: string
  size: number
  size_formatted: string
  media_type: string
  title: string
  year: number
  season: number
  episode: number
  resolution: string
  video_codec: string
  audio_codec: string
  runtime: number
  file_format: string
}

const Media: React.FC = () => {
  const [mediaFiles, setMediaFiles] = useState<MediaFile[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [mediaType, setMediaType] = useState('')
  const [resolution, setResolution] = useState('')

  useEffect(() => {
    fetchMediaFiles()
  }, [currentPage, search, mediaType, resolution])

  const fetchMediaFiles = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        per_page: '50',
        title: search,
        type: mediaType,
        resolution,
      })

      const response = await axios.get(`/api/media/files?${params}`)
      setMediaFiles(response.data.media_files)
      setTotalPages(response.data.pages)
    } catch (error) {
      console.error('Error fetching media files:', error)
    } finally {
      setLoading(false)
    }
  }

  const getMediaIcon = (mediaType: string) => {
    switch (mediaType) {
      case 'movie':
        return <Film className="h-5 w-5 text-red-500" />
      case 'tv_show':
        return <Tv className="h-5 w-5 text-blue-500" />
      case 'music':
        return <Music className="h-5 w-5 text-green-500" />
      default:
        return <Video className="h-5 w-5 text-gray-500" />
    }
  }

  const formatRuntime = (minutes: number) => {
    if (!minutes) return '-'
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Media Files
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Manage your media library
        </p>
      </div>

      {/* Filters */}
      <div className="card p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Search
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search media..."
                className="input pl-10"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Type
            </label>
            <select
              value={mediaType}
              onChange={(e) => setMediaType(e.target.value)}
              className="input"
            >
              <option value="">All Types</option>
              <option value="movie">Movies</option>
              <option value="tv_show">TV Shows</option>
              <option value="music">Music</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Resolution
            </label>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              className="input"
            >
              <option value="">All Resolutions</option>
              <option value="4K">4K</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
            </select>
          </div>
        </div>
      </div>

      {/* Media Files Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded mb-3"></div>
              <div className="space-y-2">
                <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded"></div>
                <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
              </div>
            </div>
          ))
        ) : mediaFiles.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <Video className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">No media files found</p>
          </div>
        ) : (
          mediaFiles.map((media) => (
            <div key={media.id} className="card p-4 hover:shadow-lg transition-shadow">
              <div className="flex items-center justify-between mb-3">
                {getMediaIcon(media.media_type)}
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {media.file_format?.toUpperCase()}
                </span>
              </div>
              
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2 truncate">
                {media.title || media.name}
              </h3>
              
              <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
                {media.year && (
                  <p>Year: {media.year}</p>
                )}
                {media.season && media.episode && (
                  <p>S{media.season.toString().padStart(2, '0')}E{media.episode.toString().padStart(2, '0')}</p>
                )}
                {media.resolution && (
                  <p>Resolution: {media.resolution}</p>
                )}
                {media.video_codec && (
                  <p>Video: {media.video_codec}</p>
                )}
                {media.audio_codec && (
                  <p>Audio: {media.audio_codec}</p>
                )}
                {media.runtime && (
                  <p>Runtime: {formatRuntime(media.runtime)}</p>
                )}
                <p>Size: {media.size_formatted}</p>
              </div>
              
              <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 truncate">
                {media.path}
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