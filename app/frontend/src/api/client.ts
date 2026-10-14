/**
 * API client — calls Python FastAPI backend on localhost only.
 * NO external network requests. All calls go to 127.0.0.1:37240.
 */

const BASE_URL = typeof window !== 'undefined' && window.location.origin.includes('1420') 
  ? 'http://127.0.0.1:37240/api/v1' 
  : '/api/v1'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || body.error || detail
    } catch {}
    throw new ApiError(response.status, detail)
  }

  return response.json()
}

// ─── System ────────────────────────────────────────────────
export const systemApi = {
  getStatus: () => request<SystemStatus>('/system/status'),
  getHardware: () => request<HardwareInfo>('/system/hardware'),
  getModels: () => request<ModelManagerStatus>('/system/models'),
  getPrivacy: () => request<PrivacyStatement>('/system/privacy'),
}

// ─── Documents ─────────────────────────────────────────────
export const documentsApi = {
  upload: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch(`${BASE_URL}/documents/upload`, {
      method: 'POST',
      body: form,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new ApiError(response.status, body.detail || body.message || `Upload failed (${response.status})`)
    }
    return response.json()
  },
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    if (params?.offset !== undefined) qs.set('offset', String(params.offset))
    return request<DocumentListResponse>(`/documents/?${qs}`)
  },
  get: (id: string) => request<DocumentRecord>(`/documents/${id}`),
  getText: (id: string) => request<{ pages: PageText[] }>(`/documents/${id}/text`),
  getFileUrl: (id: string) => `${BASE_URL}/documents/${id}/file`,
  getFinancialRecord: (id: string) => request<any>(`/documents/${id}/financial-record`),
  listFinancialRecords: () => request<{ records: any[]; total: number }>('/documents/financial-records'),
  delete: (id: string) => request<{ message: string }>(`/documents/${id}`, { method: 'DELETE' }),
  stats: () => request<DocumentStats>('/documents/stats/summary'),
}

// ─── Processing ────────────────────────────────────────────
export const processingApi = {
  start: (documentIds: string[], createProfile = true) =>
    request<ProcessingJob>('/processing/start', {
      method: 'POST',
      body: JSON.stringify({ document_ids: documentIds, create_profile: createProfile }),
    }),
  processSingle: (docId: string) =>
    request<{ status: string; message: string }>(`/processing/single/${docId}`, {
      method: 'POST',
    }),
  getStatus: (docId: string) => request<ProcessingStatus>(`/processing/status/${docId}`),
}

// ─── Profiles ──────────────────────────────────────────────
export const profilesApi = {
  list: () => request<{ profiles: ProfileSummary[]; total: number }>('/profiles/'),
  get: (id: string) => request<FullProfile>(`/profiles/${id}`),
  getConflicts: (id: string) => request<{ conflicts: Conflict[] }>(`/profiles/${id}/conflicts`),
  resolveConflict: (profileId: string, conflictId: string, resolvedValue: string) =>
    request(`/profiles/${profileId}/conflicts/${conflictId}/resolve`, {
      method: 'PATCH',
      body: JSON.stringify({ resolved_value: resolvedValue }),
    }),
  correctField: (profileId: string, field: string, value: string, section: string, recordId?: string) =>
    request(`/profiles/${profileId}/correct`, {
      method: 'PATCH',
      body: JSON.stringify({ field, value, section, record_id: recordId }),
    }),
}

// ─── Export ────────────────────────────────────────────────
export const exportApi = {
  exportJson: (profileId: string) => `${BASE_URL}/export/${profileId}/json`,
  exportCsv: (profileId: string) => `${BASE_URL}/export/${profileId}/csv`,
  exportPdf: (profileId: string) => `${BASE_URL}/export/${profileId}/pdf`,

  downloadFile: async (url: string, filename: string) => {
    const response = await fetch(url)
    if (!response.ok) throw new ApiError(response.status, 'Export failed')
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = filename
    a.click()
    URL.revokeObjectURL(objectUrl)
  },
}

