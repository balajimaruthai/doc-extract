import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, CheckCircle, AlertTriangle, Clock, Cpu } from 'lucide-react'
import { documentsApi, profilesApi, type DocumentStats, type SystemStatus } from '../api/client'

interface Props {
  systemStatus: SystemStatus | null
}

export function Dashboard({ systemStatus }: Props) {
  const [stats, setStats] = useState<DocumentStats | null>(null)
  const [profileCount, setProfileCount] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    documentsApi.stats().then(setStats).catch(console.error)
    profilesApi.list().then(r => setProfileCount(r.total)).catch(console.error)
  }, [])

  const issues = systemStatus?.checks.issues ?? []
  const ready = systemStatus?.checks.overall_ready ?? false

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Offline Document Intelligence — All processing performed locally</p>
      </div>

      {/* Setup Issues */}
      {issues.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="card" style={{ borderColor: '#ffc9c9', background: '#fff5f5' }}>
            <div className="card-header" style={{ marginBottom: 12 }}>
              <div className="flex items-center gap-sm">
                <AlertTriangle size={18} color="var(--color-error)" />
                <span className="card-title" style={{ color: 'var(--color-error)' }}>
                  Setup Required
                </span>
              </div>
            </div>
            <ul style={{ fontSize: 13, color: 'var(--color-error)', paddingLeft: 20 }}>
              {issues.map((issue, i) => <li key={i} style={{ marginBottom: 4 }}>{issue}</li>)}
            </ul>
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 12 }} onClick={() => navigate('/settings')}>
              View Setup Details
            </button>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <StatCard
          label="Documents"
          value={stats?.total ?? 0}
          icon={<FileText size={20} />}
          color="var(--color-info)"
          onClick={() => navigate('/documents')}
        />
        <StatCard
          label="Extracted Documents"
          value={(stats?.total ?? 0) - (stats?.pending ?? 0) - (stats?.failed ?? 0)}
          icon={<CheckCircle size={20} />}
          color="var(--color-success)"
          onClick={() => navigate('/documents')}
        />
        <StatCard
          label="Pending"
          value={stats?.pending ?? 0}
          icon={<Clock size={20} />}
          color="var(--color-warning)"
        />
        <StatCard
          label="Needs Review"
          value={(stats?.needs_review ?? 0) + (stats?.failed ?? 0)}
          icon={<AlertTriangle size={20} />}
          color="var(--color-error)"
        />
      </div>

      {/* Quick Actions */}
      <div className="grid-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: 12 }}>Quick Start</h3>
          <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginBottom: 16 }}>
            Upload any document (books, research papers, project reports, articles, scans, or notes) to extract structured intelligence locally.
          </p>
          <div className="flex gap-sm">
            <button className="btn btn-primary" onClick={() => navigate('/documents')}>
              <FileText size={14} /> Upload Documents
            </button>
            <button className="btn btn-secondary" onClick={() => navigate('/process')}>
              <Cpu size={14} /> Process &amp; Extract
            </button>
          </div>
        </div>

        {/* Privacy Statement */}
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: 12 }}>🔒 Privacy Statement</h3>
          <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
            Documents are processed <strong>locally on this device</strong>.
            No document content, personal information, or metadata is transmitted
            to any external service. All AI processing uses locally installed models.
          </p>
          <div className="flex gap-sm" style={{ marginTop: 12 }}>
            <span className="badge badge-success">No Internet Required</span>
            <span className="badge badge-success">No Telemetry</span>
            <span className="badge badge-success">No Cloud Processing</span>
          </div>
        </div>
      </div>

      {/* System Status */}
      {systemStatus && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: 12 }}>System Status</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <StatusRow
              label="Tesseract OCR"
              ok={systemStatus.checks.tesseract_available}
              detail={systemStatus.checks.tesseract_version || 'Not installed'}
            />
            <StatusRow
              label="Local AI Model"
              ok={systemStatus.checks.llm_available}
              detail={systemStatus.checks.llm_model_name || 'No model installed — see docs/MODEL_SETUP.md'}
            />
            <StatusRow
              label="Database"
              ok={systemStatus.checks.database_accessible}
              detail="SQLite (local)"
            />
            <StatusRow
              label="Network Access"
              ok={true}
              detail="None — fully offline"
              invertColor
            />
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({
  label, value, icon, color, onClick
}: {
  label: string; value: number; icon: React.ReactNode; color: string; onClick?: () => void
}) {
  return (
    <div
      className="card card-sm"
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <div className="flex items-center justify-between">
        <div>
          <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{label}</div>
        </div>
        <div style={{ color, opacity: 0.3 }}>{icon}</div>
      </div>
    </div>
  )
}

function StatusRow({
  label, ok, detail, invertColor
}: {
  label: string; ok: boolean; detail: string; invertColor?: boolean
}) {
  const color = invertColor
    ? (ok ? 'var(--color-success)' : 'var(--color-error)')
    : (ok ? 'var(--color-success)' : 'var(--color-error)')

  return (
    <div className="flex items-center gap-md" style={{ fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
      <span style={{ width: 160, fontWeight: 500 }}>{label}</span>
      <span className={`badge ${ok ? 'badge-success' : 'badge-error'}`}>
        {ok ? '✓ Ready' : '✗ Issue'}
      </span>
      <span className="text-muted">{detail}</span>
    </div>
  )
}
