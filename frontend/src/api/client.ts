import type {
  AuthTokenResponse,
  ProfessorProfile,
  SearchRequest,
  SearchResponse,
  StudentAchievement,
  StudentAchievementInput,
  StudentAuthSummary,
  StudentCompleteProfile,
  StudentDeleteResponse,
  StudentEducation,
  StudentEducationInput,
  StudentExperience,
  StudentExperienceInput,
  StudentMutationResponse,
  StudentPersonalInfoUpdate,
  StudentProject,
  StudentProjectInput,
  StudentPublication,
  StudentPublicationInput,
  StudentSkill,
  StudentSkillInput,
  TailoredResumeExportRequest,
  TailoredResumeGenerateRequest,
  TailoredResumeGenerateResponse,
} from "../types/api";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") || "http://127.0.0.1:8000";

export const SEARCH_TIMEOUT_MS = 180_000;
export const PROFILE_TIMEOUT_MS = 30_000;

const AUTH_TOKEN_STORAGE_KEY = "scholarlink_auth_token";

export function getStoredAuthToken(): string | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY) : null;
  } catch {
    return null;
  }
}

export function setStoredAuthToken(token: string): void {
  try {
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    }
  } catch {
    /* ignore storage errors */
  }
}

export function clearStoredAuthToken(): void {
  try {
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
  } catch {
    /* ignore storage errors */
  }
}

export type ApiErrorKind =
  | "validation"
  | "unauthorized"
  | "conflict"
  | "not_found"
  | "unavailable"
  | "server"
  | "timeout"
  | "network"
  | "aborted"
  | "unknown";

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind, message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

function extractValidationDetail(detail: unknown): string | undefined {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown; loc?: unknown };
    if (typeof first?.msg === "string" && first.msg.trim()) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
      return field && typeof field === "string" ? `${field.replace(/_/g, " ")}: ${first.msg}` : first.msg;
    }
  }
  return undefined;
}

export function describeHttpError(status: number, detail?: unknown): ApiError {
  const detailText = typeof detail === "string" ? detail : undefined;
  if (status === 401) {
    return new ApiError("unauthorized", detailText || "Your session has expired. Please sign in again.", status);
  }
  if (status === 404) {
    return new ApiError("not_found", detailText || "The requested resource was not found.", status);
  }
  if (status === 409) {
    return new ApiError("conflict", detailText || "This record already exists.", status);
  }
  if (status === 422) {
    return new ApiError(
      "validation",
      extractValidationDetail(detail) || "Please enter a valid research topic (it cannot be empty).",
      status,
    );
  }
  if (status === 503) {
    return new ApiError(
      "unavailable",
      detailText || "The service is temporarily unavailable. Please make sure the backend and database are running.",
      status,
    );
  }
  if (status >= 500) {
    return new ApiError("server", "The server encountered an unexpected error. Please try again.", status);
  }
  return new ApiError("unknown", detailText || `Request failed with status ${status}.`, status);
}

interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}

