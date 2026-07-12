"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, setAuthToken, getAuthToken } from "@/lib/api";
import { KeyRound, Mail, User, ShieldAlert, ArrowRight, Layers, Eye, EyeOff, Info, HelpCircle } from "lucide-react";

export default function AuthPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("End User");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  
  // Premium States
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [showDevHints, setShowDevHints] = useState(false);

  useEffect(() => {
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
    <div className="relative flex min-h-screen items-center justify-center bg-background px-4 py-12 sm:px-6 lg:px-8 overflow-hidden">
      {/* Drifting gradient orbs in background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[10%] left-[20%] h-[450px] w-[450px] rounded-full bg-purple-600/10 blur-[130px] animate-drift-one" />
        <div className="absolute bottom-[10%] right-[20%] h-[550px] w-[550px] rounded-full bg-blue-600/10 blur-[140px] animate-drift-two" />
      </div>

      <div className="z-10 w-full max-w-md space-y-7">
        <div className="flex flex-col items-center justify-center text-center">
          {/* SAP Brand themed gradient logo */}
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 shadow-xl border border-indigo-400/25">
            <Layers className="h-9 w-9 text-white animate-pulse" />
          </div>
          <h2 className="mt-5 text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground via-foreground/90 to-foreground/60 bg-clip-text text-transparent">
            SAP AI Copilot
          </h2>
          <p className="mt-1.5 text-xs font-semibold uppercase tracking-wider text-indigo-400/80">
            Enterprise Knowledge Intelligence
          </p>
        </div>

        <div className="glass-panel border-border/80 bg-card/45 p-8 rounded-3xl shadow-2xl backdrop-blur-2xl">
          {/* Custom Pill tab selector */}
          <div className="flex p-1 mb-6 rounded-xl bg-muted/80 border border-border">
            <button
              onClick={() => { setIsLogin(true); setError(""); }}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
                isLogin 
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md" 
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(""); }}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
                !isLogin 
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md" 
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Consultant Registration
            </button>
          </div>

          {error && (
            <div className={`mb-5 flex items-start gap-3 rounded-xl p-3.5 text-xs border ${
              error.includes("successfully") 
                ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" 
                : "bg-red-500/10 text-red-500 border-red-500/20"
            }`}>
              <ShieldAlert className="h-4.5 w-4.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            {!isLogin && (
              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Full Name</label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                    <User className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Enter your name"
                    className="block w-full rounded-xl bg-muted/65 border border-border/80 py-3 pl-10 pr-4 text-sm text-foreground placeholder-muted-foreground/60 transition-all focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">User ID / Email</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                </div>
                <input
                  type="text"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter user ID or email"
                  className="block w-full rounded-xl bg-muted/65 border border-border/80 py-3 pl-10 pr-4 text-sm text-foreground placeholder-muted-foreground/60 transition-all focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Password</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <KeyRound className="h-4 w-4 text-muted-foreground" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="block w-full rounded-xl bg-muted/65 border border-border/80 py-3 pl-10 pr-10 text-sm text-foreground placeholder-muted-foreground/60 transition-all focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {!isLogin && (
              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">SAP User Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="block w-full rounded-xl bg-muted/65 border border-border/80 py-3 px-4 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:bg-slate-900"
                >
                  <option value="End User">End User</option>
                  <option value="SAP Consultant">SAP Consultant</option>
                  <option value="SAP Knowledge Manager">SAP Knowledge Manager</option>
                  <option value="Super Admin">Super Admin</option>
                </select>
              </div>
            )}

            {isLogin && (
              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="rounded border-border bg-card text-primary focus:ring-0 focus:ring-offset-0 h-4 w-4"
                  />
                  <span className="text-xs text-muted-foreground font-medium">Keep me signed in</span>
                </label>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="premium-glow-button group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 py-3.5 text-sm font-bold text-white border border-indigo-400/10 shadow-lg disabled:opacity-50"
            >
              {loading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <>
                  <span>{isLogin ? "Sign In to Copilot" : "Register Profile"}</span>
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Collapsible development helper quick credentials box */}
        <div className="rounded-2xl border border-border bg-card/30 backdrop-blur-sm overflow-hidden transition-all duration-300">
          <button
            onClick={() => setShowDevHints(!showDevHints)}
            className="flex w-full items-center justify-between px-5 py-3.5 text-left text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            <div className="flex items-center gap-2">
              <HelpCircle className="h-4 w-4 text-indigo-500/80" />
              <span>Developer Quick Sign-in Hints</span>
            </div>
            <span className="text-[10px] text-indigo-500 font-bold uppercase">{showDevHints ? "Hide" : "Show"}</span>
          </button>
          
          {showDevHints && (
            <div className="px-5 pb-4 text-xs text-muted-foreground border-t border-border/60 pt-3 space-y-2 bg-muted/50">
              <p>Admin Profile: <code className="text-indigo-600 dark:text-indigo-300 bg-muted px-1.5 py-0.5 rounded border border-border font-mono">admin</code> / <code className="text-indigo-600 dark:text-indigo-300 bg-muted px-1.5 py-0.5 rounded border border-border font-mono">admin</code></p>
              <p>Consultant Profile: <code className="text-blue-600 dark:text-blue-300 bg-muted px-1.5 py-0.5 rounded border border-border font-mono">consultant@sap.com</code> / <code className="text-blue-600 dark:text-blue-300 bg-muted px-1.5 py-0.5 rounded border border-border font-mono">consultantpassword</code></p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
