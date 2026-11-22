import { NavLink, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const links = [
  { to: "/", label: "Discover Professors", end: true },
  { to: "/profile", label: "My Academic Profile" },
  { to: "/applications", label: "My Applications" },
  { to: "/about", label: "About" },
];

export default function Navbar() {
  const { isAuthenticated, student, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded bg-navy-800 font-serif text-lg text-white">S</span>
          <span className="font-serif text-xl text-navy-900">ScholarLink</span>
          <span className="hidden text-xs uppercase tracking-wider text-slate-500 sm:inline">IIT Kharagpur</span>
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <ul className="flex flex-wrap gap-1 text-sm">
            {links.map((l) => (
              <li key={l.to}>
                <NavLink
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    `rounded px-3 py-2 ${isActive ? "bg-navy-50 font-medium text-navy-800" : "text-slate-600 hover:text-navy-800"}`
                  }
                >
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-2 border-l border-slate-200 pl-3 text-sm">
            {isAuthenticated && student ? (
              <>
                <span className="hidden max-w-[160px] truncate text-xs text-slate-600 md:inline" title={student.email}>
                  {student.full_name || student.email}
                </span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="rounded border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  className="rounded px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:text-navy-900"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="rounded bg-navy-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
                >
                  Register
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}
