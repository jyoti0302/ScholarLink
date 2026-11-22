import { Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import ProtectedRoute from "./components/ProtectedRoute";
import ApplicationWorkspacePage from "./pages/ApplicationWorkspacePage";
import LandingSearchPage from "./pages/LandingSearchPage";
import LoginPage from "./pages/LoginPage";
import MyApplicationsPage from "./pages/MyApplicationsPage";
import ProfessorProfilePage from "./pages/ProfessorProfilePage";
import RegisterPage from "./pages/RegisterPage";
import SearchResultsPage from "./pages/SearchResultsPage";
import StudentProfilePage from "./pages/StudentProfilePage";
import { AboutPage, NotFoundPage } from "./pages/StaticPages";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingSearchPage />} />
      <Route path="/results" element={<SearchResultsPage />} />
      <Route path="/professors/:id" element={<ProfessorProfilePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <StudentProfilePage />
          </ProtectedRoute>
        }
      />
      <Route path="/applications" element={<MyApplicationsPage />} />
      <Route path="/applications/:professorId" element={<ApplicationWorkspacePage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        <AppRoutes />
      </main>
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        ScholarLink · Prototype for IIT Kharagpur · Data sourced from official faculty profiles and publication records
      </footer>
    </div>
  );
}
