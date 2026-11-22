import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  clearStoredAuthToken,
  getCurrentStudent,
  getStoredAuthToken,
  loginStudent,
  registerStudent,
  setStoredAuthToken,
} from "../api/client";
import type { StudentAuthSummary, StudentCompleteProfile } from "../types/api";

interface AuthContextValue {
  student: StudentAuthSummary | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<StudentAuthSummary>;
  register: (email: string, password: string) => Promise<StudentAuthSummary>;
  logout: () => void;
  refreshStudent: () => Promise<void>;
  syncStudentFromProfile: (profile: StudentCompleteProfile) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredAuthToken());
  const [student, setStudent] = useState<StudentAuthSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(() => Boolean(getStoredAuthToken()));

  const logout = useCallback(() => {
    clearStoredAuthToken();
    setToken(null);
    setStudent(null);
    setLoading(false);
  }, []);

  const refreshStudent = useCallback(async () => {
    const activeToken = getStoredAuthToken();
    if (!activeToken) {
      setToken(null);
      setStudent(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const me = await getCurrentStudent();
      setToken(activeToken);
      setStudent(me);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "unauthorized") {
        clearStoredAuthToken();
        setToken(null);
        setStudent(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStudent();
  }, [refreshStudent]);

  const login = useCallback(async (email: string, password: string): Promise<StudentAuthSummary> => {
    const res = await loginStudent(email, password);
    setStoredAuthToken(res.access_token);
    setToken(res.access_token);
    setStudent(res.student);
    setLoading(false);
    return res.student;
  }, []);

  const register = useCallback(async (email: string, password: string): Promise<StudentAuthSummary> => {
    const res = await registerStudent(email, password);
    setStoredAuthToken(res.access_token);
    setToken(res.access_token);
    setStudent(res.student);
    setLoading(false);
    return res.student;
  }, []);

  const syncStudentFromProfile = useCallback((profile: StudentCompleteProfile) => {
    setStudent({
      id: profile.id,
      email: profile.email,
      full_name: profile.full_name,
      institution: profile.institution,
      department: profile.department,
      degree_program: profile.degree_program,
      graduation_year: profile.graduation_year,
      current_year_or_semester: profile.current_year_or_semester,
      created_at: profile.created_at,
      profile_completed: Boolean(profile.full_name && profile.full_name.trim()),
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      student,
      token,
      loading,
      isAuthenticated: Boolean(token && student),
      login,
      register,
      logout,
      refreshStudent,
      syncStudentFromProfile,
    }),
    [student, token, loading, login, register, logout, refreshStudent, syncStudentFromProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