export async function searchProfessors(req: SearchRequest, opts: RequestOptions = {}): Promise<SearchResponse> {
  const query = (req.query || "").trim();
  if (!query) throw new ApiError("validation", "Please enter a research topic to search.");

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? SEARCH_TIMEOUT_MS);
  const onExternalAbort = () => controller.abort();
  if (opts.signal?.aborted) {
    controller.abort();
  } else {
    opts.signal?.addEventListener("abort", onExternalAbort);
  }

  const body: SearchRequest = {
    query,
    limit: req.limit === undefined ? 20 : req.limit,
    use_expansion: req.use_expansion ?? true,
    include_candidate_publications: req.include_candidate_publications ?? true,
    ...(req.offset !== undefined && req.offset > 0 ? { offset: req.offset } : {}),
    ...(req.university_id != null ? { university_id: req.university_id } : {}),
    ...(req.department_ids ? { department_ids: req.department_ids } : {}),
    ...(req.request_id ? { request_id: req.request_id } : {}),
  };

  try {
    const res = await (opts.fetchImpl ?? fetch)(`${API_BASE_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = (await res.json())?.detail;
      } catch {
        /* ignore */
      }
      throw describeHttpError(res.status, detail);
    }
    return (await res.json()) as SearchResponse;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error)?.name === "AbortError") {
      if (timedOut) throw new ApiError("timeout", "The search took too long to respond. Please try again.");
      throw new ApiError("aborted", "Search cancelled. You can start a new search.");
    }
    throw new ApiError("network", `Cannot reach the backend at ${API_BASE_URL}. Is the FastAPI server running?`);
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
  }
}

/**
 * Best-effort notification to the FastAPI backend to cooperatively cancel an
 * in-flight search request between processing stages. Never throws or blocks UI.
 */
export function cancelSearchRequest(requestId: string, fetchImpl: typeof fetch = fetch): void {
  const id = (requestId || "").trim();
  if (!id) return;
  try {
    void fetchImpl(`${API_BASE_URL}/search/cancel/${encodeURIComponent(id)}`, {
      method: "POST",
      keepalive: true,
    }).catch(() => {
      /* ignore best-effort backend cancel errors */
    });
  } catch {
    /* ignore */
  }
}

const profileCache = new Map<number, ProfessorProfile>();

export function clearProfessorProfileCache(): void {
  profileCache.clear();
}

export async function getProfessorProfile(
  professorId: number,
  opts: RequestOptions & { bypassCache?: boolean } = {},
): Promise<ProfessorProfile> {
  if (!Number.isInteger(professorId) || professorId <= 0) {
    throw new ApiError("not_found", "Invalid professor ID.", 404);
  }

  if (!opts.bypassCache) {
    const cached = profileCache.get(professorId);
    if (cached) return cached;
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? PROFILE_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort();
  if (opts.signal?.aborted) {
    controller.abort();
  } else {
    opts.signal?.addEventListener("abort", onExternalAbort);
  }

  try {
    const res = await (opts.fetchImpl ?? fetch)(`${API_BASE_URL}/professors/${professorId}/profile`, {
      method: "GET",
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = (await res.json())?.detail;
      } catch {
        /* ignore */
      }
      throw describeHttpError(res.status, detail);
    }
    const profile = (await res.json()) as ProfessorProfile;
    profileCache.set(professorId, profile);
    return profile;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error)?.name === "AbortError") {
      if (timedOut) throw new ApiError("timeout", "Loading the professor profile timed out. Please try again.");
      throw new ApiError("aborted", "Profile request was cancelled.");
    }
    throw new ApiError("network", `Cannot reach the backend at ${API_BASE_URL}. Is the FastAPI server running?`);
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
  }
}

// =========================================================================
// Stage 5.2 / 5.3: Authenticated Student & Academic Profile API Helpers
// =========================================================================

async function apiJsonRequest<T>(
  path: string,
  init: {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: unknown;
    requireAuth?: boolean;
    token?: string | null;
    opts?: RequestOptions;
  } = {},
): Promise<T> {
  const { method = "GET", body, requireAuth = false, opts = {} } = init;
  const token = init.token !== undefined ? init.token : getStoredAuthToken();

  if (requireAuth && !token) {
    throw new ApiError("unauthorized", "Please sign in to access your academic profile.", 401);
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? PROFILE_TIMEOUT_MS);

  const onExternalAbort = () => controller.abort();
  if (opts.signal?.aborted) {
    controller.abort();
  } else {
    opts.signal?.addEventListener("abort", onExternalAbort);
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await (opts.fetchImpl ?? fetch)(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = (await res.json())?.detail;
      } catch {
        /* ignore */
      }
      throw describeHttpError(res.status, detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error)?.name === "AbortError") {
      if (timedOut) throw new ApiError("timeout", "The request timed out. Please try again.");
      throw new ApiError("aborted", "Request was cancelled.");
    }
    throw new ApiError("network", `Cannot reach the backend at ${API_BASE_URL}. Is the FastAPI server running?`);
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
  }
}

// --- Auth ---

export function registerStudent(
  email: string,
  password: string,
  opts?: RequestOptions,
): Promise<AuthTokenResponse> {
  return apiJsonRequest<AuthTokenResponse>("/auth/register", {
    method: "POST",
    body: { email, password },
    token: null,
    opts,
  });
}

export function loginStudent(
  email: string,
  password: string,
  opts?: RequestOptions,
): Promise<AuthTokenResponse> {
  return apiJsonRequest<AuthTokenResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    token: null,
    opts,
  });
}

export function getCurrentStudent(opts?: RequestOptions): Promise<StudentAuthSummary> {
  return apiJsonRequest<StudentAuthSummary>("/auth/me", {
    method: "GET",
    requireAuth: true,
    opts,
  });
}

// --- Student Academic Profile CRUD ---

export function getStudentProfile(opts?: RequestOptions): Promise<StudentCompleteProfile> {
  return apiJsonRequest<StudentCompleteProfile>("/student/profile", {
    method: "GET",
    requireAuth: true,
    opts,
  });
}

export function updateStudentPersonalInfo(
  payload: StudentPersonalInfoUpdate,
  opts?: RequestOptions,
): Promise<StudentCompleteProfile> {
  return apiJsonRequest<StudentCompleteProfile>("/student/profile", {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function createEducation(
  payload: StudentEducationInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentEducation>> {
  return apiJsonRequest<StudentMutationResponse<StudentEducation>>("/student/profile/educations", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updateEducation(
  id: number,
  payload: StudentEducationInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentEducation>> {
  return apiJsonRequest<StudentMutationResponse<StudentEducation>>(`/student/profile/educations/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deleteEducation(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/educations/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

export function createSkill(
  payload: StudentSkillInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentSkill>> {
  return apiJsonRequest<StudentMutationResponse<StudentSkill>>("/student/profile/skills", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updateSkill(
  id: number,
  payload: StudentSkillInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentSkill>> {
  return apiJsonRequest<StudentMutationResponse<StudentSkill>>(`/student/profile/skills/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deleteSkill(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/skills/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

export function createProject(
  payload: StudentProjectInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentProject>> {
  return apiJsonRequest<StudentMutationResponse<StudentProject>>("/student/profile/projects", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updateProject(
  id: number,
  payload: StudentProjectInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentProject>> {
  return apiJsonRequest<StudentMutationResponse<StudentProject>>(`/student/profile/projects/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deleteProject(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/projects/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

export function createExperience(
  payload: StudentExperienceInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentExperience>> {
  return apiJsonRequest<StudentMutationResponse<StudentExperience>>("/student/profile/experiences", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updateExperience(
  id: number,
  payload: StudentExperienceInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentExperience>> {
  return apiJsonRequest<StudentMutationResponse<StudentExperience>>(`/student/profile/experiences/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deleteExperience(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/experiences/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

export function createAchievement(
  payload: StudentAchievementInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentAchievement>> {
  return apiJsonRequest<StudentMutationResponse<StudentAchievement>>("/student/profile/achievements", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updateAchievement(
  id: number,
  payload: StudentAchievementInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentAchievement>> {
  return apiJsonRequest<StudentMutationResponse<StudentAchievement>>(`/student/profile/achievements/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deleteAchievement(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/achievements/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

export function createPublication(
  payload: StudentPublicationInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentPublication>> {
  return apiJsonRequest<StudentMutationResponse<StudentPublication>>("/student/profile/publications", {
    method: "POST",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function updatePublication(
  id: number,
  payload: StudentPublicationInput,
  opts?: RequestOptions,
): Promise<StudentMutationResponse<StudentPublication>> {
  return apiJsonRequest<StudentMutationResponse<StudentPublication>>(`/student/profile/publications/${id}`, {
    method: "PUT",
    body: payload,
    requireAuth: true,
    opts,
  });
}

export function deletePublication(id: number, opts?: RequestOptions): Promise<StudentDeleteResponse> {
  return apiJsonRequest<StudentDeleteResponse>(`/student/profile/publications/${id}`, {
    method: "DELETE",
    requireAuth: true,
    opts,
  });
}

// --- Stage 6.2: Professor-Specific Resume Generation & Export ---

export function generateTailoredResume(
  professorId: number,
  payload: TailoredResumeGenerateRequest,
  opts?: RequestOptions,
): Promise<TailoredResumeGenerateResponse> {
  return apiJsonRequest<TailoredResumeGenerateResponse>(
    `/student/applications/${professorId}/resumes/generate`,
    {
      method: "POST",
      body: payload,
      requireAuth: true,
      opts: { timeoutMs: 60_000, ...opts },
    },
  );
}

export async function exportTailoredResume(
  professorId: number,
  payload: TailoredResumeExportRequest,
  opts: RequestOptions = {},
): Promise<{ blob: Blob; filename: string }> {
  const token = getStoredAuthToken();
  if (!token) {
    throw new ApiError("unauthorized", "Please sign in to export your resume.", 401);
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? PROFILE_TIMEOUT_MS);

  try {
    const res = await (opts.fetchImpl ?? fetch)(
      `${API_BASE_URL}/student/applications/${professorId}/resumes/export`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    );
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = (await res.json())?.detail;
      } catch {
        /* ignore */
      }
      throw describeHttpError(res.status, detail);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match?.[1] || `tailored_resume.${payload.format}`;
    return { blob, filename };
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error)?.name === "AbortError") {
      if (timedOut) throw new ApiError("timeout", "Export timed out. Please try again.");
      throw new ApiError("aborted", "Export cancelled.");
    }
    throw new ApiError("network", `Cannot reach the backend at ${API_BASE_URL}. Is the FastAPI server running?`);
  } finally {
    clearTimeout(timer);
  }
}
