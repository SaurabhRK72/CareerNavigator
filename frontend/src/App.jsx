import { Suspense, lazy, useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import './App.css'

const SkillDemandChart = lazy(() => import('./components/SkillDemandChart.jsx'))

const navigation = [
  { to: '/', label: 'Overview', short: 'OV' },
  { to: '/market', label: 'Job market', short: 'JM' },
  { to: '/recommendations', label: 'Career match', short: 'CM' },
  { to: '/skill-gaps', label: 'Skill gaps', short: 'SG' },
  { to: '/roadmap', label: 'Learning roadmap', short: 'LR' },
  { to: '/sources', label: 'Sources & project', short: 'SP' },
]

function App() {
  const [health, setHealth] = useState('checking')
  const location = useLocation()
  const currentPage =
    navigation.find((item) => item.to === location.pathname)?.label ??
    'Workspace'

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('API health check failed')
        return response.json()
      })
      .then((data) => setHealth(data.status === 'ok' ? 'online' : 'error'))
      .catch((error) => {
        if (error.name !== 'AbortError') setHealth('offline')
      })
    return () => controller.abort()
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">N</span>
          <span>
            <strong>CareerNavigator</strong>
            <small>AI career intelligence</small>
          </span>
        </NavLink>

        <p className="nav-heading">WORKSPACE</p>
        <nav className="main-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `nav-link${isActive ? ' active' : ''}`
              }
            >
              <span className="nav-icon" aria-hidden="true">
                {item.short}
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="privacy-note">
            <span className="privacy-dot" />
            <div>
              <strong>Built for clarity</strong>
              <p>Insights, not hiring predictions.</p>
            </div>
          </div>
          <p className="sidebar-caption">DASHBOARD · CONNECTED TO API</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="crumb-separator">/</span>
            <strong>{currentPage}</strong>
          </div>
          <div className="topbar-right">
            <span className={`api-status ${health}`}>
              <span className="status-dot" />
              {health === 'online'
                ? 'API connected'
                : health === 'checking'
                  ? 'Checking API'
                  : 'API unavailable'}
            </span>
            <span className="avatar" aria-label="Student profile">
              ST
            </span>
          </div>
        </header>

        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/skill-gaps" element={<SkillGapPage />} />
          <Route path="/roadmap" element={<RoadmapPage />} />
          <Route path="/sources" element={<SourcesPage />} />
        </Routes>
      </main>
    </div>
  )
}

