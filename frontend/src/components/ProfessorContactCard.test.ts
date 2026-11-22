import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ProfessorProfile } from "../types/api";
import ProfessorContactCard from "./ProfessorContactCard";

function makeBaseProfile(overrides: Partial<ProfessorProfile> = {}): ProfessorProfile {
  return {
    professor_id: 10,
    name: "Prof. Example Faculty",
    designation: "Professor",
    email: null,
    academic_unit: "Department",
    department_id: 1,
    department_name: "Computer Science and Engineering",
    department_code: "CS",
    university_id: 1,
    university_name: "Indian Institute of Technology Kharagpur",
    university_website: "https://www.iitkgp.ac.in",
    biography: null,
    educational_background: null,
    research_interests: null,
    research_group: null,
    profile_url: null,
    source_url: null,
    verification_status: "verified",
    orcid: null,
    irins_id: null,
    openalex_author_id: null,
    last_updated: null,
    contact_info: null,
    research_topics: [],
    research_projects: [],
    verified_publications: [],
    candidate_publications: [],
    ...overrides,
  };
}

describe("ProfessorContactCard", () => {
  it("renders cleanly for a professor with email only and omits unavailable fields", () => {
    const profile = makeBaseProfile({
      email: "faculty@cse.iitkgp.ac.in",
      contact_info: {
        email: "faculty@cse.iitkgp.ac.in",
        office_phone: null,
        office_room: null,
        department_address: null,
        department_office_contact: null,
        department_url: null,
        research_group_website: null,
        personal_webpage: null,
        bio_sketch_url: null,
        profile_url: null,
        academic_links: [],
        source_url: null,
      },
    });

    const html = renderToStaticMarkup(React.createElement(ProfessorContactCard, { profile }));
    expect(html).toContain("Contact Information");
    expect(html).toContain('href="mailto:faculty@cse.iitkgp.ac.in"');
    expect(html).toContain("sm:grid-cols-2");
    expect(html).not.toContain("Office Telephone");
    expect(html).not.toContain("Office &amp; Address");
    expect(html).not.toContain("Websites &amp; Public Academic Links");
    expect(html).not.toContain("Contact information is not publicly available.");
  });

  it("renders all multiple verified contact fields with clickable mailto, tel, and external links", () => {
    const profile = makeBaseProfile({
      email: "abhij@cse.iitkgp.ac.in",
      profile_url: "https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij",
      contact_info: {
        email: "abhij@cse.iitkgp.ac.in",
        office_phone: "+91-3222-282350",
        office_room: "CS-214",
        department_address: "Computer Science and Engineering, Indian Institute of Technology Kharagpur, India",
        department_office_contact: "Dept Office: +91-3222-282256",
        department_url: "https://www.iitkgp.ac.in/department/CS",
        research_group_website: "https://cnerg-iitkgp.github.io/",
        personal_webpage: "http://cse.iitkgp.ac.in/~abhij/",
        bio_sketch_url: "https://www.iitkgp.ac.in/assets/bio_sketch/MDIwMzk=.pdf",
        profile_url: "https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij",
        academic_links: [
          {
            label: "Personal Webpage",
            url: "http://cse.iitkgp.ac.in/~abhij/",
            source_url: "https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij",
          },
          {
            label: "ORCID Profile",
            url: "https://orcid.org/0000-0001-2345-6789",
            source_url: "https://orcid.org/0000-0001-2345-6789",
          },
        ],
        source_url: "https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij",
      },
    });

    const html = renderToStaticMarkup(React.createElement(ProfessorContactCard, { profile }));
    expect(html).toContain('href="mailto:abhij@cse.iitkgp.ac.in"');
    expect(html).toContain('href="tel:+913222282350"');
    expect(html).toContain("+91-3222-282350");
    expect(html).toContain("Room: CS-214");
    expect(html).toContain("Computer Science and Engineering, Indian Institute of Technology Kharagpur, India");
    expect(html).toContain("Dept Office: +91-3222-282256");
    expect(html).toContain('href="https://www.iitkgp.ac.in/department/CS"');
    expect(html).toContain('href="https://cnerg-iitkgp.github.io/"');
    expect(html).toContain('href="http://cse.iitkgp.ac.in/~abhij/"');
    expect(html).toContain('href="https://orcid.org/0000-0001-2345-6789"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
    expect(html).toContain("Source: Official Faculty Page");
  });

  it("clearly displays not publicly available when a professor has no public contact info", () => {
    const profile = makeBaseProfile({
      email: null,
      profile_url: null,
      source_url: null,
      research_group: null,
      contact_info: {
        email: null,
        office_phone: null,
        office_room: null,
        department_address: null,
        department_office_contact: null,
        department_url: null,
        research_group_website: null,
        personal_webpage: null,
        bio_sketch_url: null,
        profile_url: null,
        academic_links: [],
        source_url: null,
      },
    });

    const html = renderToStaticMarkup(React.createElement(ProfessorContactCard, { profile }));
    expect(html).toContain("Contact Information");
    expect(html).toContain("Contact information is not publicly available.");
  });

  it("rejects non-http external links so unsafe or malformed URLs are never rendered", () => {
    const profile = makeBaseProfile({
      email: "safe@iitkgp.ac.in",
      research_group: "javascript:alert(1)",
      contact_info: {
        email: "safe@iitkgp.ac.in",
        office_phone: null,
        office_room: null,
        department_address: null,
        department_office_contact: null,
        department_url: "not-a-valid-url",
        research_group_website: "javascript:alert(1)",
        personal_webpage: null,
        bio_sketch_url: null,
        profile_url: null,
        academic_links: [
          { label: "Bad Link", url: "javascript:void(0)", source_url: null },
          { label: "Valid Lab", url: "https://lab.iitkgp.ac.in", source_url: null },
        ],
        source_url: null,
      },
    });

    const html = renderToStaticMarkup(React.createElement(ProfessorContactCard, { profile }));
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("Bad Link");
    expect(html).toContain('href="https://lab.iitkgp.ac.in"');
  });
});
