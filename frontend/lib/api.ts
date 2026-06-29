const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface AuthResponse {
  tenant_id: string;
  name: string;
  api_key: string;
  access_token: string;
  token_type: string;
}

export interface TenantInfo {
  tenant_id: string;
  name: string;
}

export interface Source {
  file: string;
  page: number | null;
}

export interface ChatRequest {
  session_id?: string;
  message: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sources: Source[];
  tools_used: string[];
}

export interface IngestResponse {
  status: string;
  filename: string;
  message: string;
}

export interface DocumentInfo {
  filename: string;
  size_bytes: number;
  uploaded_at: string;
  updated_at: string | null;
  chunk_count: number | null;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total: number;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("api_key");
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail)
    );
  }
  return res.json() as Promise<T>;
}

export async function register(
  company_name: string,
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name, email, password }),
  });
  return handleResponse<AuthResponse>(res);
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<AuthResponse>(res);
}

export async function getTenant(): Promise<TenantInfo> {
  const res = await fetch(`${API_BASE}/v1/tenant`, {
    headers: authHeaders(),
  });
  return handleResponse<TenantInfo>(res);
}

export async function chat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(req),
  });
  return handleResponse<ChatResponse>(res);
}

export async function clearSession(session_id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/v1/session/${session_id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to clear session: ${res.statusText}`);
  }
}

export async function ingestDocument(file: File): Promise<IngestResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch(`${API_BASE}/v1/ingest`, {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });
  return handleResponse<IngestResponse>(res);
}

export async function listDocuments(): Promise<DocumentListResponse> {
  const res = await fetch(`${API_BASE}/v1/documents`, {
    headers: authHeaders(),
  });
  return handleResponse<DocumentListResponse>(res);
}

export async function replaceDocument(
  filename: string,
  file: File
): Promise<IngestResponse> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch(
    `${API_BASE}/v1/documents/${encodeURIComponent(filename)}`,
    {
      method: "PUT",
      headers: authHeaders(),
      body: fd,
    }
  );
  return handleResponse<IngestResponse>(res);
}

export async function deleteDocument(filename: string): Promise<IngestResponse> {
  const res = await fetch(
    `${API_BASE}/v1/documents/${encodeURIComponent(filename)}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    }
  );
  return handleResponse<IngestResponse>(res);
}
