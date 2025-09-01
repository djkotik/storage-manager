import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Files from './pages/Files'
import Media from './pages/Media'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import Duplicates from './pages/Duplicates'
import LargestFiles from './pages/LargestFiles'

function App() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/files" element={<Files />} />
          <Route path="/media" element={<Media />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/largest-files" element={<LargestFiles />} />
          <Route path="/duplicates" element={<Duplicates />} />
        </Routes>
      </Layout>
    </div>
  )
}

export default App 