function OverviewPage() {
  const [summary, setSummary] = useState(null)
  const [skills, setSkills] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function loadDashboard() {
      setLoading(true)
      setError('')
      try {
        const [summaryResponse, skillsResponse] = await Promise.all([
          fetch('/api/market/summary', { signal: controller.signal }),
          fetch('/api/market/skills?limit=8', { signal: controller.signal }),
        ])
        if (!summaryResponse.ok || !skillsResponse.ok) {
          const failedResponse = !summaryResponse.ok
            ? summaryResponse
            : skillsResponse
          const body = await failedResponse.json().catch(() => ({}))
          throw new Error(body.detail || 'Could not load market analytics.')
        }
        const [summaryData, skillsData] = await Promise.all([
          summaryResponse.json(),
          skillsResponse.json(),
        ])
        setSummary(summaryData)
        setSkills(skillsData)
      } catch (loadError) {
        if (loadError.name !== 'AbortError') setError(loadError.message)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    loadDashboard()
    return () => controller.abort()
  }, [])

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">CAREER INTELLIGENCE</p>
          <h1>See where opportunity is moving.</h1>
          <p className="page-description">
            Explore job-market signals, understand in-demand skills, and make
            your next career move with confidence.
          </p>
        </div>
        <button
          className="secondary-button"
          onClick={() => window.location.reload()}
          type="button"
        >
          <span aria-hidden="true">↻</span> Refresh
        </button>
      </section>

      <div className="data-notice">
        <span className="notice-icon" aria-hidden="true">i</span>
        <p>
          Market data refreshes periodically. Recommendations are skill
          similarity indicators, not hiring probabilities.
        </p>
        <NavLink to="/sources">How data works <span aria-hidden="true">→</span></NavLink>
      </div>

      {error && (
        <div className="error-panel" role="alert">
          <div>
            <strong>Market data isn&apos;t available yet</strong>
            <p>{error}</p>
          </div>
          <button
            className="text-button"
            onClick={() => window.location.reload()}
            type="button"
          >
            Try again
          </button>
        </div>
      )}

      <section className="metrics-grid" aria-label="Market summary">
        <MetricCard
          label="Unique job postings"
          value={loading ? '—' : summary?.unique_job_count ?? '—'}
          note="In the current collected sample"
          icon="01"
        />
        <MetricCard
          label="Skills tracked"
          value={loading ? '—' : skills?.skills?.length ?? '—'}
          note="Editable skills dictionary"
          icon="02"
          accent
        />
        <MetricCard
          label="Data sources"
          value={loading ? '—' : summary?.source_names?.length ?? '—'}
          note={summary?.source_names?.join(', ') || 'Awaiting source data'}
          icon="03"
        />
        <MetricCard
          label="Last successful refresh"
          value={loading ? '—' : formatRefresh(summary?.last_successful_refresh)}
          note="Collection time, not posting date"
          icon="04"
        />
      </section>

      <section className="dashboard-grid">
        <article className="panel skill-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">SKILLS IN DEMAND</p>
              <h2>Most-mentioned skills</h2>
            </div>
            <span className="sample-pill">
              n = {skills?.sample_size ?? '—'}
            </span>
          </div>
          {loading ? (
            <LoadingState label="Loading skill analytics…" />
          ) : error ? (
            <EmptyState title="Waiting for market data" detail="Configure a database and collect job postings to populate this chart." />
          ) : skills?.skills?.length ? (
            <>
              <Suspense fallback={<LoadingState label="Loading chart…" />}>
                <SkillDemandChart skills={skills.skills} />
              </Suspense>
              <p className="chart-footnote">
                Demand = unique sampled jobs mentioning the skill ÷ all unique
                sampled jobs.
              </p>
            </>
          ) : (
            <EmptyState title="No job postings in this sample" detail="Collect permitted job data to calculate skill demand." />
          )}
        </article>

        <article className="panel roles-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">ROLE LANDSCAPE</p>
              <h2>Popular job titles</h2>
            </div>
            <NavLink className="panel-link" to="/market">Explore <span aria-hidden="true">→</span></NavLink>
          </div>
          {loading ? (
            <LoadingState label="Loading job titles…" />
          ) : summary?.top_roles?.length ? (
            <div className="role-list">
              {summary.top_roles.slice(0, 6).map((role, index) => (
                <div className="role-row" key={role.name}>
                  <span className="role-rank">{String(index + 1).padStart(2, '0')}</span>
                  <span className="role-name">{role.name}</span>
                  <span className="role-count">{role.job_count}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No roles to show yet" detail={error || 'Role summaries appear after job postings are stored.'} />
          )}
          <div className="mini-callout">
            <span className="callout-spark" aria-hidden="true">✳</span>
            <p>
              <strong>Make your next move count.</strong>
              <br />Start with the skills appearing most often in your target roles.
            </p>
          </div>
        </article>
      </section>

      <section className="lower-grid">
        <article className="panel locations-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">WHERE JOBS ARE</p>
              <h2>Top locations</h2>
            </div>
            <span className="quiet-label">Sample counts</span>
          </div>
          {summary?.top_locations?.length ? (
            <div className="location-list">
              {summary.top_locations.slice(0, 5).map((location) => (
                <div className="location-row" key={location.name}>
                  <span>{location.name}</span>
                  <div className="location-track">
                    <span
                      style={{
                        width: `${Math.max(
                          8,
                          (location.job_count /
                            summary.top_locations[0].job_count) *
                            100,
                        )}%`,
                      }}
                    />
                  </div>
                  <strong>{location.job_count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="Location data unavailable" detail="No collected job locations to summarize." />
          )}
        </article>

        <article className="panel date-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">DATA COVERAGE</p>
              <h2>Posting date range</h2>
            </div>
            <span className="date-icon" aria-hidden="true">◷</span>
          </div>
          <div className="date-range">
            <div>
              <span>EARLIEST</span>
              <strong>{summary?.posted_date_range?.start || '—'}</strong>
            </div>
            <span className="date-arrow" aria-hidden="true">→</span>
            <div>
              <span>MOST RECENT</span>
              <strong>{summary?.posted_date_range?.end || '—'}</strong>
            </div>
          </div>
          <p className="chart-footnote">
            This is the posting-date range in the collected sample. It does not
            represent a trend by itself.
          </p>
        </article>
      </section>

      <footer className="page-footer">
        <span>CareerNavigator AI · Data-backed, student-centered guidance</span>
        <span>Market sample only · Refreshed periodically</span>
      </footer>
    </div>
  )
}

function MarketPage() {
  const [liveQuery, setLiveQuery] = useState('data analyst')
  const [liveLocation, setLiveLocation] = useState('Pune')
  const [liveResults, setLiveResults] = useState(null)
  const [liveLoading, setLiveLoading] = useState(false)
  const [saveLoading, setSaveLoading] = useState(false)
  const [liveError, setLiveError] = useState('')
  const [saveResult, setSaveResult] = useState(null)
  const [location, setLocation] = useState('')
  const [role, setRole] = useState('')
  const [skill, setSkill] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadMarketData(filters) {
    const params = new URLSearchParams()
    if (filters.location.trim()) params.set('location', filters.location.trim())
    if (filters.role.trim()) params.set('role', filters.role.trim())
    if (filters.skill.trim()) params.append('skill', filters.skill.trim())
    const [summaryResponse, skillsResponse, jobsResponse] = await Promise.all([
      fetch(`/api/market/summary?${params}`),
      fetch(`/api/market/skills?${params}`),
      fetch(`/api/market/jobs?${params}&limit=20`),
    ])
    const responses = [summaryResponse, skillsResponse, jobsResponse]
    const failed = responses.find((response) => !response.ok)
    if (failed) {
      const body = await failed.json().catch(() => ({}))
      throw new Error(body.detail || 'Market data request failed.')
    }
    const [summary, skills, jobs] = await Promise.all(
      responses.map((response) => response.json()),
    )
    setData({ summary, skills, jobs })
  }

  async function runSearch(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await loadMarketData({ location, role, skill })
    } catch (searchError) {
      setError(searchError.message)
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  async function searchLiveJobs(event) {
    event.preventDefault()
    setLiveLoading(true)
    setLiveError('')
    setSaveResult(null)
    setLiveResults(null)
    try {
      const params = new URLSearchParams({ query: liveQuery.trim() })
      if (liveLocation.trim()) params.set('location', liveLocation.trim())
      const response = await fetch(`/api/jobs/search?${params}`)
      const body = await response.json()
      if (!response.ok) {
        throw new Error(body.detail || 'Could not fetch live job postings.')
      }
      setLiveResults(body)
    } catch (searchError) {
      setLiveError(searchError.message)
    } finally {
      setLiveLoading(false)
    }
  }

  async function processLiveJobs() {
    if (!liveResults?.jobs?.length) return
    setSaveLoading(true)
    setLiveError('')
    try {
      const response = await fetch('/api/jobs/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobs: liveResults.jobs }),
      })
      const body = await response.json()
      if (!response.ok) {
        throw new Error(body.detail || 'Could not process and save these jobs.')
      }
      setSaveResult(body)
      setLoading(true)
      setError('')
      try {
        await loadMarketData({ location: '', role: '', skill: '' })
      } catch (refreshError) {
        setError(`Jobs were saved, but the dashboard refresh failed: ${refreshError.message}`)
      } finally {
        setLoading(false)
      }
    } catch (processError) {
      setLiveError(processError.message)
    } finally {
      setSaveLoading(false)
    }
  }

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">MARKET EXPLORER</p>
          <h1>Explore job market signals.</h1>
          <p className="page-description">
            Collect authorized job results, process them into the database, and
            explore market analytics from the saved sample.
          </p>
        </div>
      </section>
      <section className="workflow-panel" aria-label="How CareerNavigator works">
        <div className="workflow-heading">
          <div><p className="eyebrow">PROJECT WORKFLOW</p><h2>From live jobs to a learning plan</h2></div>
          <NavLink to="/sources">See data limits <span aria-hidden="true">→</span></NavLink>
        </div>
        <div className="workflow-steps">
          <div><span>01</span><strong>Collect</strong><p>Search Google Jobs through SerpApi.</p></div>
          <div><span>02</span><strong>Clean & save</strong><p>Normalize titles, remove duplicates, extract skills.</p></div>
          <div><span>03</span><strong>Analyze</strong><p>Measure skill demand in the saved job sample.</p></div>
          <div><span>04</span><strong>Get guidance</strong><p>Compare your skills and build a learning roadmap.</p></div>
        </div>
        <div className="workflow-links">
          <NavLink to="/recommendations">Career match</NavLink>
          <NavLink to="/skill-gaps">Skill-gap analysis</NavLink>
          <NavLink to="/roadmap">Learning roadmap</NavLink>
        </div>
      </section>
      <section className="panel live-search-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">STEP 1 · LIVE DATA</p><h2>Find current job postings</h2></div>
          <span className="sample-pill">SerpApi · India</span>
        </div>
        <p className="section-description">This makes a bounded external API request. Results are only saved when you choose “Clean & save jobs.”</p>
        <form className="filter-panel live-search-form" onSubmit={searchLiveJobs}>
          <label>
            Job title or keywords
            <input required maxLength={100} value={liveQuery} onChange={(event) => setLiveQuery(event.target.value)} placeholder="e.g. data analyst" />
          </label>
          <label>
            City or location
            <input maxLength={100} value={liveLocation} onChange={(event) => setLiveLocation(event.target.value)} placeholder="e.g. Pune" />
          </label>
          <button className="primary-button" disabled={liveLoading || saveLoading || !liveQuery.trim()} type="submit">
            {liveLoading ? 'Searching…' : 'Search live jobs'}
          </button>
        </form>
        {liveError && <div className="error-panel" role="alert"><div><strong>Job collection or processing failed</strong><p>{liveError}</p></div></div>}
        {liveResults && (
          <div className="live-results">
            <div className="live-results-summary">
              <div><strong>{liveResults.jobs.length} postings found</strong><span>{liveResults.source} · {liveResults.pages_fetched} page(s) · collected {formatRefresh(liveResults.collected_at)}</span></div>
              <button className="primary-button" disabled={!liveResults.jobs.length || saveLoading} onClick={processLiveJobs} type="button">
                {saveLoading ? 'Cleaning & saving…' : 'Clean & save jobs'}
              </button>
            </div>
            {liveResults.jobs.length ? (
              <div className="table-scroll">
                <table><thead><tr><th>Job title</th><th>Company</th><th>Location</th><th>Posted</th><th>Source</th></tr></thead>
                  <tbody>{liveResults.jobs.map((job, index) => <tr key={`${job.provider}-${job.provider_id || index}`}>
                    <td><strong>{job.title || 'Title unavailable'}</strong></td><td>{job.company || '—'}</td><td>{job.location || '—'}</td><td>{job.posted_date ? job.posted_date.slice(0, 10) : 'Date unavailable'}</td>
                    <td>{job.source_url ? <a className="job-source-link" href={job.source_url} target="_blank" rel="noreferrer">View listing ↗</a> : '—'}</td>
                  </tr>)}</tbody>
                </table>
              </div>
            ) : <EmptyState title="No job postings returned" detail="Try a different role or nearby location." />}
            {saveResult && (
              <div className="save-result" role="status">
                <strong>Jobs processed and saved.</strong>
                <span>{saveResult.jobs_created_count} new · {saveResult.jobs_updated_count} updated · {saveResult.quality_report.duplicate_count} duplicates removed · {saveResult.quality_report.excluded_missing_title_count} missing-title records excluded.</span>
                <span>The dashboard below has been refreshed from the database.</span>
              </div>
            )}
          </div>
        )}
      </section>
      <div className="section-divider"><span>STEP 2 · EXPLORE THE SAVED SAMPLE</span><span>Filters below query the database, not the external API.</span></div>
      <form className="filter-panel" onSubmit={runSearch}>
        <label>
          Location
          <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="e.g. Mumbai" />
        </label>
        <label>
          Role
          <input value={role} onChange={(event) => setRole(event.target.value)} placeholder="e.g. Data Analyst" />
        </label>
        <label>
          Skill
          <input value={skill} onChange={(event) => setSkill(event.target.value)} placeholder="e.g. Python" />
        </label>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? 'Loading…' : 'Apply filters'}
        </button>
      </form>
      {error && <div className="error-panel" role="alert"><div><strong>Could not load market data</strong><p>{error}</p></div></div>}
      {data && (
        <>
          <section className="metrics-grid compact-metrics">
            <MetricCard label="Unique postings" value={data.summary.unique_job_count} note="Filtered sample" icon="01" />
            <MetricCard label="Data source" value={data.summary.source_names.join(', ') || '—'} note="Provider for collected records" icon="02" />
            <MetricCard label="Skill results" value={data.skills.skills.length} note={`Among ${data.skills.sample_size} jobs`} icon="03" accent />
            <MetricCard label="Date coverage" value={data.summary.posted_date_range.start || '—'} note={`Through ${data.summary.posted_date_range.end || '—'}`} icon="04" />
          </section>
          <section className="panel table-panel">
            <div className="panel-heading"><div><p className="eyebrow">FILTERED SAMPLE</p><h2>Job postings</h2></div><span className="sample-pill">Showing {data.jobs.jobs.length} of {data.jobs.sample_size}</span></div>
            {data.jobs.jobs.length ? (
              <div className="table-scroll"><table><thead><tr><th>Role</th><th>Company</th><th>Location</th><th>Skills</th><th>Posted</th></tr></thead><tbody>{data.jobs.jobs.map((job, index) => <tr key={`${job.provider}-${job.provider_id || index}`}><td><strong>{job.title}</strong></td><td>{job.company || '—'}</td><td>{job.location || '—'}</td><td>{job.skills.join(', ') || '—'}</td><td>{job.posted_date ? job.posted_date.slice(0, 10) : '—'}</td></tr>)}</tbody></table></div>
            ) : <EmptyState title="No jobs match these filters" detail="Try removing a filter or collect additional job postings." />}
          </section>
          <section className="panel skill-results">
            <div className="panel-heading"><div><p className="eyebrow">SKILL DEMAND</p><h2>Skills in the filtered sample</h2></div></div>
            <div className="demand-list">{data.skills.skills.map((item) => <div className="demand-row" key={item.skill}><div><strong>{item.skill}</strong><span>{item.category}</span></div><div className="demand-track"><span style={{ width: `${item.demand_percentage}%` }} /></div><strong>{item.demand_percentage.toFixed(2)}%</strong><small>{item.job_count}/{data.skills.sample_size} jobs</small></div>)}</div>
          </section>
        </>
      )}
      {!data && !loading && !error && (
        <section className="panel initial-state">
          <span className="initial-icon" aria-hidden="true">⌕</span>
          <h2>Load saved market analytics</h2>
          <p>Once jobs are collected and saved, use these filters to view unique postings, skill demand, and the data coverage summary.</p>
          <button className="primary-button" onClick={(event) => runSearch(event)} type="button">Load all collected jobs</button>
        </section>
      )}
      <footer className="page-footer"><span>Counts represent unique cleaned postings.</span><span>Skill demand uses the filtered job count as denominator.</span></footer>
    </div>
  )
}

function SourcesPage() {
  return (
    <div className="page-content">
      <section className="page-heading"><div><p className="eyebrow">TRANSPARENCY</p><h1>Know what the data means.</h1><p className="page-description">Sources, refresh behavior, and project limitations.</p></div></section>
      <section className="info-grid">
        <article className="panel info-card"><p className="eyebrow">JOB DATA</p><h2>Google Jobs via SerpApi</h2><p>Job search results are requested through the SerpApi Google Jobs engine with India as the configured country. SerpApi requires an API key and its free plan is limited; review current quotas, provider terms, and listing-source conditions before use. API keys remain on the backend.</p><a href="https://serpapi.com/google-jobs-api" target="_blank" rel="noreferrer">SerpApi Google Jobs API ↗</a></article>
        <article className="panel info-card"><p className="eyebrow">REFRESH MODEL</p><h2>Periodic, not continuous</h2><p>Job listings are collected when a refresh is run. The system records both the source posting date and collection time. One refresh is a current sample, not a historical trend.</p></article>
        <article className="panel info-card"><p className="eyebrow">ANALYTICS</p><h2>Transparent denominator</h2><p>Skill demand is the number of unique filtered postings mentioning a skill divided by all unique filtered postings. Results describe the collected sample only.</p></article>
        <article className="panel info-card"><p className="eyebrow">RECOMMENDATIONS</p><h2>Similarity, not probability</h2><p>Role matching compares reported skills with encoded role requirements. It is not a probability of hiring or a guarantee of employment. Profiles are self-reported and role data can be incomplete.</p></article>
        <article className="panel info-card"><p className="eyebrow">DATA QUALITY</p><h2>Missing means unknown</h2><p>Missing salary, location, dates, or skills are not silently invented. Salary comparisons require consistent currency and reliable values; experience summaries require reliable structured data.</p></article>
        <article className="panel info-card"><p className="eyebrow">PROJECT STATUS</p><h2>Working project modules</h2><p>The FastAPI collector, cleaning and skill extraction pipeline, database persistence, market analytics, React dashboard, explainable role matching, skill-gap analysis, and personalized roadmaps are implemented. Live job collection requires a SerpApi key and market analytics require a configured database.</p></article>
      </section>
    </div>
  )
}

function RecommendationsPage() {
  const [skills, setSkills] = useState('SQL, Excel, Python')
  const [education, setEducation] = useState('IT Engineering')
  const [experience, setExperience] = useState('0')
  const [interests, setInterests] = useState('data, business, research')
  const [location, setLocation] = useState('')
  const [preferredRoles, setPreferredRoles] = useState('')
  const [recommendations, setRecommendations] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadRecommendations(event) {
    event.preventDefault()
    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/careers/recommendations?limit=4', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          buildStudentProfile({
            skills,
            education,
            experience,
            interests,
            location,
            preferredRoles,
          }),
        ),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'Could not calculate role matches.')
      }
      setRecommendations(await response.json())
    } catch (loadError) {
      setError(loadError.message)
      setRecommendations(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">CAREER MATCH</p>
          <h1>Find the best-fit role for your profile.</h1>
          <p className="page-description">
            Compare your profile with transparent, curated role requirements.
          </p>
        </div>
      </section>

      <form className="filter-panel profile-form" onSubmit={loadRecommendations}>
        <label>
          Technical skills and levels
          <input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="e.g. SQL: advanced, Excel: beginner, Python" />
        </label>
        <p className="form-hint">Add a level after a colon when known. Skills without a level are treated as intermediate.</p>
        <label>Education<input value={education} onChange={(event) => setEducation(event.target.value)} placeholder="Optional" /></label>
        <label>Experience (years)<input type="number" min="0" max="60" step="0.5" value={experience} onChange={(event) => setExperience(event.target.value)} /></label>
        <label>Interests<input value={interests} onChange={(event) => setInterests(event.target.value)} placeholder="e.g. data, research" /></label>
        <label>Preferred location<input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Optional" /></label>
        <label>Preferred roles<input value={preferredRoles} onChange={(event) => setPreferredRoles(event.target.value)} placeholder="Optional, comma-separated" /></label>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? 'Analyzing…' : 'Recommend roles'}
        </button>
      </form>

      {error && (
        <div className="error-panel" role="alert">
          <div>
            <strong>Could not calculate a role match</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {loading ? (
        <LoadingState label="Comparing your profile with role requirements…" />
      ) : recommendations ? (
        <section className="recommendation-list">
          <div className="recommendation-notice">
            <strong>How to read these scores</strong>
            <p>{recommendations.scoring_method} {recommendations.score_disclaimer}</p>
          </div>
          {recommendations.unknown_profile_skills.length > 0 && (
            <div className="unknown-skills">Not in the current skill dictionary: {recommendations.unknown_profile_skills.join(', ')}</div>
          )}
          {recommendations.recommendations.map((item) => (
            <article className="panel recommendation-card" key={item.role_id}>
              <div className="recommendation-heading">
                <div><p className="eyebrow">ROLE MATCH</p><h2>{item.role_name}</h2><p>{item.description}</p></div>
                <div className="score-circle"><strong>{item.match_score}%</strong><span>overlap</span></div>
              </div>
              <p className="insight-summary">{item.explanation}</p>
              <div className="gap-grid">
                <SkillGroup title="Matching skills" skills={item.matching_skills} kind="matched" />
                <SkillGroup title="Partial skills" skills={item.partial_skills} kind="partial" />
                <SkillGroup title="Skills to build" skills={item.missing_skills} kind="gap" />
              </div>
              {item.preference_note && <p className="chart-footnote">{item.preference_note}</p>}
            </article>
          ))}
        </section>
      ) : (
        <EmptyState title="Ready to compare your profile" detail="Submit your skills and optional preferences to see role matches with explanations. Your profile is not saved." />
      )}
    </div>
  )
}

function SkillGapPage() {
  const [roles, setRoles] = useState([])
  const [roleId, setRoleId] = useState('')
  const [skills, setSkills] = useState('Excel: beginner, SQL: intermediate, Power BI')
  const [gaps, setGaps] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch('/api/careers/roles')
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load career roles.')
        return response.json()
      })
      .then((data) => {
        if (!active) return
        setRoles(data)
        setRoleId(data[0]?.id || '')
      })
      .catch((loadError) => {
        if (active) setError(loadError.message)
      })
    return () => { active = false }
  }, [])

  async function loadGaps(event) {
    event.preventDefault()
    if (!roleId) return
    setLoading(true)
    setError('')

    try {
      const response = await fetch(
        `/api/careers/skill-gaps?role_id=${encodeURIComponent(roleId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildStudentProfile({ skills })),
        },
      )
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'Could not calculate skill gaps.')
      }
      setGaps(await response.json())
    } catch (loadError) {
      setError(loadError.message)
      setGaps(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">SKILL GAPS</p>
          <h1>Spot the missing skills behind the role.</h1>
          <p className="page-description">
            See what you report, what is partial, and what to learn next.
          </p>
        </div>
      </section>

      <form className="filter-panel" onSubmit={loadGaps}>
        <label>Career role<select value={roleId} onChange={(event) => setRoleId(event.target.value)} disabled={!roles.length}><option value="">Select a role</option>{roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
        <label>Your skills and levels<input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="e.g. Excel: beginner, SQL: advanced" /></label>
        <p className="form-hint">Use beginner, intermediate, or advanced after a colon. Skills without a level default to intermediate.</p>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? 'Checking…' : 'Analyze gaps'}
        </button>
      </form>

      {error && (
        <div className="error-panel" role="alert">
          <div>
            <strong>Skill-gap analysis is unavailable</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {loading ? (
        <LoadingState label="Ranking your skill gaps…" />
      ) : gaps ? (
        <>
          <section className="panel insight-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">PROFILE COVERAGE</p>
                <h2>{gaps.match_score}% weighted coverage for {gaps.role_name}</h2>
              </div>
              <span className="sample-pill">{gaps.possessed.length} possessed · {gaps.partial.length} partial · {gaps.missing.length} missing</span>
            </div>
            <div className="gap-grid">
              <SkillGroup title="Already possessed" skills={gaps.possessed} kind="matched" />
              <SkillGroup title="Partially matched" skills={gaps.partial} kind="partial" />
              <SkillGroup title="Not listed in your profile" skills={gaps.missing} kind="gap" />
            </div>
            <p className="chart-footnote">{gaps.market_demand_note}</p>
          </section>

          <section className="panel insight-panel">
            <div className="panel-heading"><div><p className="eyebrow">FOCUS PLAN</p><h2>Highest-priority learning gaps</h2></div></div>
            <div className="focus-list">
              {gaps.priority_gaps.map((gap, index) => (
                <div key={gap.skill} className="focus-row">
                  <span className="focus-rank">0{index + 1}</span>
                  <div className="focus-meta">
                    <strong>{gap.skill}</strong>
                    <span>{gap.explanation}</span>
                  </div>
                  <span className="sample-pill">{gap.market_demand_percentage == null ? `Role weight ${gap.role_weight}` : `${gap.market_demand_percentage}% market demand`}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <EmptyState title="Ready to check your skill gaps" detail="Choose a career role and enter the skills you currently report. No market-demand data is required; without a database, gaps are prioritized by role importance." />
      )}
    </div>
  )
}

function RoadmapPage() {
  const [roles, setRoles] = useState([])
  const [roleId, setRoleId] = useState('')
  const [skills, setSkills] = useState('Excel: beginner, SQL: intermediate, Python')
  const [studyHours, setStudyHours] = useState(5)
  const [roadmap, setRoadmap] = useState(null)
  const [completed, setCompleted] = useState({})
  const [storageWarning, setStorageWarning] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch('/api/careers/roles')
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load career roles.')
        return response.json()
      })
      .then((data) => {
        if (!active) return
        setRoles(data)
        setRoleId(data[0]?.id || '')
      })
      .catch((loadError) => {
        if (active) setError(loadError.message)
      })
    return () => { active = false }
  }, [])

  async function generateRoadmap(event) {
    event.preventDefault()
    if (!roleId) return
    setLoading(true)
    setError('')
    setStorageWarning('')

    try {
      const response = await fetch('/api/careers/roadmaps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile: buildStudentProfile({ skills }),
          role_id: roleId,
          weekly_study_hours: Number(studyHours),
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || 'Could not generate your roadmap.')
      }
      const result = await response.json()
      setRoadmap(result)
      try {
        const saved = window.localStorage.getItem(`careercompass-roadmap-${result.role_id}`)
        const progress = saved ? JSON.parse(saved) : {}
        if (!progress || typeof progress !== 'object' || Array.isArray(progress)) {
          throw new Error('Saved progress has an invalid format.')
        }
        setCompleted(progress)
      } catch {
        setCompleted({})
        setStorageWarning('Roadmap created, but saved progress could not be loaded from this browser.')
      }
    } catch (loadError) {
      setError(loadError.message)
      setRoadmap(null)
    } finally {
      setLoading(false)
    }
  }

  function toggleMilestone(key) {
    const next = { ...completed, [key]: !completed[key] }
    setCompleted(next)
    if (roadmap) {
      try {
        window.localStorage.setItem(
          `careercompass-roadmap-${roadmap.role_id}`,
          JSON.stringify(next),
        )
        setStorageWarning('')
      } catch {
        setStorageWarning('Progress is shown for this visit but could not be saved in this browser.')
      }
    }
  }

  return (
    <div className="page-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">LEARNING ROADMAP</p>
          <h1>Build a clear path toward your target role.</h1>
          <p className="page-description">
            Create weekly milestones from role requirements and your self-reported skill gaps.
          </p>
        </div>
      </section>

      <form className="filter-panel" onSubmit={generateRoadmap}>
        <label>Target role<select value={roleId} onChange={(event) => setRoleId(event.target.value)} disabled={!roles.length}><option value="">Select a role</option>{roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label>
        <label>Current skills and levels<input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="e.g. Excel: beginner, SQL: advanced" /></label>
        <p className="form-hint">Use beginner, intermediate, or advanced after a colon. Skills without a level default to intermediate.</p>
        <label>Study hours per week<input type="number" min="1" max="40" value={studyHours} onChange={(event) => setStudyHours(event.target.value)} /></label>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? 'Planning…' : 'Generate roadmap'}
        </button>
      </form>

      {error && (
        <div className="error-panel" role="alert">
          <div>
            <strong>Your roadmap could not be generated</strong>
            <p>{error}</p>
          </div>
        </div>
      )}
      {storageWarning && <p className="storage-warning" role="status">{storageWarning}</p>}

      {loading ? (
        <LoadingState label="Creating your roadmap…" />
      ) : roadmap ? (
        <section className="panel insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">PERSONALIZED PLAN · {roadmap.total_weeks} WEEKS</p>
              <h2>{roadmap.role_name}</h2>
            </div>
            <span className="sample-pill">{roadmap.weekly_study_hours} hours / week</span>
          </div>
          {roadmap.milestones.length ? (
            <div className="roadmap-list">
              {roadmap.milestones.map((milestone) => {
                const key = `${milestone.week}-${milestone.skill}`
                return (
                  <article className="roadmap-milestone" key={key}>
                    <div className="roadmap-week">WEEK {milestone.week}</div>
                    <div className="roadmap-task">
                      <label className="roadmap-check"><input type="checkbox" checked={Boolean(completed[key])} onChange={() => toggleMilestone(key)} /><span>Mark this week complete</span></label>
                      <h3>{milestone.skill}</h3>
                      <p><strong>Why it matters:</strong> {milestone.why_it_matters}</p>
                      <p><strong>Weekly goal:</strong> {milestone.goal}</p>
                      <p><strong>Practice:</strong> {milestone.practice_task}</p>
                      <p><strong>Mini-project:</strong> {milestone.mini_project}</p>
                      {milestone.resource ? (
                        <a className="resource-link" href={milestone.resource.url} target="_blank" rel="noreferrer">
                          {milestone.resource.title} · {milestone.resource.provider} ↗
                        </a>
                      ) : (
                        <p className="chart-footnote">No verified resource is cataloged for this skill yet; no link was generated.</p>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <EmptyState title="No skill gaps found" detail="Your reported skills meet the current encoded role levels. Try a role with a different focus or review whether your skill levels are accurate." />
          )}
          <p className="chart-footnote">{roadmap.resource_note} Progress checkboxes are saved in this browser only.</p>
        </section>
      ) : (
        <EmptyState title="Ready to create a learning plan" detail="Select a role, enter your current skills, and choose a weekly study-time budget. This works without market data; demand details appear after the database is configured." />
      )}
    </div>
  )
}

function parseList(value) {
  return String(value || '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function buildStudentProfile({
  skills = '',
  education = '',
  experience = '',
  interests = '',
  location = '',
  preferredRoles = '',
}) {
  const experienceValue = String(experience).trim()
  return {
    technical_skills: parseSkillEntries(skills),
    education: education.trim() || null,
    experience_years: experienceValue ? Number(experienceValue) : null,
    interests: parseList(interests),
    preferred_location: location.trim() || null,
    preferred_roles: parseList(preferredRoles),
  }
}

function parseSkillEntries(value) {
  return parseList(value)
    .map((entry) => {
      const levelMatch = entry.match(/^(.*):\s*(beginner|intermediate|advanced)$/i)
      return {
        name: (levelMatch ? levelMatch[1] : entry).trim(),
        level: levelMatch ? levelMatch[2].toLowerCase() : 'intermediate',
      }
    })
    .filter((skill) => skill.name)
}

function SkillGroup({ title, skills, kind }) {
  return (
    <div className="gap-column">
      <h3>{title}</h3>
      <div className="badge-list">
        {skills.length ? skills.map((item) => {
          const name = item.name || item.skill
          const detail = item.student_level
            ? `${item.student_level} / target ${item.required_level}`
            : `Target: ${item.required_level}`
          return (
            <span key={name} className={`skill-badge ${kind}`} title={detail}>
              {name}
            </span>
          )
        }) : <span className="skill-badge empty">None in this category</span>}
      </div>
    </div>
  )
}

function MetricCard({ label, value, note, icon, accent = false }) {
  return (
    <article className={`metric-card${accent ? ' metric-accent' : ''}`}>
      <div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-note">{note}</span>
    </article>
  )
}

function LoadingState({ label }) {
  return <div className="loading-state" role="status"><span className="spinner" />{label}</div>
}

function EmptyState({ title, detail }) {
  return <div className="empty-state"><span aria-hidden="true">◌</span><strong>{title}</strong><p>{detail}</p></div>
}

function formatRefresh(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default App
