import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Download, AlertTriangle, CheckCircle, Edit2, Save, X,
  FileText, User, GraduationCap, Briefcase, Code2, Award, BookOpen, ChevronDown, ChevronUp
} from 'lucide-react'
import {
  profilesApi, exportApi,
  type FullProfile, type EducationRecord, type ExperienceRecord, type Conflict
} from '../api/client'

export function ProfileDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [profile, setProfile] = useState<FullProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingField, setEditingField] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['personal', 'experience', 'education', 'skills'])
  )

  const load = async () => {
    if (!id) return
    try {
      const p = await profilesApi.get(id)
      setProfile(p)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  const toggleSection = (s: string) => setExpandedSections(prev => {
    const n = new Set(prev)
    n.has(s) ? n.delete(s) : n.add(s)
    return n
  })

  const startEdit = (fieldKey: string, currentValue: string) => {
    setEditingField(fieldKey)
    setEditValue(currentValue || '')
  }

  const saveEdit = async (fieldKey: string, section: string, field: string, recordId?: string) => {
    if (!id) return
    setSaving(true)
    try {
      await profilesApi.correctField(id, field, editValue, section, recordId)
      setEditingField(null)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const resolveConflict = async (conflictId: string, value: string) => {
    if (!id) return
    try {
      await profilesApi.resolveConflict(id, conflictId, value)
      await load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const exportPdf = async () => {
    if (!id) return
    try {
      await exportApi.downloadFile(exportApi.exportPdf(id), `profile_${id.slice(0, 8)}.pdf`)
    } catch (e: any) { setError(e.message) }
  }

  const exportJson = async () => {
    if (!id) return
    try {
      await exportApi.downloadFile(exportApi.exportJson(id), `profile_${id.slice(0, 8)}.json`)
    } catch (e: any) { setError(e.message) }
  }

  const formatExp = (months: number | null) => {
    if (!months) return '—'
    const y = Math.floor(months / 12), m = months % 12
    return y > 0 ? `${y} year${y !== 1 ? 's' : ''} ${m} month${m !== 1 ? 's' : ''}` : `${m} month${m !== 1 ? 's' : ''}`
  }

  if (loading) return (
    <div className="page flex items-center gap-sm" style={{ paddingTop: 48 }}>
      <div className="spinner" /> Loading profile…
    </div>
  )
  if (error) return (
    <div className="page">
      <div className="alert alert-error"><AlertTriangle size={16} /> {error}</div>
    </div>
  )
  if (!profile) return null

  const unresolved = profile.conflicts.filter(c => c.resolution === 'unresolved')

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
        <div className="flex items-center gap-md">
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/profiles')}>
            <ArrowLeft size={13} /> Profiles
          </button>
          <div>
            <h1 className="page-title">{profile.full_name || 'Unknown Candidate'}</h1>
            <p className="page-subtitle">{profile.email} {profile.phone ? `· ${profile.phone}` : ''}</p>
          </div>
        </div>
        <div className="flex gap-sm">
          <button className="btn btn-secondary btn-sm" onClick={exportJson}>
            <Download size={13} /> JSON
          </button>
          <button className="btn btn-secondary btn-sm" onClick={exportPdf}>
            <Download size={13} /> PDF Report
          </button>
        </div>
      </div>

      {/* Conflict Banner */}
      {unresolved.length > 0 && (
        <div className="alert alert-warning" style={{ marginBottom: 24 }}>
          <AlertTriangle size={16} />
          <div>
            <strong>{unresolved.length} unresolved conflict{unresolved.length !== 1 ? 's' : ''} detected</strong>
            {' '}between documents. Review below before exporting.
          </div>
        </div>
      )}

      {error && <div className="alert alert-error" style={{ marginBottom: 16 }}><AlertTriangle size={16}/> {error}</div>}

      {/* Experience Level Card */}
      {profile.estimated_experience_level && (
        <div className="card" style={{ marginBottom: 20, background: 'var(--color-accent-light)', borderColor: '#a5d8ff' }}>
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-accent)', marginBottom: 4 }}>
                Estimated Professional Level
              </div>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--color-accent)' }}>
                {profile.estimated_experience_level}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>
                {profile.estimated_experience_basis}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: 'var(--color-accent)', fontWeight: 600, marginBottom: 4 }}>
                DOCUMENTED EXPERIENCE
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--color-accent)' }}>
                {formatExp(profile.total_documented_experience_months)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                From {profile.experience.length} position{profile.experience.length !== 1 ? 's' : ''}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Personal Information ─────────────────────────── */}
      <Section
        id="personal" title="Personal Information" icon={<User size={15} />}
        expanded={expandedSections.has('personal')} onToggle={() => toggleSection('personal')}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <EditableField label="Full Name" value={profile.full_name} fieldKey="personal.full_name"
            editingField={editingField} editValue={editValue} setEditValue={setEditValue}
            onEdit={() => startEdit('personal.full_name', profile.full_name || '')}
            onSave={() => saveEdit('personal.full_name', 'personal', 'full_name')}
            onCancel={() => setEditingField(null)} saving={saving} />
          <EditableField label="Email" value={profile.email} fieldKey="personal.email"
            editingField={editingField} editValue={editValue} setEditValue={setEditValue}
            onEdit={() => startEdit('personal.email', profile.email || '')}
            onSave={() => saveEdit('personal.email', 'personal', 'email')}
            onCancel={() => setEditingField(null)} saving={saving} />
          <EditableField label="Phone" value={profile.phone} fieldKey="personal.phone"
            editingField={editingField} editValue={editValue} setEditValue={setEditValue}
            onEdit={() => startEdit('personal.phone', profile.phone || '')}
            onSave={() => saveEdit('personal.phone', 'personal', 'phone')}
            onCancel={() => setEditingField(null)} saving={saving} />
          <EditableField label="Location" value={profile.location} fieldKey="personal.location"
            editingField={editingField} editValue={editValue} setEditValue={setEditValue}
            onEdit={() => startEdit('personal.location', profile.location || '')}
            onSave={() => saveEdit('personal.location', 'personal', 'location')}
            onCancel={() => setEditingField(null)} saving={saving} />
        </div>
        {profile.professional_summary && (
          <div style={{ marginTop: 16, padding: 12, background: 'var(--color-surface-2)', borderRadius: 6, fontSize: 13, lineHeight: 1.7 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-secondary)', marginBottom: 6, textTransform: 'uppercase' }}>Professional Summary</div>
            {profile.professional_summary}
          </div>
        )}
      </Section>

      {/* ── Experience ────────────────────────────────────── */}
      <Section
        id="experience" title="Professional Experience" icon={<Briefcase size={15} />}
        expanded={expandedSections.has('experience')} onToggle={() => toggleSection('experience')}
        badge={profile.experience.length}
      >
        {profile.experience.length === 0 ? (
          <div className="text-muted text-sm">No experience records extracted.</div>
        ) : (
          profile.experience.map((exp, i) => (
            <ExperienceCard key={exp.id} exp={exp} index={i} formatExp={formatExp} />
          ))
        )}
      </Section>

      {/* ── Education ─────────────────────────────────────── */}
      <Section
        id="education" title="Education" icon={<GraduationCap size={15} />}
        expanded={expandedSections.has('education')} onToggle={() => toggleSection('education')}
        badge={profile.education.length}
      >
        {profile.education.length === 0 ? (
          <div className="text-muted text-sm">No education records extracted.</div>
        ) : (
          profile.education.map(edu => <EducationCard key={edu.id} edu={edu} />)
        )}
      </Section>

      {/* ── Skills ────────────────────────────────────────── */}
      <Section
        id="skills" title="Skills" icon={<Code2 size={15} />}
        expanded={expandedSections.has('skills')} onToggle={() => toggleSection('skills')}
      >
        {Object.entries(profile.skills).every(([, v]) => v.length === 0) ? (
          <div className="text-muted text-sm">No skills extracted.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.entries(profile.skills).filter(([, v]) => v.length > 0).map(([cat, skills]) => (
              <div key={cat} className="flex" style={{ gap: 12, alignItems: 'flex-start' }}>
                <div style={{ width: 160, fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'capitalize', flexShrink: 0, paddingTop: 2 }}>
                  {cat.replace(/_/g, ' ')}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {skills.map(skill => (
                    <span key={skill} style={{
                      background: 'var(--color-surface-2)', border: '1px solid var(--color-border)',
                      borderRadius: 4, padding: '2px 8px', fontSize: 12, fontWeight: 500
                    }}>{skill}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── Certifications ────────────────────────────────── */}
      {profile.certifications.length > 0 && (
        <Section
          id="certs" title="Certifications" icon={<Award size={15} />}
          expanded={expandedSections.has('certs')} onToggle={() => toggleSection('certs')}
          badge={profile.certifications.length}
        >
          {profile.certifications.map(cert => (
            <div key={cert.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
              <div style={{ fontWeight: 600 }}>{cert.name || '—'}</div>
              <div className="text-muted text-sm">
                {cert.issuer} {cert.issue_date ? `· Issued: ${cert.issue_date}` : ''}
                {cert.credential_id ? ` · ID: ${cert.credential_id}` : ''}
              </div>
            </div>
          ))}
        </Section>
      )}

      {/* ── Conflicts ─────────────────────────────────────── */}
      {profile.conflicts.length > 0 && (
        <Section
          id="conflicts" title="Detected Conflicts" icon={<AlertTriangle size={15} />}
          expanded={expandedSections.has('conflicts')} onToggle={() => toggleSection('conflicts')}
          badge={unresolved.length} badgeClass="badge-error"
        >
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginBottom: 12 }}>
            These fields have conflicting values across your documents. Review the sources and choose the correct value.
          </div>
          {profile.conflicts.map(conflict => (
            <ConflictCard key={conflict.id} conflict={conflict} onResolve={resolveConflict} />
          ))}
        </Section>
      )}

      {/* ── Source Documents ──────────────────────────────── */}
      <Section
        id="documents" title="Source Documents" icon={<FileText size={15} />}
        expanded={expandedSections.has('documents')} onToggle={() => toggleSection('documents')}
      >
        {profile.documents.map(doc => (
          <div key={doc.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--color-border-subtle)', display: 'flex', alignItems: 'center', gap: 12 }}>
            <FileText size={14} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 500 }}>{doc.original_filename}</div>
              <div className="text-xs text-muted">{doc.document_type || 'Unknown type'}</div>
            </div>
            <span className={`badge ${doc.processing_status === 'completed' ? 'badge-success' : 'badge-neutral'}`}>
              {doc.processing_status}
            </span>
          </div>
        ))}
      </Section>
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────

function Section({ id, title, icon, expanded, onToggle, children, badge, badgeClass }: {
  id: string; title: string; icon: React.ReactNode; expanded: boolean; onToggle: () => void;
  children: React.ReactNode; badge?: number; badgeClass?: string
}) {
  return (
    <div className="card" style={{ marginBottom: 16, padding: 0, overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{
          width: '100%', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 10,
          background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
          borderBottom: expanded ? '1px solid var(--color-border)' : 'none'
        }}
      >
        <span style={{ color: 'var(--color-accent)' }}>{icon}</span>
        <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{title}</span>
        {badge !== undefined && badge > 0 && (
          <span className={`badge ${badgeClass || 'badge-neutral'}`}>{badge}</span>
        )}
        {expanded ? <ChevronUp size={16} style={{ color: 'var(--color-text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--color-text-muted)' }} />}
      </button>
      {expanded && <div style={{ padding: '16px 20px' }}>{children}</div>}
    </div>
  )
}

function EditableField({ label, value, fieldKey, editingField, editValue, setEditValue, onEdit, onSave, onCancel, saving }: {
  label: string; value: string | null; fieldKey: string;
  editingField: string | null; editValue: string; setEditValue: (v: string) => void;
  onEdit: () => void; onSave: () => void; onCancel: () => void; saving: boolean
}) {
  const isEditing = editingField === fieldKey
  return (
    <div className="field-row" style={{ alignItems: 'center' }}>
      <span className="field-label">{label}</span>
      {isEditing ? (
        <div className="flex items-center gap-sm" style={{ flex: 1 }}>
          <input
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            style={{ flex: 1 }}
            autoFocus
            onKeyDown={e => { if (e.key === 'Enter') onSave(); if (e.key === 'Escape') onCancel() }}
          />
          <button className="btn btn-primary btn-sm" onClick={onSave} disabled={saving}>
            {saving ? <div className="spinner" style={{ width: 12, height: 12 }} /> : <Save size={12} />}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={onCancel}><X size={12} /></button>
        </div>
      ) : (
        <>
          <span className="field-value">{value || <span className="text-muted">—</span>}</span>
          <button className="btn btn-icon btn-secondary btn-sm" onClick={onEdit} style={{ marginLeft: 'auto', opacity: 0.5 }}>
            <Edit2 size={12} />
          </button>
          {value && <span className="field-status status-extracted">Extracted</span>}
        </>
      )}
    </div>
  )
}

function ExperienceCard({ exp, index, formatExp }: { exp: ExperienceRecord; index: number; formatExp: (m: number | null) => string }) {
  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-center justify-between">
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{exp.designation || 'Unknown Role'}</div>
          <div style={{ fontWeight: 500, color: 'var(--color-accent)' }}>{exp.company || 'Unknown Company'}</div>
          <div className="text-muted text-sm" style={{ marginTop: 2 }}>
            {exp.start_date || '?'} → {exp.is_current ? <strong>Present</strong> : (exp.end_date || '?')}
            {exp.duration_months && ` (${formatExp(exp.duration_months)})`}
          </div>
        </div>
        <div className="flex gap-sm">
          {exp.is_current === 1 && <span className="badge badge-success">Current</span>}
          {exp.user_corrected === 1 && <span className="badge badge-warning">User Edited</span>}
          {exp.confidence_level && <span className={`badge badge-${exp.confidence_level === 'high' ? 'success' : exp.confidence_level === 'low' ? 'error' : 'neutral'}`}>{exp.confidence_level}</span>}
        </div>
      </div>
      {exp.responsibilities && exp.responsibilities.length > 0 && (
        <ul style={{ marginTop: 8, paddingLeft: 16, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          {exp.responsibilities.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
    </div>
  )
}

function EducationCard({ edu }: { edu: EducationRecord }) {
  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div style={{ fontWeight: 600 }}>
        {edu.degree || '—'}{edu.specialization ? ` — ${edu.specialization}` : ''}
      </div>
      <div style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>
        {edu.institution || edu.university || '—'}
        {edu.graduation_date ? ` · Graduated: ${edu.graduation_date}` : ''}
      </div>
      <div className="text-muted text-sm">
        {edu.cgpa && `CGPA: ${edu.cgpa}`}
        {edu.percentage && `Percentage: ${edu.percentage}%`}
        {edu.user_corrected === 1 && <span className="badge badge-warning" style={{ marginLeft: 6 }}>User Edited</span>}
      </div>
    </div>
  )
}

function ConflictCard({ conflict, onResolve }: { conflict: Conflict; onResolve: (id: string, value: string) => void }) {
  const resolved = conflict.resolution !== 'unresolved'
  return (
    <div className={`conflict-card ${resolved ? '' : ''}`} style={{ marginBottom: 12, opacity: resolved ? 0.6 : 1 }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>
          {resolved ? '✓ ' : '⚠ '} Field: <code style={{ background: '#f1f3f5', padding: '1px 4px', borderRadius: 3 }}>{conflict.field_name}</code>
        </div>
        {resolved && <span className="badge badge-success">Resolved: {conflict.resolved_value}</span>}
      </div>
      <div className="conflict-values">
        <div className="conflict-value">
          <div className="text-xs text-muted" style={{ marginBottom: 4 }}>Source A · Document {conflict.source_a_document_id?.slice(0, 8)}</div>
          <div style={{ fontWeight: 600 }}>{conflict.value_a || '—'}</div>
          {!resolved && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }}
              onClick={() => onResolve(conflict.id, conflict.value_a || '')}>
              Use This Value
            </button>
          )}
        </div>
        <div className="conflict-value">
          <div className="text-xs text-muted" style={{ marginBottom: 4 }}>Source B · Document {conflict.source_b_document_id?.slice(0, 8)}</div>
          <div style={{ fontWeight: 600 }}>{conflict.value_b || '—'}</div>
          {!resolved && (
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }}
              onClick={() => onResolve(conflict.id, conflict.value_b || '')}>
              Use This Value
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
