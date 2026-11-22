import type { ResumeSectionKey, TailoredResumeContent } from "../../types/api";

const SECTION_TITLES: Record<ResumeSectionKey, string> = {
  summary: "Professional Summary",
  education: "Education",
  research_interests: "Research Interests",
  skills: "Skills",
  projects: "Selected Projects",
  research_experience: "Research Experience",
  experience: "Internships & Work Experience",
  publications: "Publications",
  achievements: "Achievements & Certifications",
};

function safeHref(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim()) return null;
  const trimmed = raw.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("10.")) return `https://doi.org/${trimmed}`;
  return null;
}

export default function ResumePreview({ content }: { content: TailoredResumeContent }) {
  const isAcademic = content.template === "academic_research";
  const isTech = content.template === "technical_ai_ml";

  const containerFont = isAcademic ? "font-serif" : "font-sans";
  const headingAccent = isTech
    ? "border-slate-900 text-slate-900"
    : "border-navy-800 text-navy-900";

  const enabled = new Set(content.enabled_sections);
  const orderedSections = content.section_order.filter((s) => enabled.has(s));

  const subtitle = [
    content.header.degree_program,
    content.header.department,
    content.header.institution,
  ]
    .filter((v) => v && v.trim())
    .join(" · ");

  const contactBits = [
    content.header.phone,
    content.header.current_year_or_semester,
    content.header.graduation_year ? `Class of ${content.header.graduation_year}` : null,
  ].filter((v) => v && v.trim());

  const headerLinks = [
    content.header.email ? { label: content.header.email, href: `mailto:${content.header.email}` } : null,
    safeHref(content.header.linkedin_url) ? { label: "LinkedIn", href: safeHref(content.header.linkedin_url)! } : null,
    safeHref(content.header.github_url) ? { label: "GitHub", href: safeHref(content.header.github_url)! } : null,
    safeHref(content.header.portfolio_url)
      ? { label: "Portfolio", href: safeHref(content.header.portfolio_url)! }
      : null,
  ].filter((x): x is { label: string; href: string } => x !== null);

  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8 ${containerFont}`}
      data-template={content.template}
    >
      {/* Document Header */}
      <header className="border-b border-slate-200 pb-4">
        <h2 className={`text-2xl font-bold tracking-tight ${isTech ? "text-slate-900" : "text-navy-900"}`}>
          {content.header.full_name}
        </h2>
        {subtitle && <p className="mt-1 text-sm text-slate-700">{subtitle}</p>}
        {contactBits.length > 0 && <p className="mt-0.5 text-xs text-slate-500">{contactBits.join(" · ")}</p>}
        {headerLinks.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {headerLinks.map((lnk) => (
              <a
                key={lnk.href}
                href={lnk.href}
                target={lnk.href.startsWith("mailto:") ? undefined : "_blank"}
                rel={lnk.href.startsWith("mailto:") ? undefined : "noreferrer"}
                className="font-medium text-navy-700 hover:underline"
              >
                {lnk.label}
              </a>
            ))}
          </div>
        )}
      </header>

      {/* Ordered Enabled Sections */}
      <div className="mt-5 space-y-5 text-sm text-slate-800">
        {orderedSections.map((sec) => {
          if (sec === "summary") {
            if (!content.summary.trim()) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <p className="mt-2 leading-relaxed text-slate-700">{content.summary}</p>
              </section>
            );
          }

          if (sec === "research_interests") {
            if (!content.research_interests?.trim()) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <p className="mt-2 leading-relaxed text-slate-700">{content.research_interests}</p>
              </section>
            );
          }

          if (sec === "education") {
            if (content.education.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2 space-y-2.5">
                  {content.education.map((edu, idx) => (
                    <div key={edu.source_id ?? idx}>
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="font-semibold text-slate-900">
                          {edu.degree}
                          {edu.department_major ? `, ${edu.department_major}` : ""} — {edu.institution}
                        </p>
                        {edu.duration && <span className="text-xs text-slate-500">{edu.duration}</span>}
                      </div>
                      {(edu.cgpa_or_percentage || edu.relevant_coursework) && (
                        <p className="mt-0.5 text-xs text-slate-600">
                          {[
                            edu.cgpa_or_percentage ? `Grade / CGPA: ${edu.cgpa_or_percentage}` : null,
                            edu.relevant_coursework ? `Coursework: ${edu.relevant_coursework}` : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            );
          }

          if (sec === "skills") {
            const nonEmpty = content.skills.filter((g) => g.items.length > 0);
            if (nonEmpty.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2 space-y-1">
                  {nonEmpty.map((grp, idx) => (
                    <p key={idx} className="text-xs leading-relaxed text-slate-700">
                      <span className="font-semibold text-slate-900">{grp.category}:</span> {grp.items.join(", ")}
                    </p>
                  ))}
                </div>
              </section>
            );
          }

          if (sec === "projects" || sec === "research_experience") {
            const items = sec === "projects" ? content.projects : content.research_experience;
            if (items.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2.5 space-y-3">
                  {items.map((proj, idx) => {
                    const link = safeHref(proj.url);
                    return (
                      <div key={proj.source_id ?? idx}>
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="font-semibold text-slate-900">
                            {link ? (
                              <a href={link} target="_blank" rel="noreferrer" className="hover:text-navy-700 hover:underline">
                                {proj.title} ↗
                              </a>
                            ) : (
                              proj.title
                            )}
                            {(proj.role || proj.organization) && (
                              <span className="font-normal text-slate-600">
                                {" "}
                                — {[proj.role, proj.organization].filter(Boolean).join(", ")}
                              </span>
                            )}
                          </p>
                          {proj.duration && <span className="text-xs text-slate-500">{proj.duration}</span>}
                        </div>
                        {proj.technologies && (
                          <p className="mt-0.5 text-xs text-slate-500">
                            <span className="font-medium text-slate-700">Technologies:</span> {proj.technologies}
                          </p>
                        )}
                        {proj.bullets.length > 0 && (
                          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs leading-relaxed text-slate-700">
                            {proj.bullets.map((b, bIdx) => (
                              <li key={bIdx}>{b}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          }

          if (sec === "experience") {
            if (content.experience.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2.5 space-y-3">
                  {content.experience.map((exp, idx) => (
                    <div key={exp.source_id ?? idx}>
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="font-semibold text-slate-900">
                          {exp.role} — {exp.organization}
                          {exp.location ? <span className="font-normal text-slate-600"> ({exp.location})</span> : null}
                        </p>
                        {exp.duration && <span className="text-xs text-slate-500">{exp.duration}</span>}
                      </div>
                      {exp.technologies && (
                        <p className="mt-0.5 text-xs text-slate-500">
                          <span className="font-medium text-slate-700">Technologies:</span> {exp.technologies}
                        </p>
                      )}
                      {exp.bullets.length > 0 && (
                        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs leading-relaxed text-slate-700">
                          {exp.bullets.map((b, bIdx) => (
                            <li key={bIdx}>{b}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            );
          }

          if (sec === "publications") {
            if (content.publications.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2 space-y-2">
                  {content.publications.map((pub, idx) => {
                    const link = safeHref(pub.doi_or_url);
                    return (
                      <div key={pub.source_id ?? idx}>
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="font-semibold text-slate-900">
                            {link ? (
                              <a href={link} target="_blank" rel="noreferrer" className="hover:text-navy-700 hover:underline">
                                {pub.title} ↗
                              </a>
                            ) : (
                              pub.title
                            )}
                          </p>
                          {pub.date && <span className="text-xs text-slate-500">{pub.date}</span>}
                        </div>
                        {(pub.authors || pub.venue) && (
                          <p className="text-xs text-slate-600">
                            {[pub.authors, pub.venue].filter(Boolean).join(" · ")}
                          </p>
                        )}
                        {pub.summary && <p className="mt-0.5 text-xs text-slate-700">{pub.summary}</p>}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          }

          if (sec === "achievements") {
            if (content.achievements.length === 0) return null;
            return (
              <section key={sec}>
                <h3 className={`border-b pb-1 text-xs font-bold uppercase tracking-wider ${headingAccent}`}>
                  {SECTION_TITLES[sec]}
                </h3>
                <div className="mt-2 space-y-2">
                  {content.achievements.map((ach, idx) => {
                    const link = safeHref(ach.credential_url);
                    return (
                      <div key={ach.source_id ?? idx}>
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="font-semibold text-slate-900">
                            {link ? (
                              <a href={link} target="_blank" rel="noreferrer" className="hover:text-navy-700 hover:underline">
                                {ach.title} ↗
                              </a>
                            ) : (
                              ach.title
                            )}
                            {ach.issuer && <span className="font-normal text-slate-600"> — {ach.issuer}</span>}
                          </p>
                          {ach.date && <span className="text-xs text-slate-500">{ach.date}</span>}
                        </div>
                        {ach.description && <p className="text-xs text-slate-700">{ach.description}</p>}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          }

          return null;
        })}
      </div>
    </div>
  );
}
