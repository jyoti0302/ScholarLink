import { Link } from "react-router-dom";
import {
  APPLICATION_STATUS_MAP,
  countSelectedItems,
  useApplications,
  type ApplicationDocumentVersion,
} from "../context/ApplicationsContext";

function formatDate(iso: string | undefined): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function summarizeDocStatus(versions: ApplicationDocumentVersion[]): { label: string; ready: boolean } {
  if (versions.length === 0) return { label: "Not created", ready: false };
  const hasReady = versions.some((v) => v.status === "ready");
  const plural = versions.length === 1 ? "version" : "versions";
  return {
    label: hasReady ? `Ready (${versions.length} ${plural})` : `Draft (${versions.length} ${plural})`,
    ready: hasReady,
  };
}

export default function MyApplicationsPage() {
  const { applications } = useApplications();

  const sortedApplications = [...applications].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="font-serif text-3xl text-navy-900">My Applications</h1>
          <p className="mt-1 text-sm text-slate-600">
            Organize professor-specific tailored resumes, cover letters, outreach email drafts, and selected profile
            items in dedicated workspaces.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/profile"
            className="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            My Academic Profile
          </Link>
          <Link
            to="/"
            className="rounded-md bg-navy-800 px-3.5 py-2 text-sm font-medium text-white hover:bg-navy-900"
          >
            Discover Professors
          </Link>
        </div>
      </div>

      {/* Master Profile & Storage Transparency Notice */}
      <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs text-slate-600">
        Each professor has an isolated application workspace. Selections reference items from{" "}
        <Link to="/profile" className="font-medium text-navy-800 hover:underline">
          My Academic Profile
        </Link>{" "}
        and never overwrite your master profile or mix across professors. Workspace selections and status are currently
        saved in this browser&apos;s local storage per signed-in student account.
      </div>

      {sortedApplications.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
          <h2 className="font-serif text-xl text-navy-900">No professor applications yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-slate-600">
            Start by discovering a professor whose research matches your interests. From any professor&apos;s profile page,
            choose <span className="font-medium text-slate-800">Create Tailored Resume</span>,{" "}
            <span className="font-medium text-slate-800">Create Cover Letter</span>, or{" "}
            <span className="font-medium text-slate-800">Generate Outreach Email</span> to open their dedicated
            application workspace here.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link
              to="/"
              className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
            >
              Discover Professors
            </Link>
            <Link
              to="/profile"
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Update Academic Profile
            </Link>
          </div>
        </div>
      ) : (
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          {sortedApplications.map((app) => {
            const statusMeta = APPLICATION_STATUS_MAP[app.status];
            const resumeStatus = summarizeDocStatus(app.resumeVersions);
            const coverStatus = summarizeDocStatus(app.coverLetterVersions);
            const emailStatus = summarizeDocStatus(app.outreachEmailDrafts);
            const selectedCount = countSelectedItems(app.selections);
            const lastUpdated = formatDate(app.updatedAt);

            return (
              <article
                key={app.professorId}
                className="flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:border-navy-300"
              >
                <div>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h2 className="font-serif text-xl text-navy-900">{app.professorName}</h2>
                      <p className="mt-0.5 text-sm text-slate-600">
                        {[app.department, app.university].filter(Boolean).join(" · ") || "Faculty Profile"}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${statusMeta.badgeClassName}`}
                    >
                      {statusMeta.label}
                    </span>
                  </div>

                  {/* Document & Selection Status Grid */}
                  <dl className="mt-4 grid grid-cols-3 gap-2 rounded-md border border-slate-100 bg-slate-50/70 p-3 text-xs">
                    <div>
                      <dt className="text-slate-500">Tailored Resume</dt>
                      <dd className={`mt-1 font-medium ${resumeStatus.ready ? "text-emerald-700" : "text-slate-700"}`}>
                        {resumeStatus.label}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Cover Letter</dt>
                      <dd className={`mt-1 font-medium ${coverStatus.ready ? "text-emerald-700" : "text-slate-700"}`}>
                        {coverStatus.label}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Outreach Email</dt>
                      <dd className={`mt-1 font-medium ${emailStatus.ready ? "text-emerald-700" : "text-slate-700"}`}>
                        {emailStatus.label}
                      </dd>
                    </div>
                  </dl>

                  <p className="mt-2.5 text-xs text-slate-500">
                    Selected profile items: <span className="font-medium text-slate-700">{selectedCount}</span>
                  </p>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3.5 text-xs">
                  <div className="flex flex-wrap items-center gap-3 text-slate-500">
                    <Link
                      to={`/professors/${app.professorId}`}
                      className="font-medium text-navy-700 hover:underline"
                    >
                      View Professor Profile
                    </Link>
                    {lastUpdated && <span>Updated {lastUpdated}</span>}
                  </div>
                  <Link
                    to={`/applications/${app.professorId}`}
                    className="rounded-md bg-navy-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
                  >
                    Open Workspace →
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
