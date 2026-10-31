import React, { useState, useCallback } from 'react'
import { 
  Search, Download, Loader2, CheckCircle, AlertCircle, 
  Info, FileText, Zap, Globe, ExternalLink
} from 'lucide-react'
import axios from 'axios'

const API_BASE = '/api'

// Types
interface EpisodeInfo {
  title: string
  url: string
  season: number | null
  episode: number | null
  language: 'sub' | 'dub' | 'all'
  quality: string
}

interface VideoSource {
  quality: string
  url: string
  type: string
}

interface EpisodeDownloadInfo {
  episode: EpisodeInfo
  video_sources: VideoSource[]
  error: string | null
}

interface AnimeInfo {
  title: string
  cover_url: string | null
  description: string | null
  genres: string[]
  episodes: EpisodeInfo[]
  total_episodes: number
}

interface DownloadResult {
  job_id: string
  download_url: string
  files: Record<string, { filename: string; url: string }>
}

function App() {
  // State
  const [url, setUrl] = useState('')
  const [language, setLanguage] = useState<'sub' | 'dub' | 'all'>('sub')
  const [season, setSeason] = useState<'all' | '1' | '2' | '3'>('all')
  
  const [animeInfo, setAnimeInfo] = useState<AnimeInfo | null>(null)
  const [episodes, setEpisodes] = useState<EpisodeDownloadInfo[]>([])
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())
  
  const [scrapingStatus, setScrapingStatus] = useState<'idle' | 'anime' | 'episodes' | 'done' | 'error'>('idle')
  const [scrapingProgress, setScrapingProgress] = useState(0)
  const [scrapingError, setScrapingError] = useState<string | null>(null)
  
  const [downloadResult, setDownloadResult] = useState<DownloadResult | null>(null)
  const [generatingDownloads, setGeneratingDownloads] = useState(false)

  // API calls
  const scrapeAnime = useCallback(async () => {
    if (!url.trim()) return
    
    setScrapingStatus('anime')
    setScrapingProgress(0)
    setScrapingError(null)
    setAnimeInfo(null)
    setEpisodes([])
    setSelectedEpisodes(new Set())
    setDownloadResult(null)
    
    try {
      const response = await axios.post(`${API_BASE}/scrape`, {
        url,
        language,
        season
      })
      setAnimeInfo(response.data)
      setScrapingStatus('done')
      setScrapingProgress(100)
    } catch (err: any) {
      setScrapingError(err.response?.data?.detail || err.message)
      setScrapingStatus('error')
    }
  }, [url, language, season])

  const scrapeEpisodes = useCallback(async () => {
    if (!animeInfo) return
    
    setScrapingStatus('episodes')
    setScrapingProgress(0)
    setScrapingError(null)
    
    try {
      const response = await axios.post(`${API_BASE}/scrape/episodes`, {
        url,
        language,
        season
      })
      
      const episodesData = response.data
      setEpisodes(episodesData)
      
      // Select all by default
      const allSelected = new Set<number>(episodesData.map((_: any, i: number) => i))
      setSelectedEpisodes(allSelected)
      
      setScrapingStatus('done')
      setScrapingProgress(100)
    } catch (err: any) {
      setScrapingError(err.response?.data?.detail || err.message)
      setScrapingStatus('error')
    }
  }, [animeInfo, url, language, season])

  const handleScrape = useCallback(async () => {
    await scrapeAnime()
    if (animeInfo || !scrapingError) {
      await scrapeEpisodes()
    }
  }, [scrapeAnime, scrapeEpisodes, animeInfo, scrapingError])

  const toggleEpisodeSelection = (index: number) => {
    const newSelected = new Set(selectedEpisodes)
    if (newSelected.has(index)) {
      newSelected.delete(index)
    } else {
      newSelected.add(index)
    }
    setSelectedEpisodes(newSelected)
  }

  const toggleSelectAll = () => {
    if (selectedEpisodes.size === episodes.length) {
      setSelectedEpisodes(new Set())
    } else {
      setSelectedEpisodes(new Set(episodes.map((_, i) => i)))
    }
  }

  const generateDownloads = async () => {
    const selected = episodes.filter((_, i) => selectedEpisodes.has(i))
    if (selected.length === 0) return
    
    setGeneratingDownloads(true)
    try {
      const response = await axios.post(`${API_BASE}/generate-downloads`, {
        episodes: selected,
        format: 'all'
      })
      setDownloadResult(response.data)
    } catch (err: any) {
      alert('Failed to generate downloads: ' + (err.response?.data?.detail || err.message))
    } finally {
      setGeneratingDownloads(false)
    }
  }

  const downloadAll = () => {
    if (!downloadResult) return
    window.open(`${API_BASE}/download/${downloadResult.job_id}/zip`, '_blank')
  }

  const formatTypeLabels: Record<string, { name: string; desc: string; icon: React.ReactNode }> = {
    idm: { name: 'IDM (Internet Download Manager)', desc: 'Text file for IDM batch import', icon: <Zap size={24} /> },
    ab_downloader: { name: 'AB Downloader', desc: '.lst format for AB Downloader', icon: <Download size={24} /> },
    aria2: { name: 'Aria2', desc: 'Input file for aria2c', icon: <FileText size={24} /> },
    txt: { name: 'Simple Text', desc: 'One URL per line', icon: <FileText size={24} /> },
    m3u: { name: 'M3U Playlist', desc: 'For media players (VLC, MPV)', icon: <Globe size={24} /> }
  }

  const getLanguageBadge = (lang: string) => (
    <span className={`badge badge-${lang}`}>{lang.toUpperCase()}</span>
  )

  const getBestSource = (sources: VideoSource[]) => {
    if (!sources.length) return null
    const qualityOrder: Record<string, number> = { '1080p': 0, '720p': 1, '480p': 2, 'Auto': 3 }
    const typeOrder: Record<string, number> = { 'direct': 0, 'm3u8': 1, 'embed': 2 }
    return [...sources].sort((a, b) => 
      (qualityOrder[a.quality] || 99) - (qualityOrder[b.quality] || 99) ||
      (typeOrder[a.type] || 99) - (typeOrder[b.type] || 99)
    )[0]
  }

  return (
    <div className="container" style={{ paddingTop: '32px', paddingBottom: '32px' }}>
      {/* Header */}
      <header style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <Zap size={32} style={{ color: 'var(--accent)' }} />
          <h1 style={{ fontSize: '28px', fontWeight: '600' }}>Wcoflix Downloader</h1>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
          Generate batch download links for IDM, AB Downloader, Aria2, and more
        </p>
      </header>

      {/* Input Form */}
      <section className="card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '20px' }}>
          Anime URL
        </h2>
        
        <div className="form-group">
          <label className="label" htmlFor="anime-url">Wcoflix Anime URL</label>
          <div style={{ display: 'flex', gap: '12px' }}>
            <input
              id="anime-url"
              type="url"
              className="input"
              placeholder="https://www.wcoflix.tv/anime/the-apothecary-diaries/?season=all&lang=sub"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleScrape()}
              style={{ flex: 1 }}
            />
            <button
              className="btn btn-primary"
              onClick={handleScrape}
              disabled={scrapingStatus !== 'idle' && scrapingStatus !== 'done' || !url.trim()}
              style={{ minWidth: '140px' }}
            >
              {scrapingStatus === 'anime' || scrapingStatus === 'episodes' ? (
                <>
                  <Loader2 className="spinner" />
                  Scraping...
                </>
              ) : (
                <>
                  <Search size={18} />
                  Scrape Episodes
                </>
              )}
            </button>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="label" htmlFor="language">Language</label>
            <select
              id="language"
              className="select"
              value={language}
              onChange={(e) => setLanguage(e.target.value as 'sub' | 'dub' | 'all')}
            >
              <option value="sub">Subbed (Japanese + Subtitles)</option>
              <option value="dub">Dubbed (English Audio)</option>
              <option value="all">All Languages</option>
            </select>
          </div>
          
          <div className="form-group">
            <label className="label" htmlFor="season">Season</label>
            <select
              id="season"
              className="select"
              value={season}
              onChange={(e) => setSeason(e.target.value as 'all' | '1' | '2' | '3')}
            >
              <option value="all">All Seasons</option>
              <option value="1">Season 1</option>
              <option value="2">Season 2</option>
              <option value="3">Season 3</option>
            </select>
          </div>
        </div>

        {scrapingError && (
          <div className="alert alert-error">
            <AlertCircle size={20} />
            <span>{scrapingError}</span>
          </div>
        )}
      </section>

      {/* Anime Info & Episode List */}
      {animeInfo && (
        <section className="card" style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '8px' }}>
                {animeInfo.title}
              </h2>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', color: 'var(--text-secondary)', fontSize: '14px' }}>
                {animeInfo.genres.slice(0, 6).map((genre) => (
                  <span key={genre} className="badge badge-sub" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                    {genre}
                  </span>
                ))}
                {animeInfo.genres.length > 6 && (
                  <span className="badge" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                    +{animeInfo.genres.length - 6} more
                  </span>
                )}
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="btn btn-secondary"
                onClick={scrapeEpisodes}
                disabled={scrapingStatus === 'episodes'}
              >
                <Loader2 size={18} className={scrapingStatus === 'episodes' ? 'spinner' : ''} />
                Re-scan Episodes
              </button>
            </div>
          </div>

          {scrapingStatus === 'episodes' && (
            <div style={{ marginBottom: '16px' }}>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: `${scrapingProgress}%` }} />
              </div>
              <p style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px', marginTop: '8px' }}>
                Extracting video sources from {episodes.length} episodes...
              </p>
            </div>
          )}

          {/* Episode Selection Controls */}
          {episodes.length > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
                  <input
                    type="checkbox"
                    checked={selectedEpisodes.size === episodes.length && episodes.length > 0}
                    onChange={toggleSelectAll}
                    style={{ width: '16px', height: '16px', accentColor: 'var(--accent)' }}
                  />
                  Select All ({episodes.length} episodes)
                </label>
                <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                  {selectedEpisodes.size} selected
                </span>
              </div>
              
              <button
                className="btn btn-success"
                onClick={generateDownloads}
                disabled={generatingDownloads || selectedEpisodes.size === 0}
                style={{ minWidth: '200px' }}
              >
                {generatingDownloads ? (
                  <>
                    <Loader2 className="spinner" />
                    Generating Download Files...
                  </>
                ) : (
                  <>
                    <Download size={18} />
                    Generate Download Files ({selectedEpisodes.size} episodes)
                  </>
                )}
              </button>
            </div>
          )}

          {/* Episode List */}
          <div className="episode-list">
            {episodes.map((epInfo, index) => (
              <div
                key={index}
                className={`episode-item ${epInfo.error ? 'error' : ''}`}
                style={{ opacity: selectedEpisodes.has(index) ? 1 : 0.6 }}
              >
                <input
                  type="checkbox"
                  checked={selectedEpisodes.has(index)}
                  onChange={() => toggleEpisodeSelection(index)}
                  style={{ width: '18px', height: '18px', accentColor: 'var(--accent)', flexShrink: 0 }}
                />
                
                <div className="episode-info" style={{ flex: 1, minWidth: 0 }}>
                  <div className="episode-title">
                    {epInfo.episode.title}
                    {epInfo.episode.season && epInfo.episode.episode && (
                      <span style={{ marginLeft: '8px', color: 'var(--text-secondary)', fontWeight: '400' }}>
                        S{epInfo.episode.season}E{String(epInfo.episode.episode).padStart(2, '0')}
                      </span>
                    )}
                  </div>
                  <div className="episode-meta">
                    <span>{getLanguageBadge(epInfo.episode.language)}</span>
                    <span>{epInfo.episode.quality}</span>
                    {epInfo.error && (
                      <span style={{ color: 'var(--error)' }}>
                        <AlertCircle size={14} /> {epInfo.error}
                      </span>
                    )}
                  </div>
                </div>

                <div className="episode-sources">
                  {epInfo.video_sources.map((source, si) => {
                    const best = getBestSource(epInfo.video_sources)
                    const isBest = best && source.url === best.url
                    return (
                      <span key={si} className={`source-badge ${isBest ? 'best' : ''}`}>
                        {source.quality} ({source.type})
                      </span>
                    )
                  })}
                  {epInfo.video_sources.length === 0 && !epInfo.error && (
                    <span className="source-badge" style={{ color: 'var(--warning)' }}>
                      No sources found
                    </span>
                  )}
                </div>
              </div>
            ))}
            
            {episodes.length === 0 && scrapingStatus === 'done' && (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
                <Info size={48} style={{ marginBottom: '16px', opacity: 0.5 }} />
                <p>No episodes found. Try changing the language or season filter.</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Download Results */}
      {downloadResult && (
        <section className="card" style={{ marginBottom: '24px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '20px' }}>
            <CheckCircle size={20} style={{ color: 'var(--success)', marginRight: '8px', verticalAlign: 'middle' }} />
            Download Files Ready
          </h2>
          
          <div className="download-options">
            {Object.entries(downloadResult.files).map(([key, file]) => {
              const info = formatTypeLabels[key]
              return (
                <a
                  key={key}
                  href={file.url}
                  className="download-option"
                  download
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <div className="download-option-icon" style={{ color: 'var(--accent)' }}>
                    {info.icon}
                  </div>
                  <span className="download-option-name">{info.name}</span>
                  <span className="download-option-desc">{info.desc}</span>
                </a>
              )
            })}
          </div>

          <div style={{ marginTop: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={downloadAll}>
              <Download size={18} />
              Download All as ZIP
            </button>
            <a
              href={downloadResult.files.idm?.url || '#'}
              className="btn btn-secondary"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink size={18} />
              Open IDM File Directly
            </a>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer className="footer">
        <p>
          Wcoflix Downloader v1.0.0 • 
          <a href="https://github.com/mzmarkib/wcoflix-downlaoder" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
            GitHub
          </a>
          • 
          <span style={{ color: 'var(--warning)' }}>Note: Cloudflare protection may block automated scraping. Use residential proxies for best results.</span>
        </p>
      </footer>
    </div>
  )
}

export default App