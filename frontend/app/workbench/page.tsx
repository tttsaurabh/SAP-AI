"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getAuthToken, getUserRole } from "@/lib/api";
import { 
  ArrowLeft, Terminal, AlertTriangle, CheckCircle, HelpCircle, Info,
  Settings, Key, Download, Cpu, Play, RefreshCw, FileCode, Check, Copy,
  Network, Share2, Layers, ShieldAlert, CheckSquare, ListTodo, LogIn, FlaskConical
} from "lucide-react";

// Small inline badge shown next to any panel that renders data from a
// simulated/demo backend response (i.e. the response included
// `simulated: true`). Complements the persistent page-level banner below —
// it doesn't replace it.
function SimulatedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-400">
      <FlaskConical className="h-3 w-3" />
      Simulated
    </span>
  );
}

export default function WorkbenchPage() {
  const router = useRouter();
  
  // Navigation & Tabs
  const [activeTab, setActiveTab] = useState<"diagnostics" | "snote" | "clean_core" | "transition" | "integration">("diagnostics");

  // Authentication role check
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push("/auth");
    }
  }, [router]);

  // --- STATE FOR DIAGNOSTICS ---
  const [dumpText, setDumpText] = useState(
    "Runtime Error         OBJECTS_OBJREF_NOT_ASSIGNED\n" +
    "Exception             CX_SY_REF_IS_INITIAL\n" +
    "Triggering Program    CL_USMD_RULE_SERVICE==========CP\n" +
    "Transaction           USMD_TCODE\n" +
    "Line Number           142\n" +
    "Call Stack:\n" +
    "  1. CL_USMD_RULE_SERVICE==========CP -> IF_USMD_RULE_SERVICE~CHECK_RULES\n" +
    "  2. ZCL_MDG_BP_VALIDATION=========CP -> IF_USMD_RULE_SERVICE~CHECK_RULES\n" +
    "System Environment:\n" +
    "  SAP_BASIS           752"
  );
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagResult, setDiagResult] = useState<any>(null);

  const runDumpAnalysis = async () => {
    setDiagLoading(true);
    setDiagResult(null);
    try {
      const result = await api.analyzeDump(dumpText);
      setDiagResult(result);
    } catch (err) {
      console.error(err);
      alert("Failed to analyze dump.");
    } finally {
      setDiagLoading(false);
    }
  };

  // --- STATE FOR SNOTE ---
  const [noteNumber, setNoteNumber] = useState("2732094");
  const [basisVersion, setBasisVersion] = useState("701");
  const [noteLoading, setNoteLoading] = useState(false);
  const [noteResult, setNoteResult] = useState<any>(null);

  // Authenticate SNOTE states
  const [authMode, setAuthMode] = useState<"certificate" | "credentials">("certificate");
  const [sUser, setSUser] = useState("");
  const [sPassword, setSPassword] = useState("");
  const [authStatus, setAuthStatus] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(false);

  const performHandshake = async () => {
    setAuthLoading(true);
    try {
      const result = await api.authenticateNotes(authMode, sUser, sPassword);
      setAuthStatus(result);
    } catch (err) {
      console.error(err);
      alert("Auth handshake failed.");
    } finally {
      setAuthLoading(false);
    }
  };

  const fetchNoteDetails = async () => {
    setNoteLoading(true);
    setNoteResult(null);
    try {
      const result = await api.searchNotes(noteNumber, basisVersion);
      setNoteResult(result);
    } catch (err) {
      console.error(err);
      alert("Failed to fetch Note details.");
    } finally {
      setNoteLoading(false);
    }
  };

  // --- STATE FOR CLEAN CORE ---
  const abapTemplates: Record<string, string> = {
    compliant: (
      "CLASS zcl_mdg_bp_reader DEFINITION\n" +
      "  PUBLIC FINAL CREATE PUBLIC.\n" +
      "  PUBLIC SECTION.\n" +
      "    INTERFACES if_oo_adt_classrun.\n" +
      "    METHODS read_business_partner_core\n" +
      "      IMPORTING !iv_bp_id TYPE c LENGTH 10\n" +
      "      RAISING cx_abap_invalid_value.\n" +
      "ENDCLASS.\n\n" +
      "CLASS zcl_mdg_bp_reader IMPLEMENTATION.\n" +
      "  METHOD read_business_partner_core.\n" +
      "    \" Entity Manipulation Language is used instead of direct DB updates\n" +
      "    READ ENTITIES OF i_businesspartnertp\n" +
      "      ENTITY BusinessPartner\n" +
      "        FIELDS ( BusinessPartner BusinessPartnerName )\n" +
      "        WITH VALUE #( ( %key-BusinessPartner = iv_bp_id ) )\n" +
      "      RESULT DATA(lt_bp_results)\n" +
      "      FAILED DATA(ls_failed).\n\n" +
      "    IF ls_failed IS NOT INITIAL.\n" +
      "      RAISE EXCEPTION NEW cx_abap_invalid_value( ).\n" +
      "    ENDIF.\n" +
      "  ENDMETHOD.\n" +
      "ENDCLASS."
    ),
    non_compliant: (
      "CLASS zcl_legacy_bp_writer DEFINITION\n" +
      "  PUBLIC CREATE PUBLIC.\n" +
      "  PUBLIC SECTION.\n" +
      "    METHODS update_bp_name\n" +
      "      IMPORTING\n" +
      "        iv_bp TYPE c\n" +
      "        iv_name TYPE c.\n" +
      "ENDCLASS.\n\n" +
      "CLASS zcl_legacy_bp_writer IMPLEMENTATION.\n" +
      "  METHOD update_bp_name.\n" +
      "    DATA ls_but000 TYPE but000.\n" +
      "    \n" +
      "    \" VIOLATION: Obsolete keyword\n" +
      "    MOVE iv_name TO ls_but000-name_org1.\n" +
      "    \n" +
      "    \" VIOLATION: Direct database update to standard staging table\n" +
      "    UPDATE but000 SET name_org1 = iv_name WHERE partner = iv_bp.\n" +
      "    \n" +
      "    \" VIOLATION: Classic service BAdI spots\n" +
      "    DATA lo_rules TYPE REF TO cl_usmd_rule_service.\n" +
      "    CREATE OBJECT lo_rules.\n" +
      "  ENDMETHOD.\n" +
      "ENDCLASS."
    )
  };

  const [codeText, setCodeText] = useState(abapTemplates.compliant);
  const [valLoading, setValLoading] = useState(false);
  const [valResult, setValResult] = useState<any>(null);

  const runCleanCoreValidation = async () => {
    setValLoading(true);
    setValResult(null);
    try {
      const result = await api.validateCode(codeText);
      setValResult(result);
    } catch (err) {
      console.error(err);
      alert("Failed to compile code.");
    } finally {
      setValLoading(false);
    }
  };

  // --- STATE FOR TRANSITIONS ---
  const [guideData, setGuideData] = useState<any>(null);
  const [guideLoading, setGuideLoading] = useState(false);

  const loadTransitionGuide = async () => {
    setGuideLoading(true);
    try {
      const data = await api.getTransitionGuide();
      setGuideData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setGuideLoading(false);
    }
  };

  useEffect(() => {
    loadTransitionGuide();
  }, []);

  // --- STATE FOR INTEGRATION ---
  const [targetSystem, setTargetSystem] = useState("crm");
  const [intLoading, setIntLoading] = useState(false);
  const [intResult, setIntResult] = useState<any>(null);

  const fetchIntegrationSpec = async () => {
    setIntLoading(true);
    setIntResult(null);
    try {
      const result = await api.getIntegrationSpec(targetSystem);
      setIntResult(result);
    } catch (err) {
      console.error(err);
      alert("Failed to generate integration specs.");
    } finally {
      setIntLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrationSpec();
  }, [targetSystem]);

  return (
    <div className="flex h-screen w-screen bg-[#05070e] text-[#f1f5f9] overflow-hidden">
      {/* Glow Effects */}
      <div className="absolute top-[10%] left-[10%] h-[350px] w-[350px] rounded-full bg-purple-600/5 blur-[110px] pointer-events-none" />
      <div className="absolute bottom-[10%] right-[10%] h-[350px] w-[350px] rounded-full bg-blue-600/5 blur-[110px] pointer-events-none" />

      {/* Main Container */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">

        {/* Persistent simulation-mode banner — not dismissable, always visible */}
        <div className="flex shrink-0 items-center gap-2.5 border-b border-amber-500/25 bg-amber-500/10 px-6 py-2.5 text-[11px] font-semibold text-amber-300">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
          <span>
            SIMULATION MODE — SAP Agentic Workbench uses hardcoded demo data (SNOTE search,
            diagnostics, ABAP validation, transition guide) and does not connect to a real SAP system.
          </span>
        </div>

        {/* Top Header */}
        <header className="flex h-16 items-center justify-between border-b border-slate-800/60 bg-slate-950/20 px-6 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/chat")}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/50 text-slate-400 hover:text-white transition-all"
              title="Return to Chat"
              aria-label="Return to chat"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-purple-400" />
              <h1 className="text-sm font-bold text-white tracking-wider">SAP AGENTIC WORKBENCH</h1>
            </div>
          </div>
          <div className="text-xs text-slate-500 font-semibold uppercase tracking-widest bg-slate-900/55 px-3 py-1.5 rounded-lg border border-slate-800/80">
            RAP & Clean Core Tools
          </div>
        </header>

        {/* Horizontal Navigation Tabs */}
        <div className="border-b border-slate-800/40 bg-slate-950/10 px-6 py-2 flex gap-2">
          <button
            onClick={() => setActiveTab("diagnostics")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
              activeTab === "diagnostics" 
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/30" 
                : "text-slate-400 hover:bg-slate-900/40 hover:text-white"
            }`}
          >
            <Terminal className="h-4 w-4" />
            <span>Diagnostics Analyzer</span>
          </button>
          <button
            onClick={() => setActiveTab("snote")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
              activeTab === "snote" 
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/30" 
                : "text-slate-400 hover:bg-slate-900/40 hover:text-white"
            }`}
          >
            <Download className="h-4 w-4" />
            <span>SNOTE verification</span>
          </button>
          <button
            onClick={() => setActiveTab("clean_core")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
              activeTab === "clean_core" 
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/30" 
                : "text-slate-400 hover:bg-slate-900/40 hover:text-white"
            }`}
          >
            <FileCode className="h-4 w-4" />
            <span>Clean Core Playground</span>
          </button>
          <button
            onClick={() => setActiveTab("transition")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
              activeTab === "transition" 
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/30" 
                : "text-slate-400 hover:bg-slate-900/40 hover:text-white"
            }`}
          >
            <ListTodo className="h-4 w-4" />
            <span>MDG Cloud-Ready Transition</span>
          </button>
          <button
            onClick={() => setActiveTab("integration")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
              activeTab === "integration" 
                ? "bg-purple-600/20 text-purple-300 border border-purple-500/30" 
                : "text-slate-400 hover:bg-slate-900/40 hover:text-white"
            }`}
          >
            <Network className="h-4 w-4" />
            <span>Integration Architectures</span>
          </button>
        </div>

        {/* Workbench Scroll Area */}
        <div className="flex-1 overflow-y-auto p-6">
          
          {/* TAB 1: DIAGNOSTICS ANALYZER */}
          {activeTab === "diagnostics" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full items-start">
              
              {/* Input Dump Form */}
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <h2 className="text-sm font-bold text-white uppercase tracking-wider">ST22 Runtime dump parser</h2>
                    <p className="text-[11px] text-slate-500">Paste your raw SAP System Dump error log below to parse diagnostic attributions.</p>
                  </div>
                  <button
                    onClick={() => setDumpText(
                      "Runtime Error         OBJECTS_OBJREF_NOT_ASSIGNED\n" +
                      "Exception             CX_SY_REF_IS_INITIAL\n" +
                      "Triggering Program    ZCL_CUSTOM_BP_ENHANCEMENT====CP\n" +
                      "Transaction           MDGIMG\n" +
                      "Line Number           52"
                    )}
                    className="text-[10px] text-purple-400 font-bold hover:underline"
                  >
                    Load Custom Error Sample
                  </button>
                </div>
                
                <textarea
                  value={dumpText}
                  onChange={(e) => setDumpText(e.target.value)}
                  rows={14}
                  className="w-full font-mono text-xs text-slate-300 bg-slate-950 border border-slate-800 p-4 rounded-xl focus:outline-none focus:border-purple-500/50"
                  placeholder="Paste ST22 dump details here..."
                />
                
                <button
                  onClick={runDumpAnalysis}
                  disabled={diagLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 py-3 text-xs font-bold text-white shadow-md transition-all active:scale-98 disabled:opacity-40"
                >
                  {diagLoading ? (
                    <RefreshCw className="h-4.5 w-4.5 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  <span>Run Parsing Diagnostics</span>
                </button>
              </div>

              {/* Analysis Output Panel */}
              <div className="space-y-6">
                {!diagResult ? (
                  <div className="bg-slate-950/20 border border-slate-800/40 rounded-2xl p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-3">
                    <Terminal className="h-8 w-8 text-slate-700" />
                    <p className="text-xs italic">Submit an SAP short dump log to initialize the pipeline diagnostics trace.</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {/* Header summary card */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Diagnostic Summary</h3>
                        {diagResult.simulated && <SimulatedBadge />}
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-900 text-center">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">Exception</p>
                          <p className="text-xs font-bold text-white truncate mt-1">{diagResult.exception}</p>
                        </div>
                        <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-900 text-center">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">Namespace</p>
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 mt-2 text-[10px] font-bold ${
                            diagResult.is_custom ? "bg-amber-500/10 text-amber-400" : "bg-blue-500/10 text-blue-400"
                          }`}>
                            {diagResult.attribution}
                          </span>
                        </div>
                        <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-900 text-center">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">Program</p>
                          <p className="text-xs font-bold text-white truncate mt-1">{diagResult.program}</p>
                        </div>
                        <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-900 text-center">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">T-Code</p>
                          <p className="text-xs font-bold text-white truncate mt-1">{diagResult.tcode}</p>
                        </div>
                      </div>
                    </div>

                    {/* Diagnostics pipeline visualization */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Execution Pipeline Trace</h3>
                      <div className="space-y-4">
                        {diagResult.pipeline.map((p: any, idx: number) => (
                          <div key={idx} className="flex gap-3.5 items-start">
                            <div className="flex flex-col items-center">
                              <div className="h-6 w-6 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-400 flex items-center justify-center text-xs font-bold font-mono">
                                {idx + 1}
                              </div>
                              {idx < diagResult.pipeline.length - 1 && (
                                <div className="w-0.5 h-6 bg-slate-800 mt-1" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0 bg-slate-950/60 p-3.5 rounded-xl border border-slate-900">
                              <div className="flex items-center justify-between">
                                <p className="text-xs font-bold text-white">{p.step}</p>
                                <span className="text-[9px] font-bold text-emerald-400 uppercase">{p.status}</span>
                              </div>
                              <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{p.detail}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Recommendations and troubleshooting details */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400">
                        <Info className="h-4 w-4 text-purple-400" />
                        <span>Root Cause & Remediations</span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed font-medium bg-slate-950 p-3.5 rounded-xl border border-slate-900">{diagResult.analysis_details}</p>
                      
                      <div className="space-y-2 pt-1">
                        {diagResult.recommendations.map((rec: string, idx: number) => (
                          <div key={idx} className="flex gap-2.5 items-start bg-slate-900/30 p-3 rounded-xl border border-slate-800/40">
                            <CheckCircle className="h-4 w-4 shrink-0 text-emerald-500" />
                            <p className="text-xs text-slate-300 leading-relaxed">{rec}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* TAB 2: SNOTE VERIFICATION */}
          {activeTab === "snote" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              
              {/* Credentials / Certificate Session manager */}
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4">
                <div className="flex items-center gap-2 mb-2">
                  <LogIn className="h-5 w-5 text-purple-400" />
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">Identity Backbone Session</h2>
                </div>

                <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-[10px] leading-relaxed text-amber-300/90">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  <span>Demo authentication — any credentials are accepted; no real SAP Support Portal connection is made.</span>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Authentication Protocol</label>
                  <div className="grid grid-cols-2 gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800">
                    <button
                      onClick={() => setAuthMode("certificate")}
                      className={`text-center py-2 text-xs font-semibold rounded-lg transition-all ${
                        authMode === "certificate" ? "bg-purple-600 text-white" : "text-slate-400 hover:text-white"
                      }`}
                    >
                      Client PFX Cert
                    </button>
                    <button
                      onClick={() => setAuthMode("credentials")}
                      className={`text-center py-2 text-xs font-semibold rounded-lg transition-all ${
                        authMode === "credentials" ? "bg-purple-600 text-white" : "text-slate-400 hover:text-white"
                      }`}
                    >
                      IAS S-User Credentials
                    </button>
                  </div>
                </div>

                {authMode === "credentials" && (
                  <div className="space-y-3 pt-1">
                    <div className="space-y-1">
                      <label className="text-[10px] text-slate-500 font-bold uppercase">S-User Account ID</label>
                      <input
                        type="text"
                        value={sUser}
                        onChange={(e) => setSUser(e.target.value)}
                        placeholder="e.g. S002495819"
                        className="w-full bg-slate-950 border border-slate-800/80 p-2.5 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] text-slate-500 font-bold uppercase">IAS Password</label>
                      <input
                        type="password"
                        value={sPassword}
                        onChange={(e) => setSPassword(e.target.value)}
                        placeholder="••••••••••••"
                        className="w-full bg-slate-950 border border-slate-800/80 p-2.5 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
                      />
                    </div>
                  </div>
                )}

                {authMode === "certificate" && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-900 text-[11px] text-slate-400 leading-relaxed">
                    Uses secure TLS cryptographic handshake via your client **SAP Passport PFX** certificate directly with **accounts.sap.com**, bypassing manual credentials.
                  </div>
                )}

                <button
                  onClick={performHandshake}
                  disabled={authLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-900 border border-slate-800 hover:border-purple-500/40 text-xs font-bold py-3 transition-all"
                >
                  {authLoading ? <RefreshCw className="h-4.5 w-4.5 animate-spin" /> : <Key className="h-4 w-4" />}
                  <span>Harvest Session Token</span>
                </button>

                {authStatus && (
                  <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 space-y-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                        <CheckCircle className="h-4.5 w-4.5" />
                        <span>{authStatus.status}</span>
                      </div>
                      {authStatus.simulated && <SimulatedBadge />}
                    </div>
                    <div className="bg-slate-950/80 p-2 rounded border border-slate-900 text-[10px] text-slate-500 font-mono break-all leading-tight">
                      Cached in-memory (demo session, not persisted to disk): {authStatus.session_cookie}
                    </div>
                  </div>
                )}
              </div>

              {/* Note details lookup & Release checker */}
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4 lg:col-span-2">
                <div className="flex items-center gap-2 mb-2">
                  <Download className="h-5 w-5 text-blue-400" />
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">OData Notes Backbone Crawler</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">SAP Note / KBA Number</label>
                    <input
                      type="text"
                      value={noteNumber}
                      onChange={(e) => setNoteNumber(e.target.value)}
                      placeholder="e.g. 2187425"
                      className="w-full bg-slate-950 border border-slate-800/80 p-3 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
                    />
                  </div>
                  
                  <div className="space-y-1">
                    <label className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Base Release Release (SAP_BASIS)</label>
                    <select
                      value={basisVersion}
                      onChange={(e) => setBasisVersion(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800/80 p-3 rounded-xl text-xs text-white focus:outline-none focus:border-purple-500"
                    >
                      <option value="750">750 (S/4HANA Standard)</option>
                      <option value="740">740 (NetWeaver 7.40)</option>
                      <option value="702">702 (Low Release NW 7.02)</option>
                      <option value="701">701 (Low Release NW 7.01)</option>
                    </select>
                  </div>
                </div>

                <button
                  onClick={fetchNoteDetails}
                  disabled={noteLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 py-3 text-xs font-bold text-white shadow-md transition-all disabled:opacity-40"
                >
                  {noteLoading ? <RefreshCw className="h-4.5 w-4.5 animate-spin" /> : <Play className="h-4 w-4" />}
                  <span>Retrieve Note Instructions</span>
                </button>

                {noteResult && (
                  <div className="space-y-4 pt-2">
                    <div className="flex justify-end">
                      {noteResult.simulated && <SimulatedBadge />}
                    </div>
                    {/* Low release alert */}
                    {noteResult.low_release_warning && (
                      <div className="flex gap-3 bg-red-500/10 border border-red-500/25 p-4 rounded-xl text-xs text-red-400 leading-relaxed">
                        <ShieldAlert className="h-5 w-5 shrink-0 text-red-500 mt-0.5" />
                        <span>{noteResult.warning_message}</span>
                      </div>
                    )}

                    {/* Output metadata */}
                    {noteResult.found ? (
                      <div className="space-y-4">
                        <div className="bg-slate-950 p-5 rounded-xl border border-slate-900 space-y-4">
                          <div className="flex items-center justify-between border-b border-slate-850 pb-2">
                            <span className="text-xs font-bold text-purple-400">Note ID: {noteResult.note_details.note_number}</span>
                            <span className="text-[10px] text-slate-500 font-bold bg-slate-900 border border-slate-800/80 px-2 py-0.5 rounded uppercase">
                              {noteResult.note_details.delivery_format}
                            </span>
                          </div>
                          
                          <div className="space-y-1">
                            <h3 className="text-xs font-bold text-white uppercase tracking-wider">Note Title</h3>
                            <p className="text-xs text-slate-300 leading-relaxed font-semibold">{noteResult.note_details.title}</p>
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-[10px] text-slate-500 font-bold uppercase">Software Validity Range</p>
                              <p className="text-xs font-bold text-white mt-0.5">{noteResult.note_details.release_range}</p>
                            </div>
                            <div>
                              <p className="text-[10px] text-slate-500 font-bold uppercase">Prerequisites</p>
                              <p className="text-xs font-bold text-white mt-0.5">
                                {noteResult.note_details.prerequisites.length > 0 
                                  ? noteResult.note_details.prerequisites.join(", ") 
                                  : "None"}
                              </p>
                            </div>
                          </div>
                        </div>

                        <div className="bg-slate-950 p-5 rounded-xl border border-slate-900 space-y-2">
                          <h4 className="text-[10px] text-slate-500 font-bold uppercase">Manual Code Adjustments / Steps</h4>
                          <pre className="text-[11px] font-mono text-slate-300 bg-slate-900 p-3.5 rounded border border-slate-850 whitespace-pre-wrap leading-relaxed">
                            {noteResult.note_details.manual_steps}
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs italic text-center text-red-400 py-4">{noteResult.message}</p>
                    )}
                  </div>
                )}
              </div>

            </div>
          )}

          {/* TAB 3: CLEAN CORE LAB */}
          {activeTab === "clean_core" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start h-full">
              
              {/* Left pane: code editor */}
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <h2 className="text-sm font-bold text-white uppercase tracking-wider">Developer compliance sandbox</h2>
                    <p className="text-[11px] text-slate-500">Paste your ABAP class logic to test clean core compatibility.</p>
                  </div>
                  
                  <div className="flex gap-2">
                    <button
                      onClick={() => setCodeText(abapTemplates.compliant)}
                      className="text-[10px] text-emerald-400 border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1 rounded hover:bg-emerald-500/10 transition-all font-semibold"
                    >
                      Compliant Example
                    </button>
                    <button
                      onClick={() => setCodeText(abapTemplates.non_compliant)}
                      className="text-[10px] text-red-400 border border-red-500/20 bg-red-500/5 px-2.5 py-1 rounded hover:bg-red-500/10 transition-all font-semibold"
                    >
                      Non-Compliant Example
                    </button>
                  </div>
                </div>

                <textarea
                  value={codeText}
                  onChange={(e) => setCodeText(e.target.value)}
                  rows={16}
                  className="w-full font-mono text-xs text-slate-300 bg-slate-950 border border-slate-800 p-4 rounded-xl focus:outline-none focus:border-purple-500/50"
                  placeholder="Insert ABAP code block..."
                />

                <button
                  onClick={runCleanCoreValidation}
                  disabled={valLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 py-3 text-xs font-bold text-white shadow-md transition-all disabled:opacity-40"
                >
                  {valLoading ? <RefreshCw className="h-4.5 w-4.5 animate-spin" /> : <Play className="h-4 w-4" />}
                  <span>Evaluate Compliance Grade</span>
                </button>
              </div>

              {/* Right pane: compliance scores & remediation */}
              <div className="space-y-6">
                {!valResult ? (
                  <div className="bg-slate-950/20 border border-slate-800/40 rounded-2xl p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-3">
                    <FileCode className="h-8 w-8 text-slate-700" />
                    <p className="text-xs italic">Submit ABAP code to verify Clean-Core compliance levels.</p>
                  </div>
                ) : (
                  <div className="space-y-6 animate-fade-in">
                    
                    {/* Score card */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Grading Output</h3>
                        {valResult.simulated && <SimulatedBadge />}
                      </div>
                      <div className="flex items-center gap-4">
                        <div className={`h-16 w-16 rounded-2xl flex flex-col items-center justify-center font-extrabold text-lg border shadow-lg ${
                          valResult.grade === "Level A" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-emerald-500/5" :
                          valResult.grade === "Level B" ? "bg-blue-500/10 border-blue-500/30 text-blue-400 shadow-blue-500/5" :
                          valResult.grade === "Level C" ? "bg-amber-500/10 border-amber-500/30 text-amber-400 shadow-amber-500/5" :
                          "bg-red-500/10 border-red-500/30 text-red-400 shadow-red-500/5"
                        }`}>
                          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">GRADE</span>
                          {valResult.grade.split(" ")[1]}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-extrabold text-white leading-tight">{valResult.status}</p>
                          <p className="text-[11px] text-slate-400 mt-1 leading-normal">{valResult.description}</p>
                        </div>
                      </div>
                    </div>

                    {/* Verification gates checklist */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">Verification Gates</h3>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between bg-slate-950 p-3 rounded-xl border border-slate-900">
                          <span className="text-xs font-bold text-slate-300">1. Offline Parsing Gate</span>
                          <span className="text-[10px] font-bold text-slate-400 bg-slate-900 border border-slate-850 px-2 py-0.5 rounded">{valResult.gates.offline_linter}</span>
                        </div>
                        <div className="flex items-center justify-between bg-slate-950 p-3 rounded-xl border border-slate-900">
                          <span className="text-xs font-bold text-slate-300">2. Online ADT Compiler</span>
                          <span className="text-[10px] font-bold text-slate-400 bg-slate-900 border border-slate-850 px-2 py-0.5 rounded">{valResult.gates.online_compilation}</span>
                        </div>
                        <div className="flex items-center justify-between bg-slate-950 p-3 rounded-xl border border-slate-900">
                          <span className="text-xs font-bold text-slate-300">3. Execution Validation Gate</span>
                          <span className="text-[10px] font-bold text-slate-400 bg-slate-900 border border-slate-850 px-2 py-0.5 rounded">{valResult.gates.unit_test_validation}</span>
                        </div>
                      </div>
                    </div>

                    {/* Violations and warnings */}
                    {valResult.violations.length > 0 && (
                      <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-red-400">
                          <AlertTriangle className="h-4 w-4" />
                          <span>Syntax Violations Found</span>
                        </div>
                        <div className="space-y-2">
                          {valResult.violations.map((v: any, idx: number) => (
                            <div key={idx} className="bg-slate-950 border border-slate-900 p-3.5 rounded-xl space-y-1">
                              <div className="flex items-center justify-between text-[10px] font-bold uppercase">
                                <span className="text-slate-500">{v.rule}</span>
                                <span className={`px-1.5 py-0.5 rounded ${
                                  v.severity === "Critical" ? "bg-red-500/10 text-red-400" :
                                  v.severity === "High" ? "bg-amber-500/10 text-amber-400" :
                                  "bg-blue-500/10 text-blue-400"
                                }`}>{v.severity}</span>
                              </div>
                              <p className="text-xs text-slate-300 mt-1 leading-normal font-medium">{v.message}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Remediation code block suggestion */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400">
                        <Info className="h-4 w-4 text-purple-400" />
                        <span>Remediation Advice</span>
                      </div>
                      <pre className="text-[11px] font-mono text-slate-300 bg-slate-950 p-4 rounded-xl border border-slate-900 whitespace-pre-wrap leading-relaxed">
                        {valResult.remediation_advice}
                      </pre>
                    </div>

                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: TRANSITION CHECKLIST */}
          {activeTab === "transition" && (
            <div className="max-w-4xl mx-auto space-y-6">
              
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4">
                <div className="space-y-1 border-b border-slate-850 pb-4">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-base font-bold text-white uppercase tracking-wider">Cloud-Ready Switch & Transition Guide</h2>
                    {guideData?.simulated && <SimulatedBadge />}
                  </div>
                  <p className="text-xs text-slate-500 leading-normal">
                    To activate Cloud-Ready mode inside S/4HANA instances, follow this customization guideline derived from implementation logs.
                  </p>
                </div>

                {guideLoading ? (
                  <div className="flex justify-center py-12">
                    <RefreshCw className="h-8 w-8 animate-spin text-purple-500" />
                  </div>
                ) : guideData ? (
                  <div className="space-y-6">
                    {/* Setup steps */}
                    <div className="space-y-3.5">
                      <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 block mb-2">Technical Implementation Steps</h3>
                      {guideData.steps.map((step: any) => (
                        <div key={step.id} className="flex gap-4 items-start bg-slate-950/65 border border-slate-900 hover:border-slate-850 p-4 rounded-xl transition-all">
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-600/10 border border-purple-500/25 text-purple-400 text-xs font-bold font-mono">
                            0{step.id}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-bold text-white">{step.title}</h4>
                              <span className="text-[9px] font-bold bg-slate-900 border border-slate-800 text-slate-500 px-2 py-0.5 rounded uppercase">{step.status}</span>
                            </div>
                            <p className="text-xs text-slate-400 leading-relaxed mt-1.5">{step.action}</p>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Coexistence verification checks */}
                    <div className="bg-slate-950/20 border border-slate-800/60 p-5 rounded-xl space-y-3">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400">
                        <CheckSquare className="h-4.5 w-4.5 text-purple-400" />
                        <span>Parallel Coexistence Checks</span>
                      </div>
                      <p className="text-[11px] text-slate-500 leading-relaxed">
                        Because Cloud-Ready Mode runs side-by-side with Classic MDG (e.g. executing Business Partner in cloud mode and Material in classic mode), verify these items:
                      </p>
                      <div className="space-y-2 mt-2">
                        {guideData.coexistence_checks.map((check: string, idx: number) => (
                          <div key={idx} className="flex gap-2 items-center bg-slate-950 p-3 rounded-lg border border-slate-900 text-xs text-slate-300">
                            <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                            <span>{check}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs italic text-slate-500">No guide data loaded.</p>
                )}
              </div>

            </div>
          )}

          {/* TAB 5: INTEGRATION ARCHITECTURES */}
          {activeTab === "integration" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start h-full">
              
              {/* Left pane: selector */}
              <div className="bg-slate-950/40 border border-slate-800/80 p-6 rounded-2xl space-y-4">
                <div className="space-y-1">
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">Integration profile planner</h2>
                  <p className="text-[11px] text-slate-500">Select your target application server to view secure routing configurations.</p>
                </div>

                <div className="space-y-2 pt-2">
                  {[
                    { id: "crm", title: "Salesforce / CRM System", desc: "RESTful Synchronous address validation" },
                    { id: "warehouse", title: "Enterprise Data Warehouse", desc: "Decoupled Asynchronous queues" },
                    { id: "datalake", title: "AWS / Google Cloud Storage", desc: "SFTP Bulk Batch Extract scheduler" },
                    { id: "saas", title: "SAP Ariba / SaaS Central", desc: "Master Data Integration hub (mTLS)" }
                  ].map((sys) => (
                    <button
                      key={sys.id}
                      onClick={() => setTargetSystem(sys.id)}
                      className={`w-full text-left p-3.5 rounded-xl border transition-all ${
                        targetSystem === sys.id 
                          ? "bg-purple-600/10 border-purple-500/40 text-purple-300 shadow-md shadow-purple-600/5" 
                          : "bg-slate-950 border-slate-900 hover:border-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      <h3 className="text-xs font-bold leading-normal">{sys.title}</h3>
                      <p className="text-[10px] text-slate-500 leading-normal mt-1">{sys.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Right pane: visualizer & instructions */}
              <div className="lg:col-span-2 space-y-6">
                {intLoading ? (
                  <div className="flex justify-center py-24">
                    <RefreshCw className="h-8 w-8 animate-spin text-purple-500" />
                  </div>
                ) : intResult ? (
                  <div className="space-y-6">
                    {/* Visual Topology Diagram */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <div className="flex items-center justify-between border-b border-slate-850 pb-2">
                        <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500">Secure Network Topology Diagram</h4>
                        <div className="flex items-center gap-2">
                          {intResult.simulated && <SimulatedBadge />}
                          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">PROTOCOL: {intResult.protocol}</span>
                        </div>
                      </div>
                      
                      {/* ASCII Diagram representation */}
                      <pre className="text-[10px] leading-relaxed font-mono text-purple-300 bg-slate-950 p-4 rounded-xl border border-slate-900 overflow-x-auto">
{`   ┌────────────────────────────────────────────────────────┐
   │                  SAP BTP CLOUD TENANT                  │
   │                                                        │
   │      ┌─────────────────────────┐        ┌───────────┐  │
   │      │  SAP Integration Suite  │◄──────►│  Event    │  │
   │      │  (iFlow XML Router)     │        │  Mesh     │  │
   │      └────────────▲────────────┘        └─────▲─────┘  │
   └───────────────────┼───────────────────────────┼────────┘
                       │ TLS Secure Tunnel         │ AMQP Protocol
                       ▼                           ▼
   ┌────────────────────────────────────────────────────────┐
   │                  ON-PREMISE ENTERPRISE                 │
   │                                                        │
   │      ┌─────────────────────────┐        ┌───────────┐  │
   │      │   SAP Cloud Connector   │◄──────►│ S/4 HANA  │  │
   │      │   (Principal Proxy)     │        │ MDG Core  │  │
   │      └─────────────────────────┘        └───────────┘  │
   └────────────────────────────────────────────────────────┘
                       │
                       ▼
         TARGET ROUTE: [${intResult.title}]`}
                      </pre>
                    </div>

                    {/* Metadata breakdown */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-4">
                      <div>
                        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Replication Profile</h3>
                        <h2 className="text-sm font-extrabold text-white mt-1.5">{intResult.title}</h2>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-900">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">Integration Pattern</p>
                          <p className="text-xs font-bold text-white mt-1">{intResult.pattern}</p>
                        </div>
                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-900">
                          <p className="text-[10px] text-slate-500 font-bold uppercase">Connection Adapter</p>
                          <p className="text-xs font-bold text-white mt-1">{intResult.adapter}</p>
                        </div>
                      </div>

                      <div className="bg-slate-950 p-4 rounded-xl border border-slate-900 space-y-1">
                        <p className="text-[10px] text-slate-500 font-bold uppercase">Middleware & Gateway Security</p>
                        <p className="text-xs font-bold text-white leading-normal">{intResult.security}</p>
                      </div>
                    </div>

                    {/* Step-by-step setup guides */}
                    <div className="bg-slate-950/40 border border-slate-800/80 p-5 rounded-2xl space-y-3">
                      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500">Replication Setup Procedure</h4>
                      <div className="space-y-2">
                        {intResult.steps.map((step: string, idx: number) => (
                          <div key={idx} className="bg-slate-950 p-3 rounded-xl border border-slate-900 text-xs text-slate-300 leading-relaxed font-medium">
                            {step}
                          </div>
                        ))}
                      </div>
                    </div>

                  </div>
                ) : (
                  <p className="text-xs italic text-slate-500">Select a target configuration system profile.</p>
                )}
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
