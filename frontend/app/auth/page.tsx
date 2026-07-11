"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, setAuthToken, getAuthToken } from "@/lib/api";
import { KeyRound, Mail, User, ShieldAlert, ArrowRight, Layers } from "lucide-react";

export default function AuthPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("End User");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // If token exists, direct to chat
    if (getAuthToken()) {
      router.push("/chat");
    }
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isLogin) {
        // Build urlencoded body for OAuth2PasswordRequestForm
        const params = new URLSearchParams();
        params.append("username", email);
        params.append("password", password);
        
        const data = await api.login(params);
        setAuthToken(data.access_token, data.role, data.email);
        router.push("/chat");
      } else {
        await api.register({
          email,
          password,
          full_name: fullName || null,
          role,
        });
        // Success -> Switch to login and prefill
        setIsLogin(true);
        setError("Account created successfully! Please log in.");
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please check your details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-[#03050c] px-4 py-12 sm:px-6 lg:px-8">
      {/* Decorative background gradients */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[20%] left-[30%] h-[400px] w-[400px] rounded-full bg-purple-600/10 blur-[120px]" />
        <div className="absolute bottom-[20%] right-[30%] h-[500px] w-[500px] rounded-full bg-blue-600/10 blur-[130px]" />
      </div>

      <div className="z-10 w-full max-w-md space-y-8">
        <div className="flex flex-col items-center justify-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-purple-600 to-blue-500 shadow-lg shadow-purple-600/20">
            <Layers className="h-8 w-8 text-white animate-pulse" />
          </div>
          <h2 className="mt-6 text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
            SAP AI Knowledge Assistant
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            {isLogin ? "Sign in to access your SAP RAG Copilot" : "Create an account to begin"}
          </p>
        </div>

        <div className="glass-panel border-slate-800 bg-slate-900/60 p-8 rounded-3xl shadow-2xl backdrop-blur-xl">
          {error && (
            <div className={`mb-6 flex items-start gap-3 rounded-xl p-4 text-sm border ${
              error.includes("successfully") 
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" 
                : "bg-red-500/10 text-red-400 border-red-500/20"
            }`}>
              <ShieldAlert className="h-5 w-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-5" onSubmit={handleSubmit}>
            {!isLogin && (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-400">Full Name</label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                    <User className="h-4 w-4 text-slate-500" />
                  </div>
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Enter your name"
                    className="block w-full rounded-xl bg-slate-950/65 border border-slate-800/80 py-3 pl-10 pr-4 text-sm text-white placeholder-slate-500 transition-all focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-400">Email Address</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <Mail className="h-4 w-4 text-slate-500" />
                </div>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@sap.com"
                  className="block w-full rounded-xl bg-slate-950/65 border border-slate-800/80 py-3 pl-10 pr-4 text-sm text-white placeholder-slate-500 transition-all focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-400">Password</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <KeyRound className="h-4 w-4 text-slate-500" />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="block w-full rounded-xl bg-slate-950/65 border border-slate-800/80 py-3 pl-10 pr-4 text-sm text-white placeholder-slate-500 transition-all focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                />
              </div>
            </div>

            {!isLogin && (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-400">SAP User Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="block w-full rounded-xl bg-slate-950/65 border border-slate-800/80 py-3 px-4 text-sm text-white focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                >
                  <option value="End User">End User</option>
                  <option value="SAP Consultant">SAP Consultant</option>
                  <option value="SAP Knowledge Manager">SAP Knowledge Manager</option>
                  <option value="Super Admin">Super Admin</option>
                </select>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-500 py-3 text-sm font-semibold text-white shadow-lg shadow-purple-500/20 transition-all duration-200 hover:from-purple-500 hover:to-blue-400 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {loading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <>
                  <span>{isLogin ? "Sign In" : "Sign Up"}</span>
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-800/80 pt-6 text-center">
            <button
              onClick={() => {
                setIsLogin(!isLogin);
                setError("");
              }}
              className="text-sm font-medium text-purple-400 hover:text-purple-300"
            >
              {isLogin ? "New user? Create a consultant profile" : "Already have an account? Sign in"}
            </button>
          </div>
        </div>

        {/* Development Helper Quick login hints */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-center text-xs text-slate-500">
          <p className="font-semibold text-slate-400 mb-1">Development Quick Sign-in Credentials</p>
          <p>Admin Profile: <code className="text-purple-400">admin@sap.com</code> / <code className="text-purple-400">adminpassword</code></p>
          <p>Consultant Profile: <code className="text-blue-400">consultant@sap.com</code> / <code className="text-blue-400">consultantpassword</code></p>
        </div>
      </div>
    </div>
  );
}
