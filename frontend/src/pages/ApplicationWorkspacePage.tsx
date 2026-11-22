import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, getStudentProfile } from "../api/client";
import SelectedProfileItemsPanel from "../components/applications/SelectedProfileItemsPanel";
import TailoredResumesTab from "../components/applications/TailoredResumesTab";
import {
  APPLICATION_STATUSES,
  APPLICATION_STATUS_MAP,
  countSelectedItems,
  useApplications,
  validateStatusTransition,
  type ApplicationStatus,
  type ProfessorApplicationSeed,
} from "../context/ApplicationsContext";
import { useAuth } from "../context/AuthContext";
import type { StudentCompleteProfile } from "../types/api";

type WorkspaceTab = "resume" | "cover-letter" | "outreach" | "profile-selection";

interface WorkspaceLocationState {
  professorId?: number;
  professorName?: string;
  department?: string;
  university?: string;
}

const TAB_LABELS: { id: WorkspaceTab; label: string }[] = [
  { id: "resume", label: "Tailored Resumes" },
  { id: "cover-letter", label: "Cover Letters" },
  { id: "outreach", label: "Outreach Emails" },
  { id: "profile-selection", label: "Selected Profile Items" },
];

export default function ApplicationWorkspacePage() {
  const { professorId: rawId } = useParams();
  const professorId = Number(rawId);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const state = (location.state as WorkspaceLocationState | null) ?? null;

  const { isAuthenticated, loading: authLoading, logout } = useAuth();
  const {
    getApplication,
    ensureApplication,
    updateApplicationNotes,
    updateApplicationSelections,
    updateApplicationStatus,
    addResumeVersion,
    updateResumeVersion,
    duplicateResumeVersion,
    deleteResumeVersion,
    removeApplication,
  } = useApplications();

  const existing = Number.isInteger(professorId) && professorId > 0 ? getApplication(professorId) : undefined;

  useEffect(() => {
    if (!Number.isInteger(professorId) || professorId <= 0) return;
    if (!existing && state?.professorName) {
      const seed: ProfessorApplicationSeed = {
        professorId,
        professorName: state.professorName,
        department: state.department,
        university: state.university,
      };
      ensureApplication(seed);
    }
  }, [professorId, existing, state, ensureApplication]);

  const application = Number.isInteger(professorId) && professorId > 0 ? getApplication(professorId) : undefined;

  const rawTab = searchParams.get("tab") as WorkspaceTab | null;
  const activeTab: WorkspaceTab =
    rawTab && TAB_LABELS.some((t) => t.id === rawTab) ? rawTab : "resume";

  // Notes state
  const [notesDraft, setNotesDraft] = useState(application?.notes ?? "");
  const [notesSaved, setNotesSaved] = useState(false);

  // Status workflow confirmation & validation feedback
  const [statusFeedback, setStatusFeedback] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [pendingStatusConfirmation, setPendingStatusConfirmation] = useState<"ready_to_send" | "sent" | null>(null);

  // Student master profile state (read-only source for Selected Profile Items)
  const [studentProfile, setStudentProfile] = useState<StudentCompleteProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    setNotesDraft(application?.notes ?? "");
    setStatusFeedback(null);
    setPendingStatusConfirmation(null);
  }, [application?.professorId, application?.notes]);

  const loadStudentMasterProfile = useCallback(async () => {
    if (!isAuthenticated) {
      setStudentProfile(null);
      setProfileError(null);
      return;
    }
    setProfileLoading(true);
    setProfileError(null);
    try {
      const data = await getStudentProfile();
      setStudentProfile(data);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "unauthorized") {
        logout();
        setStudentProfile(null);
        return;
      }
      setProfileError(err instanceof Error ? err.message : "Unable to load your Academic Profile.");
    } finally {
      setProfileLoading(false);
    }
  }, [isAuthenticated, logout]);

  useEffect(() => {
    if (
      (activeTab === "profile-selection" || activeTab === "resume") &&
      isAuthenticated &&
      !studentProfile &&
      !profileLoading
    ) {
      void loadStudentMasterProfile();
    }
  }, [activeTab, isAuthenticated, studentProfile, profileLoading, loadStudentMasterProfile]);

  if (!Number.isInteger(professorId) || professorId <= 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center">
        <h1 className="font-serif text-2xl text-navy-900">Invalid application workspace</h1>
        <p className="mt-2 text-sm text-slate-600">The requested professor application ID is invalid.</p>
        <Link
          to="/applications"
          className="mt-5 inline-block rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
        >
          Back to My Applications
        </Link>
      </div>
    );
  }

  if (!application) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center">
        <h1 className="font-serif text-2xl text-navy-900">Application workspace not found</h1>
        <p className="mt-2 text-sm text-slate-600">
          Open a professor&apos;s profile page to initiate a tailored resume, cover letter, or outreach email for them.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            to={`/professors/${professorId}`}
            className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
          >
            View Professor Profile
          </Link>
          <Link
            to="/applications"
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Back to My Applications
          </Link>
        </div>
      </div>
    );
  }

  const currentStatusMeta = APPLICATION_STATUS_MAP[application.status];
  const selectedTotal = countSelectedItems(application.selections);

  function handleStatusSelect(nextStatus: ApplicationStatus) {
    if (!application || nextStatus === application.status) return;
    setStatusFeedback(null);
    setPendingStatusConfirmation(null);

    if (nextStatus === "ready_to_send") {
      const check = validateStatusTransition(application, "ready_to_send", { explicitApproval: true });
      if (!check.allowed) {
        setStatusFeedback({ kind: "error", text: check.reason || "Cannot change status." });
        return;
      }
      setPendingStatusConfirmation("ready_to_send");
      return;
    }

    if (nextStatus === "sent") {
      const check = validateStatusTransition(application, "sent", { confirmSubmission: true });
      if (!check.allowed) {
        setStatusFeedback({ kind: "error", text: check.reason || "Cannot change status." });
        return;
      }
      setPendingStatusConfirmation("sent");
      return;
    }

    const res = updateApplicationStatus(professorId, nextStatus);
    if (!res.allowed) {
      setStatusFeedback({ kind: "error", text: res.reason || "Status transition not allowed." });
    } else {
      setStatusFeedback({
        kind: "success",
        text: `Status updated to ${APPLICATION_STATUS_MAP[nextStatus].label}.`,
      });
    }
  }

  function handleConfirmPendingStatus() {
    if (!pendingStatusConfirmation) return;
    const opts =
      pendingStatusConfirmation === "ready_to_send"
        ? { explicitApproval: true }
        : { confirmSubmission: true };
    const res = updateApplicationStatus(professorId, pendingStatusConfirmation, opts);
    if (!res.allowed) {
      setStatusFeedback({ kind: "error", text: res.reason || "Status transition not allowed." });
    } else {
      setStatusFeedback({
        kind: "success",
        text: `Status updated to ${APPLICATION_STATUS_MAP[pendingStatusConfirmation].label}.`,
      });
    }
    setPendingStatusConfirmation(null);
  }

  function handleSaveNotes() {
    updateApplicationNotes(professorId, notesDraft);
    setNotesSaved(true);
    setTimeout(() => setNotesSaved(false), 2500);
  }

  function handleRemoveWorkspace() {
    removeApplication(professorId);
    navigate("/applications");
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-4">
        <Link to="/applications" className="text-sm font-medium text-navy-700 hover:underline">
          ← Back to My Applications
        </Link>
      </div>

      {/* Workspace Header */}
      <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
              Professor Application Workspace
            </p>
            <h1 className="mt-1 font-serif text-3xl text-navy-900">{application.professorName}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {[application.department, application.university].filter(Boolean).join(" · ") || "Faculty Profile"}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
              <Link to={`/professors/${application.professorId}`} className="font-medium text-navy-700 hover:underline">
                View Professor Profile →
              </Link>
              <Link to="/profile" className="font-medium text-slate-600 hover:text-navy-800 hover:underline">
                Open Master Academic Profile
              </Link>
            </div>
          </div>

          <div className="min-w-[220px]">
            <label htmlFor="application-status" className="block text-[11px] font-medium uppercase text-slate-500">
              Application Status
            </label>
            <div className="mt-1 flex items-center gap-2">
              <select
                id="application-status"
                value={application.status}
                onChange={(e) => handleStatusSelect(e.target.value as ApplicationStatus)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 focus:border-navy-700 focus:outline-none"
              >
                {APPLICATION_STATUSES.map((st) => (
                  <option key={st.value} value={st.value}>
                    {st.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">{currentStatusMeta.description}</p>
          </div>
        </div>

        {/* Explicit Approval / Submission Confirmation */}
        {pendingStatusConfirmation && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-950">
            <p className="font-medium">
              {pendingStatusConfirmation === "ready_to_send"
                ? "Confirm Ready to Send Approval"
                : "Confirm Application Submission"}
            </p>
            <p className="mt-1 text-xs text-amber-900">
              {pendingStatusConfirmation === "ready_to_send"
                ? `Have you reviewed all generated application materials for ${application.professorName} and approved them as Ready to Send?`
                : `Confirm that you have actually sent your application to ${application.professorName}.`}
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleConfirmPendingStatus}
                className="rounded-md bg-navy-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
              >
                {pendingStatusConfirmation === "ready_to_send" ? "Approve as Ready to Send" : "Confirm Sent"}
              </button>
              <button
                type="button"
                onClick={() => setPendingStatusConfirmation(null)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {statusFeedback && (
          <div
            role={statusFeedback.kind === "error" ? "alert" : "status"}
            className={`mt-4 flex items-center justify-between rounded-md border px-3.5 py-2 text-xs ${
              statusFeedback.kind === "error"
                ? "border-red-200 bg-red-50 text-red-800"
                : "border-emerald-200 bg-emerald-50 text-emerald-800"
            }`}
          >
            <span>{statusFeedback.text}</span>
            <button
              type="button"
              onClick={() => setStatusFeedback(null)}
              className="ml-3 font-medium opacity-70 hover:opacity-100"
            >
              Dismiss
            </button>
          </div>
        )}
      </header>

      {/* Workspace Tabs */}
      <div className="mt-6 flex flex-wrap gap-1 border-b border-slate-200">
        {TAB_LABELS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSearchParams({ tab: tab.id })}
              className={`border-b-2 px-4 py-2.5 text-sm font-medium transition ${
                isActive
                  ? "border-navy-800 text-navy-900"
                  : "border-transparent text-slate-600 hover:text-navy-800"
              }`}
            >
              {tab.label}
              {tab.id === "profile-selection" && selectedTotal > 0 ? ` (${selectedTotal})` : ""}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="rounded-lg border border-slate-200 bg-white p-6 lg:col-span-2">
          {activeTab === "resume" && (
            <TailoredResumesTab
              application={application}
              isAuthenticated={isAuthenticated}
              studentProfile={studentProfile}
              studentProfileLoading={profileLoading}
              onJumpToSelections={() => setSearchParams({ tab: "profile-selection" })}
              onAddResumeVersion={(input) => addResumeVersion(professorId, input)}
              onUpdateResumeVersion={(versionId, updates) => updateResumeVersion(professorId, versionId, updates)}
              onDuplicateResumeVersion={(versionId) => duplicateResumeVersion(professorId, versionId)}
              onDeleteResumeVersion={(versionId) => deleteResumeVersion(professorId, versionId)}
              onAuthExpired={() => {
                logout();
                navigate("/login", {
                  replace: true,
                  state: { from: { pathname: `/applications/${professorId}`, search: "?tab=resume" } },
                });
              }}
            />
          )}

          {activeTab === "cover-letter" && (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-serif text-xl text-navy-900">Cover Letters</h2>
                <span className="rounded bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                  {application.coverLetterVersions.length} version(s)
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                Professor-specific cover letter drafts grounded in {application.professorName}&apos;s research and your
                selected profile items.
              </p>
              <div className="mt-6 rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-6 text-center">
                <p className="font-medium text-slate-800">No cover letter drafts yet</p>
                <p className="mx-auto mt-1 max-w-md text-xs text-slate-600">
                  {selectedTotal > 0
                    ? `${selectedTotal} profile item(s) are selected for this application. Cover letter drafting will use these selections in the next stage.`
                    : "Cover letter drafting and version management for this professor will be enabled in the next stage."}
                </p>
              </div>
            </div>
          )}

          {activeTab === "outreach" && (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-serif text-xl text-navy-900">Outreach Emails</h2>
                <span className="rounded bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                  {application.outreachEmailDrafts.length} draft(s)
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                Concise cold-outreach email drafts referencing {application.professorName}&apos;s publications and your
                selected profile highlights.
              </p>
              <div className="mt-6 rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-6 text-center">
                <p className="font-medium text-slate-800">No outreach email drafts yet</p>
                <p className="mx-auto mt-1 max-w-md text-xs text-slate-600">
                  {selectedTotal > 0
                    ? `${selectedTotal} profile item(s) are selected for this application. Outreach email generation will use these selections in the next stage.`
                    : "Outreach email drafting for this professor will be enabled in the next stage."}
                </p>
              </div>
            </div>
          )}

          {activeTab === "profile-selection" && (
            <div>
              {authLoading ? (
                <div className="animate-pulse space-y-4 py-4">
                  <div className="h-5 w-48 rounded bg-slate-200" />
                  <div className="h-24 rounded bg-slate-100" />
                  <div className="h-24 rounded bg-slate-100" />
                </div>
              ) : !isAuthenticated ? (
                <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-8 text-center">
                  <h2 className="font-serif text-xl text-navy-900">Sign in to select profile items</h2>
                  <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">
                    Sign in to load your real projects, skills, research experience, internships, achievements, and
                    publications from My Academic Profile.
                  </p>
                  <div className="mt-5 flex justify-center gap-3">
                    <Link
                      to="/login"
                      state={{ from: { pathname: `/applications/${professorId}`, search: "?tab=profile-selection" } }}
                      className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
                    >
                      Sign in
                    </Link>
                    <Link
                      to="/register"
                      state={{ from: { pathname: `/applications/${professorId}`, search: "?tab=profile-selection" } }}
                      className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Create account
                    </Link>
                  </div>
                </div>
              ) : profileLoading ? (
                <div className="animate-pulse space-y-4 py-4">
                  <div className="h-6 w-56 rounded bg-slate-200" />
                  <div className="grid grid-cols-4 gap-2">
                    {[0, 1, 2, 3].map((i) => (
                      <div key={i} className="h-14 rounded bg-slate-100" />
                    ))}
                  </div>
                  <div className="h-28 rounded bg-slate-100" />
                  <div className="h-28 rounded bg-slate-100" />
                </div>
              ) : profileError ? (
                <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-5 text-center text-red-900">
                  <p className="text-sm font-medium">Could not load your Academic Profile</p>
                  <p className="mt-1 text-xs">{profileError}</p>
                  <button
                    type="button"
                    onClick={() => void loadStudentMasterProfile()}
                    className="mt-4 rounded-md bg-navy-800 px-4 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
                  >
                    Retry
                  </button>
                </div>
              ) : studentProfile ? (
                <SelectedProfileItemsPanel
                  professorName={application.professorName}
                  profile={studentProfile}
                  savedSelections={application.selections}
                  onSaveSelections={(nextSelections) => updateApplicationSelections(professorId, nextSelections)}
                />
              ) : null}
            </div>
          )}
        </section>

        {/* Application Notes Sidebar */}
        <aside className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <h3 className="font-serif text-lg text-navy-900">Application Notes</h3>
            <p className="mt-1 text-xs text-slate-500">
              Private notes specific to {application.professorName} (papers to cite, lab deadlines, follow-ups).
            </p>
            <textarea
              rows={5}
              value={notesDraft}
              onChange={(e) => setNotesDraft(e.target.value)}
              placeholder="e.g. Mention their recent ACL paper and ask about summer research openings..."
              className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-navy-700 focus:outline-none focus:ring-1 focus:ring-navy-700"
            />
            <div className="mt-3 flex items-center justify-between">
              <span className="text-xs text-emerald-700">{notesSaved ? "Notes saved" : ""}</span>
              <button
                type="button"
                onClick={handleSaveNotes}
                className="rounded-md bg-navy-800 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
              >
                Save Notes
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <button
              type="button"
              onClick={handleRemoveWorkspace}
              className="w-full rounded-md border border-red-200 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
            >
              Remove Application Workspace
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