// ─── Types ─────────────────────────────────────────────────
export interface SystemStatus {
  status: 'ready' | 'setup_required'
  offline_mode: boolean
  version: string
  checks: {
    tesseract_available: boolean
    tesseract_version: string
    llm_available: boolean
    llm_model_name: string
    database_accessible: boolean
    uploads_writable: boolean
    overall_ready: boolean
    issues: string[]
  }
}

export interface HardwareInfo {
  os: string
  cpu: string
  cpu_cores: number
  ram_total_gb: number
  gpu?: { name: string; vram_mb: number; cuda_available: boolean } | null
  profile: string
  recommended_model_tier: string
}

export interface ModelManagerStatus {
  models: ModelInfo[]
  best_model: string | null
  has_any_model: boolean
  setup_required: boolean
  setup_instructions: string
}

export interface ModelInfo {
  name: string
  size_gb: number
  tier: string
  estimated_ram_gb: number
  status: 'ready' | 'missing' | 'too_large'
  notes: string
}

export interface PrivacyStatement {
  statement: string
  network_access: boolean
  telemetry: boolean
}

export interface DocumentRecord {
  id: string
  original_filename: string
  file_type: string
  file_size: number
  processing_status: 'pending' | 'processing' | 'completed' | 'failed' | 'review'
  document_type: string | null
  classification_confidence: string | null
  page_count: number | null
  ocr_performed: number
  upload_timestamp: string
  error_message: string | null
  content_hash: string
  metadata_json?: string | null
}

export interface DocumentListResponse {
  documents: DocumentRecord[]
  total: number
}

export interface DocumentStats {
  total: number
  pending: number
  completed: number
  failed: number
  needs_review: number
}

export interface PageText {
  page_number: number
  extraction_method: string
  cleaned_text: string
  ocr_confidence: number | null
}

export interface ProcessingJob {
  job_id: string
  status: string
  document_count: number
}

export interface ProcessingStatus {
  document_id: string
  status: string
  document_type: string | null
  page_count: number | null
  error_message: string | null
  processing_stages: ProcessingStage[]
}

export interface ProcessingStage {
  stage: string
  status: string
  started_at: string
  completed_at: string | null
  duration_ms: number | null
  error_reason: string | null
}

export interface ProfileSummary {
  id: string
  full_name: string | null
  email: string | null
  estimated_experience_level: string | null
  total_documented_experience_months: number | null
  created_at: string
}

export interface FullProfile {
  id: string
  full_name: string | null
  email: string | null
  phone: string | null
  location: string | null
  date_of_birth: string | null
  professional_summary: string | null
  estimated_experience_level: string | null
  estimated_experience_basis: string | null
  total_documented_experience_months: number | null
  education: EducationRecord[]
  experience: ExperienceRecord[]
  skills: Record<string, string[]>
  certifications: CertificationRecord[]
  projects: ProjectRecord[]
  achievements: AchievementRecord[]
  conflicts: Conflict[]
  documents: LinkedDocument[]
  conflict_count: number
}

export interface EducationRecord {
  id: string
  degree: string | null
  specialization: string | null
  institution: string | null
  university: string | null
  graduation_date: string | null
  cgpa: number | null
  percentage: number | null
  confidence_level: string | null
  user_corrected: number
}

export interface ExperienceRecord {
  id: string
  company: string | null
  designation: string | null
  start_date: string | null
  end_date: string | null
  is_current: number
  responsibilities: string[]
  duration_months: number | null
  confidence_level: string | null
  user_corrected: number
}

export interface CertificationRecord {
  id: string
  name: string | null
  issuer: string | null
  issue_date: string | null
  expiry_date: string | null
  credential_id: string | null
}

export interface ProjectRecord {
  id: string
  name: string | null
  description: string | null
  technologies: string[]
}

export interface AchievementRecord {
  id: string
  title: string | null
  organization: string | null
  date: string | null
  description: string | null
}

export interface Conflict {
  id: string
  field_name: string
  value_a: string | null
  source_a_document_id: string | null
  source_a_page: number | null
  value_b: string | null
  source_b_document_id: string | null
  source_b_page: number | null
  resolution: 'unresolved' | 'user_resolved' | 'auto_resolved'
  resolved_value: string | null
}

export interface LinkedDocument {
  id: string
  original_filename: string
  document_type: string | null
  processing_status: string
}
