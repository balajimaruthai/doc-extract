import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, ChevronRight } from 'lucide-react'
import { profilesApi, type ProfileSummary } from '../api/client'

export function Profiles() {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    profilesApi.list().then(r => { setProfiles(r.profiles); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const formatExperience = (months: number | null) => {
    if (!months) return '—'
    const y = Math.floor(months / 12)
    const m = months % 12
    return y > 0 ? `${y}y ${m}m` : `${m}m`
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Profiles</h1>
        <p className="page-subtitle">Consolidated professional profiles generated from documents</p>
      </div>

      {loading ? (
        <div className="flex items-center gap-sm" style={{ padding: 32 }}>
          <div className="spinner" /> Loading profiles…
        </div>
      ) : profiles.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <User size={32} style={{ color: 'var(--color-text-muted)', marginBottom: 12 }} />
          <div style={{ fontWeight: 600, marginBottom: 4 }}>No profiles yet</div>
          <div className="text-muted text-sm">Process documents to generate a consolidated profile</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {profiles.map(profile => (
            <div
              key={profile.id}
              className="card"
              onClick={() => navigate(`/profiles/${profile.id}`)}
              style={{ cursor: 'pointer', transition: 'box-shadow 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.boxShadow = 'var(--shadow-md)')}
              onMouseLeave={e => (e.currentTarget.style.boxShadow = 'var(--shadow-sm)')}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-md">
                  <div style={{
                    width: 40, height: 40, borderRadius: '50%',
                    background: 'var(--color-accent-light)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'var(--color-accent)', fontWeight: 700, fontSize: 16
                  }}>
                    {(profile.full_name || '?')[0].toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600 }}>{profile.full_name || 'Unknown Candidate'}</div>
                    <div className="text-muted text-sm">{profile.email || 'No email'}</div>
                  </div>
                </div>
                <div className="flex items-center gap-md">
                  {profile.estimated_experience_level && (
                    <span className="badge badge-info">{profile.estimated_experience_level}</span>
                  )}
                  <div style={{ textAlign: 'right' }}>
                    <div className="text-sm" style={{ fontWeight: 500 }}>
                      {formatExperience(profile.total_documented_experience_months)}
                    </div>
                    <div className="text-xs text-muted">experience</div>
                  </div>
                  <ChevronRight size={16} style={{ color: 'var(--color-text-muted)' }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
