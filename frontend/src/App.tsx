import React, { useState, useCallback, useEffect } from 'react'
import { 
  Search, Download, Loader2, CheckCircle, AlertCircle, RefreshCw, 
  Info, FileText, Zap, Globe, ExternalLink, Settings, Wifi, WifiOff
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
  seasons: number[]
}

interface DownloadResult {
  job_id: string
  download_url: string
  files: Record<string, { filename: string; url: string }>
}

const PROXY_STORAGE_KEY = 'wcoflix_proxy_url'
const getStoredProxy = () => {
  if (typeof window !== 'undefined') {
    return sessionStorage.getItem(PROXY_STORAGE_KEY) || ''
  }
  return ''
}
const setStoredProxy = (url: string) => {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(PROXY_STORAGE_KEY, url)
  }
}

function App() {
  const [url, setUrl] = useState('')
  const [language, setLanguage] = useState<'sub' | 'dub' | 'all'>('sub')
  const [season, setSeason] = useState<string>('all')
  const [proxyUrl, setProxyUrl] = useState(() => getStoredProxy())
  const [showProxyInput, setShowProxyInput] = useState(false)
  const [proxyStatus, setProxyStatus] = useState<'unknown' | 'checking' | 'connected' | 'failed'>('unknown')
  
  const [animeInfo, setAnimeInfo] = useState<AnimeInfo | null>(null)
  const [episodes, setEpisodes] = useState<EpisodeDownloadInfo[]>([])
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())
  
  const [scrapingStatus, setScrapingStatus] = useState<'idle' | 'anime' | 'episodes' | 'done' | 'error'>('idle')
  const [scrapingProgress, setScrapingProgress] = useState(0)
  const [scrapingError, setScrapingError] = useState<string | null>(null)
  
  const [downloadResult, setDownloadResult] = useState<DownloadResult | null>(null)
  const [generatingDownloads, setGeneratingDownloads] = useState(false)

  const availableSeasons = animeInfo?.seasons || []
  const hasScraped = animeInfo !== null
  const hasMultipleSeasons = availableSeasons.length > 1
  const hasNoSeasons = hasScraped && availableSeasons.length === 0
  const hasSingleSeason = hasScraped && availableSeasons.length === 1

  useEffect(() => {
    setStoredProxy(proxyUrl)
  }, [proxyUrl])

  const testProxy = useCallback(async () => {
    if (!proxyUrl.trim()) {
      setProxyStatus('failed')
      return
    }
    setProxyStatus('checking')
    try {
      await axios.get(`${API_BASE}/health`, { timeout: 5000 })
      setProxyStatus('connected')
    } catch {
      setProxyStatus('unknown')
    }
  }, [proxyUrl])

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
        season,
        proxy_url: proxyUrl || undefined
      })
      setAnimeInfo(response.data)
      setScrapingStatus('done')
      setScrapingProgress(100)
    } catch (err: any) {
      setScrapingError(err.response?.data?.detail || err.message)
      setScrapingStatus('error')
    }
  }, [url, language, season, proxyUrl])

  const scrapeEpisodes = useCallback(async () => {
    if (!animeInfo) return
    
    setScrapingStatus('episodes')
    setScrapingProgress(0)
    setScrapingError(null)
    
    try {
      const response = await axios.post(`${API_BASE}/scrape/episodes`, {
        url,
        language,
        season,
        proxy_url: proxyUrl || undefined
      })
      
      const episodesData = response.data
      setEpisodes(episodesData)
      
      const allSelected = new Set<number>(episodesData.map((_: any, i: number) => i))
      setSelectedEpisodes(allSelected)
      
      setScrapingStatus('done')
      setScrapingProgress(100)
    } catch (err: any) {
      setScrapingError(err.response?.data?.detail || err.message)
      setScrapingStatus('error')
    }
  }, [animeInfo, url, language, season, proxyUrl])

  const handleScrape = useCallback(async () => {
    await scrapeAnime()
    if (animeInfo || !scrapingError) {
      await scrapeEpisodes()
    }
  }, [scrapeAnime, scrapeEpisodes, animeInfo, scrapingError]);

  const handleRescrape = useCallback(async () => {
    await scrapeEpisodes()
  }, [scrapeEpisodes]);

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
    React.createElement('span', { className: `badge badge-${lang}` }, lang.toUpperCase())
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

  const getSeasonFilterInfo = () => {
    if (season === 'all') return 'Showing all seasons'
    const seasonNum = parseInt(season)
    const filtered = episodes.filter(e => e.episode.season === seasonNum)
    return `Season ${seasonNum}: ${filtered.length} episodes`
  }

  // Render Proxy Settings section
  const renderProxySettings = () => (
    React.createElement('section', { className: 'card', style: { marginBottom: '24px' } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' } },
        React.createElement('h2', { style: { fontSize: '18px', fontWeight: '600' } }, 'Proxy Settings (Residential IP)'),
        React.createElement('button', { 
          className: 'btn btn-secondary btn-sm',
          onClick: () => setShowProxyInput(!showProxyInput)
        },
          React.createElement(Settings, { size: 16 }), ' ', showProxyInput ? 'Hide' : 'Configure'
        )
      ),
      showProxyInput && React.createElement('div', { style: { animation: 'slideDown 0.2s ease' } },
        React.createElement('div', { className: 'form-group' },
          React.createElement('label', { className: 'label', htmlFor: 'proxy-url' }, 'Proxy URL (HTTP/HTTPS)'),
          React.createElement('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
            React.createElement('input', {
              id: 'proxy-url',
              type: 'url',
              className: 'input',
              placeholder: 'https://abc123.ngrok-free.app or http://user:pass@host:port',
              value: proxyUrl,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setProxyUrl(e.target.value),
              style: { flex: 1, minWidth: '300px' }
            }),
            React.createElement('button', {
              className: 'btn btn-secondary',
              onClick: testProxy,
              disabled: !proxyUrl.trim() || proxyStatus === 'checking'
            },
              proxyStatus === 'checking' ? (
                React.createElement(Loader2, { className: 'spinner', size: 16 })
              ) : (
                React.createElement(React.Fragment, null,
                  React.createElement(Wifi, { size: 16 }), ' Test'
                )
              )
            )
          ),
          React.createElement('div', { style: { marginTop: '8px', fontSize: '12px', color: 'var(--text-secondary)' } },
            React.createElement('strong', null, 'Format: '), 
            React.createElement('code', null, 'http://host:port'), ' or ',
            React.createElement('code', null, 'http://user:pass@host:port'), ' or ',
            React.createElement('code', null, 'https://ngrok-url'),
            React.createElement('br', null),
            React.createElement('strong', null, 'Saved to: '), 'sessionStorage (persists until browser close)',
            React.createElement('br', null),
            React.createElement('strong', null, 'Current: '), proxyUrl || '<none>'
          ),
          React.createElement('div', { style: { marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' } },
            React.createElement('span', { style: { fontSize: '13px', color: 'var(--text-secondary)' } }, 'Status:'),
            React.createElement('span', { 
              className: `badge ${proxyStatus === 'connected' ? 'badge-success' : proxyStatus === 'checking' ? '' : proxyStatus === 'failed' ? 'badge-error' : 'badge'}` 
            },
              proxyStatus === 'connected' && React.createElement(Wifi, { size: 12 }),
              proxyStatus === 'checking' && React.createElement(Loader2, { className: 'spinner', size: 12 }),
              proxyStatus === 'failed' && React.createElement(WifiOff, { size: 12 }),
              proxyStatus.charAt(0).toUpperCase() + proxyStatus.slice(1)
            )
          )
        )
      )
    )
  )

  // Render Input Form section
  const renderInputForm = () => (
    React.createElement('section', { className: 'card', style: { marginBottom: '24px' } },
      React.createElement('h2', { style: { fontSize: '18px', fontWeight: '600', marginBottom: '20px' } }, 'Anime URL'),
      
      React.createElement('div', { className: 'form-group' },
        React.createElement('label', { className: 'label', htmlFor: 'anime-url' }, 'Wcoflix Anime URL'),
        React.createElement('div', { style: { display: 'flex', gap: '12px' } },
          React.createElement('input', {
            id: 'anime-url',
            type: 'url',
            className: 'input',
            placeholder: 'https://www.wcoflix.tv/anime/the-apothecary-diaries/?season=all&lang=sub',
            value: url,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setUrl(e.target.value),
            onKeyDown: (e: React.KeyboardEvent) => e.key === 'Enter' && handleScrape(),
            style: { flex: 1 }
          }),
          React.createElement('button', {
            className: 'btn btn-primary',
            onClick: handleScrape,
            disabled: scrapingStatus !== 'idle' && scrapingStatus !== 'done' || !url.trim(),
            style: { minWidth: '140px' }
          },
            scrapingStatus === 'anime' || scrapingStatus === 'episodes' ? (
              React.createElement(React.Fragment, null,
                React.createElement(Loader2, { className: 'spinner' }),
                ' Scraping...'
              )
            ) : (
              React.createElement(React.Fragment, null,
                React.createElement(Search, { size: 18 }),
                ' Scrape Episodes'
              )
            )
          )
        )
      ),

      React.createElement('div', { className: 'form-row' },
        React.createElement('div', { className: 'form-group' },
          React.createElement('label', { className: 'label', htmlFor: 'language' }, 'Language'),
          React.createElement('select', {
            id: 'language',
            className: 'select',
            value: language,
            onChange: (e: React.ChangeEvent<HTMLSelectElement>) => setLanguage(e.target.value as 'sub' | 'dub' | 'all')
          },
            React.createElement('option', { value: 'sub' }, 'Subbed (Japanese + Subtitles)'),
            React.createElement('option', { value: 'dub' }, 'Dubbed (English Audio)'),
            React.createElement('option', { value: 'all' }, 'All Languages')
          )
        ),
        
        React.createElement('div', { className: 'form-group' },
          React.createElement('label', { className: 'label', htmlFor: 'season' }, 'Season Filter'),
          !hasScraped
            ? React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
                React.createElement('select', {
                  id: 'season',
                  className: 'select',
                  value: season,
                  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => setSeason(e.target.value),
                  disabled: true
                },
                  React.createElement('option', { value: 'all' }, 'All Seasons (scrape first)')
                ),
                React.createElement('span', { className: 'badge badge-sub', style: { fontSize: '11px' } }, 'Scrape first')
              )
            : hasScraped
            ? React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: '4px' } },
                React.createElement('select', {
                  id: 'season',
                  className: 'select',
                  value: season,
                  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => setSeason(e.target.value),
                  disabled: !hasMultipleSeasons && !hasNoSeasons
                },
                  React.createElement('option', { value: 'all' }, 'All Seasons'),
                  hasMultipleSeasons && availableSeasons.map((s: number) => React.createElement('option', { key: s, value: String(s) }, `Season ${s}`)),
                  hasSingleSeason && React.createElement('option', { value: String(availableSeasons[0]) }, `Season ${availableSeasons[0]}`),
                  hasNoSeasons && React.createElement('option', { value: 'all' }, 'No seasons detected (use All Seasons)')
                ),
                hasMultipleSeasons && React.createElement('span', { style: { fontSize: '12px', color: 'var(--text-secondary)' } },
                  'Detected: ', availableSeasons.join(', ')
                ),
                hasNoSeasons && React.createElement('span', { className: 'badge badge-sub', style: { fontSize: '11px' } },
                  'No seasons in URLs \u2014 use "All Seasons"'
                ),
                hasSingleSeason && React.createElement('span', { style: { fontSize: '12px', color: 'var(--text-secondary)' } },
                  `Only Season ${availableSeasons[0]} detected`
                )
              )
            : null,
          React.createElement('div', { style: { marginTop: '8px', padding: '8px', background: 'var(--bg-primary)', borderRadius: '4px', fontSize: '12px', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' } },
            React.createElement('strong', null, 'How season filtering works: '), 
            'The season parameter is sent to wcoflix.tv as ',
            React.createElement('code', null, '?season=X&lang=Y'), '. ',
            'wcoflix.tv filters server-side. ',
            React.createElement('strong', null, 'If an anime has no season in episode URLs (e.g., Chibi Godzilla), '),
            'selecting a specific season returns empty \u2014 ',
            React.createElement('strong', null, 'always use "All Seasons" for those.')
          )
        )
      ),
      scrapingError
        ? React.createElement('div', { className: 'alert alert-error', style: { display: 'flex', flexDirection: 'column', gap: '8px' } },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
              React.createElement(AlertCircle, { size: 20 }),
              React.createElement('span', null, scrapingError)
            ),
            (!proxyUrl && scrapingError.toLowerCase().includes('cloudflare'))
              ? React.createElement('div', { className: 'alert', style: { background: 'rgba(210, 153, 34, 0.1)', borderColor: 'rgba(210, 153, 34, 0.3)', color: 'var(--warning)' } },
                  React.createElement('span', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
                    React.createElement(AlertCircle, { size: 18 }),
                    React.createElement('span', null, 'Cloudflare may be blocking requests. ', React.createElement('strong', null, 'Configure a residential proxy '), 'in Proxy Settings above for reliable scraping.')
                  )
                )
              : null,
            React.createElement('div', { style: { display: 'flex', gap: '8px' } },
              React.createElement('button', { className: 'btn btn-secondary btn-sm', onClick: handleScrape, disabled: scrapingStatus !== 'idle' && scrapingStatus !== 'done' },
                React.createElement(RefreshCw, { size: 16 }), ' Retry'
              ),
              hasScraped
                ? React.createElement('button', { className: 'btn btn-secondary btn-sm', onClick: handleRescrape, disabled: scrapingStatus === 'episodes' },
                    React.createElement(RefreshCw, { size: 16 }), ' Re-scan Episodes'
                  )
                : null
            )
          )
        : null
    )
  )

  // Render Anime Section
  const renderAnimeSection = () => {
    if (!animeInfo) return null
    
    return (
      React.createElement('section', { className: 'card', style: { marginBottom: '24px' } },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' } },
          React.createElement('div', null,
            React.createElement('h2', { style: { fontSize: '20px', fontWeight: '600', marginBottom: '8px' } }, animeInfo.title),
            React.createElement('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', color: 'var(--text-secondary)', fontSize: '14px' } },
              animeInfo.genres.slice(0, 6).map((genre: string) => React.createElement('span', { key: genre, className: 'badge badge-sub', style: { backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' } }, genre)),
              animeInfo.genres.length > 6 && React.createElement('span', { className: 'badge', style: { backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' } }, `+${animeInfo.genres.length - 6} more`)
            )
          ),
          React.createElement('div', { style: { display: 'flex', gap: '8px' } },
            React.createElement('button', {
              className: 'btn btn-secondary',
              onClick: scrapeEpisodes,
              disabled: scrapingStatus === 'episodes'
            },
              React.createElement(Loader2, { size: 18, className: scrapingStatus === 'episodes' ? 'spinner' : '' }),
              ' Re-scan Episodes'
            )
          )
        ),

        scrapingStatus === 'episodes' && React.createElement('div', { style: { marginBottom: '16px' } },
          React.createElement('div', { className: 'progress-bar' },
            React.createElement('div', { className: 'progress-fill', style: { width: `${scrapingProgress}%` } })
          ),
          React.createElement('p', { style: { textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px', marginTop: '8px' } },
            `Extracting video sources from ${episodes.length} episodes...`
          )
        ),

        episodes.length > 0 && React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' } },
            React.createElement('label', { style: { display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' } },
              React.createElement('input', {
                type: 'checkbox',
                checked: selectedEpisodes.size === episodes.length && episodes.length > 0,
                onChange: toggleSelectAll,
                style: { width: '16px', height: '16px', accentColor: 'var(--accent)' }
              }),
              `Select All (${episodes.length} episodes)`
            ),
            React.createElement('span', { style: { color: 'var(--text-secondary)', fontSize: '13px' } },
              `${selectedEpisodes.size} selected`
            ),
            React.createElement('span', { style: { color: 'var(--accent)', fontSize: '12px', fontWeight: 500 } },
              getSeasonFilterInfo()
            )
          ),
          React.createElement('button', {
            className: 'btn btn-success',
            onClick: generateDownloads,
            disabled: generatingDownloads || selectedEpisodes.size === 0,
            style: { minWidth: '200px' }
          },
            generatingDownloads ? (
              React.createElement(React.Fragment, null,
                React.createElement(Loader2, { className: 'spinner' }),
                ' Generating Download Files...'
              )
            ) : (
              React.createElement(React.Fragment, null,
                React.createElement(Download, { size: 18 }),
                ` Generate Download Files (${selectedEpisodes.size} episodes)`
              )
            )
          )
        ),

        React.createElement('div', { className: 'episode-list' },
          episodes.map((epInfo: EpisodeDownloadInfo, index: number) => React.createElement('div', {
            key: index,
            className: `episode-item ${epInfo.error ? 'error' : ''}`,
            style: { opacity: selectedEpisodes.has(index) ? 1 : 0.6 }
          },
            React.createElement('input', {
              type: 'checkbox',
              checked: selectedEpisodes.has(index),
              onChange: () => toggleEpisodeSelection(index),
              style: { width: '18px', height: '18px', accentColor: 'var(--accent)', flexShrink: 0 }
            }),
            React.createElement('div', { className: 'episode-info', style: { flex: 1, minWidth: 0 } },
              React.createElement('div', { className: 'episode-title' },
                epInfo.episode.title,
                epInfo.episode.season && epInfo.episode.episode && React.createElement('span', { style: { marginLeft: '8px', color: 'var(--text-secondary)', fontWeight: '400' } },
                  `S${epInfo.episode.season}E${String(epInfo.episode.episode).padStart(2, '0')}`
                ),
                epInfo.episode.episode && !epInfo.episode.season && React.createElement('span', { style: { marginLeft: '8px', color: 'var(--text-secondary)', fontWeight: '400' } },
                  `Ep ${epInfo.episode.episode}`
                )
              ),
              React.createElement('div', { className: 'episode-meta' },
                getLanguageBadge(epInfo.episode.language),
                React.createElement('span', null, epInfo.episode.quality),
                epInfo.error && React.createElement('span', { style: { color: 'var(--error)' } },
                  React.createElement(AlertCircle, { size: 14 }), ` ${epInfo.error}`
                )
              )
            ),
            React.createElement('div', { className: 'episode-sources' },
              epInfo.video_sources.map((source: VideoSource, si: number) => {
                const best = getBestSource(epInfo.video_sources)
                const isBest = best && source.url === best.url
                return React.createElement('span', { key: si, className: `source-badge ${isBest ? 'best' : ''}` },
                  `${source.quality} (${source.type})`
                )
              }),
              epInfo.video_sources.length === 0 && !epInfo.error && React.createElement('span', { className: 'source-badge', style: { color: 'var(--warning)' } },
                'No sources found'
              )
            )
          )),
          episodes.length === 0 && scrapingStatus === 'done' && React.createElement('div', { style: { textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' } },
            React.createElement(Info, { size: 48, style: { marginBottom: '16px', opacity: 0.5 } }),
            React.createElement('p', null, 'No episodes found. Try changing the language or season filter.')
          )
        )
      )
    )
  }

  // Render Download Section
  const renderDownloadSection = () => {
    if (!downloadResult) return null
    
    return (
      React.createElement('section', { className: 'card', style: { marginBottom: '24px' } },
        React.createElement('h2', { style: { fontSize: '18px', fontWeight: '600', marginBottom: '20px' } },
          React.createElement(CheckCircle, { size: 20, style: { color: 'var(--success)', marginRight: '8px', verticalAlign: 'middle' } }),
          ' Download Files Ready'
        ),
        React.createElement('div', { className: 'download-options' },
          Object.entries(downloadResult.files).map(([key, file]) => {
            const info = formatTypeLabels[key]
            return React.createElement('a', {
              key: key,
              href: file.url,
              className: 'download-option',
              download: true,
              target: '_blank',
              rel: 'noopener noreferrer'
            },
              React.createElement('div', { className: 'download-option-icon', style: { color: 'var(--accent)' } }, info.icon),
              React.createElement('span', { className: 'download-option-name' }, info.name),
              React.createElement('span', { className: 'download-option-desc' }, info.desc)
            )
          })
        ),
        React.createElement('div', { style: { marginTop: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap' } },
          React.createElement('button', { className: 'btn btn-primary', onClick: downloadAll },
            React.createElement(Download, { size: 18 }),
            ' Download All as ZIP'
          ),
          React.createElement('a', {
            href: downloadResult.files.idm?.url || '#',
            className: 'btn btn-secondary',
            target: '_blank',
            rel: 'noopener noreferrer'
          },
            React.createElement(ExternalLink, { size: 18 }),
            ' Open IDM File Directly'
          )
        )
      )
    )
  }

  return (
    React.createElement('div', { className: 'container', style: { paddingTop: '32px', paddingBottom: '32px' } },
      React.createElement('header', { style: { marginBottom: '32px' } },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' } },
          React.createElement(Zap, { size: 32, style: { color: 'var(--accent)' } }),
          React.createElement('h1', { style: { fontSize: '28px', fontWeight: '600' } }, 'Wcoflix Downloader')
        ),
        React.createElement('p', { style: { color: 'var(--text-secondary)', fontSize: '15px' } },
          'Generate batch download links for IDM, AB Downloader, Aria2, and more'
        )
      ),

      renderProxySettings(),
      renderInputForm(),
      renderAnimeSection(),
      renderDownloadSection(),
      React.createElement('footer', { className: 'footer' },
        React.createElement('p', null,
          'Wcoflix Downloader v1.0.0 \u2022 ',
          React.createElement('a', { href: 'https://github.com/mzmarkib/wcoflix-downlaoder', target: '_blank', rel: 'noopener noreferrer', style: { color: 'var(--accent)' } }, 'GitHub'),
          ' \u2022 ',
          React.createElement('span', { style: { color: 'var(--warning)' } }, 'Note: Cloudflare protection may block automated scraping. Use residential proxies for best results.')
        )
      )
    )
  )
}

export default App