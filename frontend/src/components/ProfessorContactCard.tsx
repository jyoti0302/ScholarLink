import type { ProfessorContactLink, ProfessorProfile } from "../types/api";

function validHttpUrl(raw: string | null | undefined): string | null {
  if (!raw || typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!/^https?:\/\/[^\s]+$/i.test(trimmed)) return null;
  return trimmed;
}

function formatTelHref(phone: string): string {
  return `tel:${phone.replace(/[^+\d]/g, "")}`;
}

function MailIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 shrink-0 text-navy-700" aria-hidden="true">
      <rect x="2.5" y="4.5" width="15" height="11" rx="1.8" />
      <path d="M3.5 5.5 10 10.5l6.5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 shrink-0 text-navy-700" aria-hidden="true">
      <path
        d="M4.5 3.5h3l1.3 3.4-1.8 1.2a9.8 9.8 0 0 0 4.9 4.9l1.2-1.8 3.4 1.3v3a1.5 1.5 0 0 1-1.6 1.5A12.5 12.5 0 0 1 3 5.1 1.5 1.5 0 0 1 4.5 3.5Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LocationIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 shrink-0 text-navy-700" aria-hidden="true">
      <path d="M10 17.5s5.5-4.7 5.5-9a5.5 5.5 0 1 0-11 0c0 4.3 5.5 9 5.5 9Z" strokeLinejoin="round" />
      <circle cx="10" cy="8.5" r="2" />
    </svg>
  );
}

function BuildingIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 shrink-0 text-navy-700" aria-hidden="true">
      <path d="M3.5 17h13M5 17V4.5A1 1 0 0 1 6 3.5h8a1 1 0 0 1 1 1V17" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 7h1.5M10.5 7H12M8 10h1.5M10.5 10H12M9 17v-3.5h2V17" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 shrink-0 text-navy-700" aria-hidden="true">
      <circle cx="10" cy="10" r="7.2" />
      <path d="M2.8 10h14.4M10 2.8a11.2 11.2 0 0 1 0 14.4M10 2.8a11.2 11.2 0 0 0 0 14.4" strokeLinecap="round" />
    </svg>
  );
}

