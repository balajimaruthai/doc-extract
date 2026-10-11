import { useEffect, useState } from 'react'
import { Cpu, HardDrive, Monitor, AlertTriangle, CheckCircle, ExternalLink } from 'lucide-react'
import { systemApi, type SystemStatus, type HardwareInfo, type ModelManagerStatus } from '../api/client'

interface Props {
  systemStatus: SystemStatus | null
}

export function SettingsPage({ systemStatus }: Props) {
  const [hardware, setHardware] = useState<HardwareInfo | null>(null)
  const [models, setModels] = useState<ModelManagerStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      systemApi.getHardware().then(setHardware),
      systemApi.getModels().then(setModels),
    ]).finally(() => setLoading(false))
  }, [])

  return (
    <div className="page" style={{ maxWidth: 800 }}>
      <div className="page-header">
        <h1 className="page-title">Settings &amp; Setup</h1>
        <p className="page-subtitle">Hardware profile, model manager, and system diagnostics</p>
      </div>

      {/* Setup Status */}
      {systemStatus && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 className="card-title" style={{ marginBottom: 12 }}>System Readiness</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <StatusRow ok={systemStatus.checks.tesseract_available}
              label="Tesseract OCR"
              detail={systemStatus.checks.tesseract_available
                ? systemStatus.checks.tesseract_version
                : 'Not installed. Run: conda install -c conda-forge tesseract'} />
            <StatusRow ok={systemStatus.checks.llm_available}
              label="Local AI Model (GGUF)"
              detail={systemStatus.checks.llm_available
                ? `Model: ${systemStatus.checks.llm_model_name}`
                : 'No model installed. See MODEL_SETUP.md'} />
            <StatusRow ok={systemStatus.checks.database_accessible}
              label="Database (SQLite)" detail="Local file-based storage" />
            <StatusRow ok={systemStatus.checks.uploads_writable}
              label="Uploads Directory" detail="Write access confirmed" />
            <StatusRow ok={false} label="External Network" detail="None — all processing is local" invertOk />
          </div>

          {systemStatus.checks.issues.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Issues to resolve:</div>
              {systemStatus.checks.issues.map((issue, i) => (
                <div key={i} className="alert alert-warning" style={{ marginBottom: 8 }}>
                  <AlertTriangle size={14} />{issue}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Model Manager */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h3 className="card-title" style={{ marginBottom: 4 }}>Local AI Model Manager</h3>
        <p className="text-muted text-sm" style={{ marginBottom: 16 }}>
          GGUF models must be installed manually before offline operation.
          Models are never downloaded automatically.
        </p>

        {loading ? <div className="spinner" /> : models ? (
          <>
            {models.setup_required && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                <AlertTriangle size={16} />
                <div>
                  <strong>No model installed.</strong> Place a GGUF model file in the{' '}
                  <code style={{ background: '#fff5f5', padding: '1px 4px', borderRadius: 3 }}>models/small/</code> directory.
                  <br />
                  <span className="text-sm">Recommended: <strong>Phi-3-mini-4k-instruct Q4_K_M</strong> (~2.2 GB) for this hardware</span>
                </div>
              </div>
            )}

            {models.models.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center' }}>
                <div className="text-muted">No GGUF models found in models/ directory</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {models.models.map(model => (
                  <div key={model.name} style={{
                    padding: 12, border: '1px solid var(--color-border)', borderRadius: 6,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    background: model.name === models.best_model ? 'var(--color-accent-light)' : 'var(--color-surface)'
                  }}>
                    <div>
                      <div style={{ fontWeight: 600 }}>{model.name}</div>
                      <div className="text-xs text-muted">
                        {model.tier} tier · {model.size_gb} GB · ~{model.estimated_ram_gb} GB RAM
                      </div>
                      {model.notes && <div className="text-xs" style={{ color: 'var(--color-warning)' }}>{model.notes}</div>}
                    </div>
                    <div className="flex items-center gap-sm">
                      {model.name === models.best_model && <span className="badge badge-info">Selected</span>}
                      <span className={`badge ${model.status === 'ready' ? 'badge-success' : 'badge-error'}`}>
                        {model.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ marginTop: 16, padding: 12, background: 'var(--color-surface-2)', borderRadius: 6, fontSize: 12 }}>
              <strong>To install a model:</strong>
              <ol style={{ marginTop: 6, paddingLeft: 20, lineHeight: 2 }}>
                <li>Download a GGUF model (e.g., from Hugging Face)</li>
                <li>Recommended: <code>phi-3-mini-4k-instruct-q4_k_m.gguf</code> (~2.2 GB)</li>
                <li>Place the <code>.gguf</code> file in: <code>models/small/</code></li>
                <li>Restart the application</li>
              </ol>
              <div style={{ marginTop: 8, color: 'var(--color-text-secondary)' }}>
                See <code>docs/MODEL_SETUP.md</code> for detailed offline installation instructions.
              </div>
            </div>
          </>
        ) : null}
      </div>

      {/* Hardware Info */}
      {hardware && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 className="card-title" style={{ marginBottom: 12 }}>Detected Hardware</h3>
          <div className="grid-2" style={{ gap: 12 }}>
            <HardwareItem icon={<Cpu size={16} />} label="CPU" value={hardware.cpu} sub={`${hardware.cpu_cores} cores`} />
            <HardwareItem icon={<HardDrive size={16} />} label="RAM" value={`${hardware.ram_total_gb} GB total`} sub={`Profile: ${hardware.profile}`} />
            {hardware.gpu && (
              <HardwareItem icon={<Monitor size={16} />} label="GPU" value={hardware.gpu.name}
                sub={`${(hardware.gpu.vram_mb / 1024).toFixed(1)} GB VRAM · CUDA: ${hardware.gpu.cuda_available ? 'Yes' : 'No'}`} />
            )}
            <HardwareItem icon={<CheckCircle size={16} />} label="Recommended Model Tier"
              value={hardware.recommended_model_tier.toUpperCase()} sub="Based on available RAM" />
          </div>
        </div>
      )}

      {/* Privacy */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: 12 }}>Privacy &amp; Security</h3>
        <div className="alert alert-success" style={{ marginBottom: 12 }}>
          <CheckCircle size={16} />
          <div>
            <strong>All processing is local.</strong> Documents are processed on this device only.
            No content, metadata, or personal information is transmitted to any external service.
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
          {[
            ['External Network Requests', 'None — fully offline after setup'],
            ['Telemetry', 'None'],
            ['Analytics', 'None'],
            ['Document Storage', 'Local disk only (data/uploads/)'],
            ['Model Inference', 'Local CPU/GPU — no cloud API'],
            ['OCR Processing', 'Local Tesseract — no cloud OCR'],
            ['Database', 'SQLite (local file — data/docextract.db)'],
          ].map(([label, value]) => (
            <div key={label} className="flex" style={{ padding: '4px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
              <span style={{ width: 200, color: 'var(--color-text-secondary)', fontWeight: 500 }}>{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatusRow({ ok, label, detail, invertOk }: { ok: boolean; label: string; detail: string; invertOk?: boolean }) {
  const isGood = invertOk ? !ok : ok
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
      {isGood ? <CheckCircle size={15} color="var(--color-success)" /> : <AlertTriangle size={15} color="var(--color-error)" />}
      <span style={{ width: 180, fontWeight: 500 }}>{label}</span>
      <span className="text-muted">{detail}</span>
    </div>
  )
}

function HardwareItem({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div style={{ padding: 12, background: 'var(--color-surface-2)', borderRadius: 6 }}>
      <div className="flex items-center gap-sm" style={{ marginBottom: 4, color: 'var(--color-accent)' }}>
        {icon}
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--color-text-secondary)' }}>{label}</span>
      </div>
      <div style={{ fontWeight: 600 }}>{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  )
}
