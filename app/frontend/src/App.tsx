import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  LayoutDashboard, FileText, Cpu, User, GraduationCap,
  Briefcase, Code2, Award, BookOpen, AlertTriangle, Download,
  Settings, ChevronRight, Wifi, WifiOff
} from 'lucide-react'
import { systemApi, type SystemStatus } from './api/client'
import { Dashboard } from './pages/Dashboard'
import { Documents } from './pages/Documents'
import { Process } from './pages/Process'
import { Profiles } from './pages/Profiles'
import { ProfileDetail } from './pages/ProfileDetail'
import { SettingsPage } from './pages/Settings'

export function App() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [backendReady, setBackendReady] = useState(false)
  const [connecting, setConnecting] = useState(true)

  useEffect(() => {
    const tryConnect = async () => {
      for (let attempt = 0; attempt < 20; attempt++) {
        try {
          const status = await systemApi.getStatus()
          setSystemStatus(status)
          setBackendReady(true)
          setConnecting(false)
          return
        } catch {
          await new Promise(r => setTimeout(r, 1000))
        }
      }
      setConnecting(false)
    }
    tryConnect()
  }, [])

  if (connecting) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16 }}>
        <div className="spinner" style={{ width: 32, height: 32 }} />
        <div style={{ fontSize: 15, fontWeight: 600 }}>Starting local services…</div>
        <div className="text-muted text-sm">Connecting to local document processing backend</div>
      </div>
    )
  }

  if (!backendReady) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16, padding: 32 }}>
        <AlertTriangle size={48} color="var(--color-error)" />
        <div style={{ fontSize: 18, fontWeight: 700 }}>Backend Not Available</div>
        <div className="text-muted" style={{ textAlign: 'center', maxWidth: 400 }}>
          The local document processing service could not be started.
          Make sure all prerequisites are installed. See{' '}
          <code>docs/TROUBLESHOOTING.md</code> for help.
        </div>
      </div>
    )
  }

  const conflictCount = 0  // TODO: from global state

  return (
    <BrowserRouter>
      <div className="app-shell">
        {/* ─── Sidebar ─────────────────────────────────── */}
        <aside className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-logo">DocExtract</div>
            <div className="sidebar-subtitle">Document Intelligence</div>
          </div>

          <nav className="sidebar-nav">
            <NavItem to="/" icon={<LayoutDashboard size={15} />} label="Dashboard" exact />
            <NavItem to="/documents" icon={<FileText size={15} />} label="Documents" />
            <NavItem to="/process" icon={<Cpu size={15} />} label="Process" />

            <div className="nav-section-label">Analysis</div>
            <NavItem to="/profiles" icon={<User size={15} />} label="Profiles" />

            <div className="nav-section-label">Data</div>
            <NavItem to="/settings" icon={<Settings size={15} />} label="Settings" />
          </nav>

          <div className="sidebar-footer">
            {/* Startup issues */}
            {systemStatus && !systemStatus.checks.overall_ready && (
              <div style={{ marginBottom: 8, padding: '6px 8px', background: '#2c1f1f', borderRadius: 4, fontSize: 11, color: '#ff6b6b' }}>
                ⚠ Setup incomplete
              </div>
            )}
            <div className="offline-indicator">
              <div className="offline-dot" />
              OFFLINE MODE
            </div>
            <div style={{ fontSize: 10, color: '#495057', marginTop: 4 }}>
              All processing local
            </div>
          </div>
        </aside>

        {/* ─── Main Content ──────────────────────────── */}
        <main className="main-content">
          {/* Setup warning banner */}
          {systemStatus && !systemStatus.checks.overall_ready && (
            <div className="alert alert-warning" style={{ borderRadius: 0, borderLeft: 'none', borderRight: 'none', borderTop: 'none' }}>
              <AlertTriangle size={16} />
              <div>
                <strong>Setup Required: </strong>
                {systemStatus.checks.issues.slice(0, 1).join(' ')}
                {systemStatus.checks.issues.length > 1 && ` (+${systemStatus.checks.issues.length - 1} more)`}
                &nbsp;— See <strong>Settings</strong> for details.
              </div>
            </div>
          )}

          <Routes>
            <Route path="/" element={<Dashboard systemStatus={systemStatus} />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/process" element={<Process />} />
            <Route path="/profiles" element={<Profiles />} />
            <Route path="/profiles/:id" element={<ProfileDetail />} />
            <Route path="/settings" element={<SettingsPage systemStatus={systemStatus} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

function NavItem({
  to, icon, label, badge, exact
}: {
  to: string; icon: React.ReactNode; label: string; badge?: number; exact?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={exact}
      className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
    >
      <span className="icon">{icon}</span>
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="nav-badge">{badge}</span>
      )}
    </NavLink>
  )
}