export default function ProfessorContactCard({ profile }: { profile: ProfessorProfile }) {
  const info = profile.contact_info;

  const email = (info?.email ?? profile.email ?? "").trim() || null;
  const officePhone = (info?.office_phone ?? "").trim() || null;
  const officeRoom = (info?.office_room ?? "").trim() || null;
  const departmentAddress = (info?.department_address ?? "").trim() || null;
  const departmentOfficeContact = (info?.department_office_contact ?? "").trim() || null;
  const departmentUrl = validHttpUrl(info?.department_url);
  const researchGroupWebsite =
    validHttpUrl(info?.research_group_website) || validHttpUrl(profile.research_group);
  const officialProfileUrl = validHttpUrl(info?.profile_url ?? profile.profile_url);
  const sourceUrl = validHttpUrl(info?.source_url ?? profile.source_url ?? profile.profile_url);

  // Deduplicated public academic links (Personal Webpage, Bio Sketch, ORCID, IRINS, OpenAlex)
  const academicLinks: ProfessorContactLink[] = [];
  const seen = new Set<string>();
  const addLink = (label: string, rawUrl: string | null | undefined, linkSource: string | null = null) => {
    const valid = validHttpUrl(rawUrl);
    if (!valid) return;
    const norm = valid.replace(/\/+$/, "").toLowerCase();
    if (seen.has(norm)) return;
    seen.add(norm);
    academicLinks.push({ label, url: valid, source_url: validHttpUrl(linkSource) });
  };

  if (info?.academic_links?.length) {
    for (const link of info.academic_links) {
      addLink(link.label, link.url, link.source_url);
    }
  } else {
    // Fallback if older response without contact_info is provided
    if (profile.orcid?.trim()) {
      const v = profile.orcid.trim();
      addLink("ORCID Profile", v.startsWith("http") ? v : `https://orcid.org/${v}`);
    }
    if (profile.irins_id?.trim()) {
      const v = profile.irins_id.trim();
      addLink("IRINS Profile", v.startsWith("http") ? v : `https://iitkgp.irins.org/profile/${v}`);
    }
    if (profile.openalex_author_id?.trim()) {
      const v = profile.openalex_author_id.trim();
      addLink("OpenAlex Author Profile", v.startsWith("http") ? v : `https://openalex.org/${v}`);
    }
  }

  const hasOfficeLocation = Boolean(officeRoom || departmentAddress);
  const hasDepartmentBlock = Boolean(departmentUrl || departmentOfficeContact);
  const hasWebsitesBlock = Boolean(researchGroupWebsite || officialProfileUrl || academicLinks.length > 0);
  const hasAnyContact = Boolean(email || officePhone || hasOfficeLocation || hasDepartmentBlock || hasWebsitesBlock);

  return (
    <section
      aria-labelledby="contact-information-heading"
      className="rounded-lg border border-slate-200 bg-white p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="contact-information-heading" className="font-serif text-xl text-navy-900">
          Contact Information
        </h2>
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-slate-500 hover:text-navy-700 hover:underline"
          >
            Source: Official Faculty Page ↗
          </a>
        )}
      </div>

      {!hasAnyContact ? (
        <p className="mt-3 text-sm italic text-slate-500">
          Contact information is not publicly available.
        </p>
      ) : (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {/* Official Institutional Email */}
          {email && (
            <div className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50/60 p-3.5">
              <div className="mt-0.5">
                <MailIcon />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Official Email</p>
                <a
                  href={`mailto:${email}`}
                  className="mt-0.5 block break-all text-sm font-medium text-navy-800 hover:underline"
                >
                  {email}
                </a>
              </div>
            </div>
          )}

          {/* Office Telephone / Extension */}
          {officePhone && (
            <div className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50/60 p-3.5">
              <div className="mt-0.5">
                <PhoneIcon />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Office Telephone</p>
                <a
                  href={formatTelHref(officePhone)}
                  className="mt-0.5 block text-sm font-medium text-navy-800 hover:underline"
                >
                  {officePhone}
                </a>
              </div>
            </div>
          )}

          {/* Office Room & Building / Department Address */}
          {hasOfficeLocation && (
            <div className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50/60 p-3.5">
              <div className="mt-0.5">
                <LocationIcon />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Office &amp; Address</p>
                {officeRoom && <p className="mt-0.5 text-sm font-medium text-slate-900">Room: {officeRoom}</p>}
                {departmentAddress && <p className="mt-0.5 text-sm text-slate-700">{departmentAddress}</p>}
              </div>
            </div>
          )}

          {/* Department Website / Office Contact */}
          {hasDepartmentBlock && (
            <div className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50/60 p-3.5">
              <div className="mt-0.5">
                <BuildingIcon />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Department</p>
                {profile.department_name && (
                  <p className="mt-0.5 text-sm font-medium text-slate-900">
                    {profile.department_name}
                    {profile.department_code ? ` (${profile.department_code})` : ""}
                  </p>
                )}
                {departmentOfficeContact && (
                  <p className="mt-0.5 text-xs text-slate-600">{departmentOfficeContact}</p>
                )}
                {departmentUrl && (
                  <a
                    href={departmentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-xs font-medium text-navy-700 hover:underline"
                  >
                    Official Department Page ↗
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Research Group Website, Official Profile URL & Public Academic Links */}
          {hasWebsitesBlock && (
            <div className="flex items-start gap-3 rounded-md border border-slate-100 bg-slate-50/60 p-3.5 sm:col-span-2">
              <div className="mt-0.5">
                <GlobeIcon />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Websites &amp; Public Academic Links
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {officialProfileUrl && (
                    <a
                      href={officialProfileUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded-md border border-navy-200 bg-white px-2.5 py-1 text-xs font-medium text-navy-800 hover:bg-navy-50"
                    >
                      Official Faculty Profile ↗
                    </a>
                  )}
                  {researchGroupWebsite && (
                    <a
                      href={researchGroupWebsite}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded-md border border-navy-200 bg-white px-2.5 py-1 text-xs font-medium text-navy-800 hover:bg-navy-50"
                    >
                      Research Group / Lab Website ↗
                    </a>
                  )}
                  {academicLinks.map((link) => (
                    <a
                      key={link.url}
                      href={link.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-navy-300 hover:text-navy-800"
                    >
                      {link.label} ↗
                    </a>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
