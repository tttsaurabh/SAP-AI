"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getAuthToken, getUserRole, DocumentInfo, ChunkInfo } from "@/lib/api";
import { 
  FileText, ArrowLeft, Upload, Trash2, Search, Database, Layers,
  Activity, BarChart3, AlertCircle, ThumbsUp, ThumbsDown, Eye, X, BookOpen, ChevronRight, Check
} from "lucide-react";

export default function AdminPage() {
  const router = useRouter();
  
  // State
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [analytics, setAnalytics] = useState<any>({
    total_documents: 0,
    total_chunks: 0,
    total_size_bytes: 0,
    status_counts: {},
    collection_counts: {}
  });
  const [chatAnalytics, setChatAnalytics] = useState<any>({
    total_conversations: 0,
    total_messages: 0,
    total_feedbacks: 0,
    positive_feedbacks: 0,
    negative_feedbacks: 0
  });

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCollection, setUploadCollection] = useState("Default");
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  
  // Custom states for premium features
  const [dragActive, setDragActive] = useState(false);
  const [showConfirmDeleteId, setShowConfirmDeleteId] = useState<number | null>(null);
  
  // Chunk inspector states
  const [selectedDocForInspection, setSelectedDocForInspection] = useState<DocumentInfo | null>(null);
  const [docChunks, setDocChunks] = useState<ChunkInfo[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  useEffect(() => {
    const token = getAuthToken();
    const role = getUserRole();
    const adminRoles = ["Super Admin", "SAP Knowledge Manager", "SAP Consultant"];
    
    if (!token || !adminRoles.includes(role)) {
      router.push("/chat");
      return;
    }

    loadDocuments();
    loadAnalytics();
  }, [router]);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (!hasProcessing) return;

    const interval = setInterval(() => {
      loadDocuments();
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const loadDocuments = async () => {
    try {
      const data = await api.listDocuments();
      setDocuments(data);
    } catch (err) {
      console.error("Failed to load documents", err);
    }
  };

  const loadAnalytics = async () => {
    try {
      const docsData = await api.getDocumentAnalytics();
      setAnalytics(docsData);
      
      const chatsData = await api.getConversationAnalytics();
      setChatAnalytics(chatsData);
    } catch (err) {
      console.error("Failed to load analytics", err);
    }
  };

  const handleUploadSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!uploadFile) return;
    setUploadError("");
    setUploadLoading(true);

    try {
      await api.uploadDocument(uploadFile, uploadCollection);
      setUploadFile(null);
      const fileInput = document.getElementById("file-upload") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
      
      loadDocuments();
      loadAnalytics();
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload document");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleDeleteDoc = async (id: number) => {
    try {
      await api.deleteDocument(id);
      setDocuments(documents.filter(d => d.id !== id));
      loadAnalytics();
      setShowConfirmDeleteId(null);
    } catch (err) {
      console.error("Failed to delete document", err);
    }
  };

  const handleInspectChunks = async (doc: DocumentInfo) => {
    setSelectedDocForInspection(doc);
    setChunksLoading(true);
    try {
      const data = await api.getDocumentChunks(doc.id);
      setDocChunks(data);
    } catch (err) {
      console.error("Failed to load chunks for document", err);
    } finally {
      setChunksLoading(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  // Drag and drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setUploadFile(e.dataTransfer.files[0]);
    }
  };

  // Get file icon color based on extension
  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return <span className="bg-red-500/10 text-red-400 border border-red-500/20 px-1.5 py-0.5 rounded font-mono font-bold text-[9px] mr-2">PDF</span>;
    if (ext === 'docx' || ext === 'doc') return <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded font-mono font-bold text-[9px] mr-2">DOC</span>;
    if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') return <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold text-[9px] mr-2">XLS</span>;
    return <span className="bg-slate-500/10 text-slate-400 border border-slate-500/20 px-1.5 py-0.5 rounded font-mono font-bold text-[9px] mr-2">TXT</span>;
  };

  const filteredDocs = documents.filter(d => 
    d.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.collection_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-screen w-screen bg-background text-foreground overflow-hidden">
      
      {/* Admin Content Workspace */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Glow Effects */}
        <div className="absolute top-[10%] left-[10%] h-[350px] w-[350px] rounded-full bg-purple-600/3 dark:bg-purple-600/5 blur-[100px] pointer-events-none" />
        <div className="absolute bottom-[10%] right-[10%] h-[400px] w-[400px] rounded-full bg-blue-600/3 dark:bg-blue-600/5 blur-[110px] pointer-events-none" />

        {/* Title Navbar */}
        <div className="flex h-16 items-center justify-between border-b border-border bg-card/20 px-6 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/chat")}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted/40 text-muted-foreground hover:text-foreground transition-all"
              aria-label="Back to chat"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-indigo-500 dark:text-indigo-400" />
              <h1 className="text-xs font-bold text-foreground tracking-widest uppercase">SAP AI Knowledge Center</h1>
            </div>
          </div>
        </div>

        {/* Admin Scroll Workspace */}
        <div className="flex-1 overflow-y-auto px-8 py-8 space-y-8 z-10">
          
          {/* Analytics Stats Grid with mini inline sparks */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            
            <div className="glass-card bg-card/25 p-5 rounded-2xl border border-border flex items-center justify-between relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-1 h-full bg-purple-500" />
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Indexed Documents</p>
                <p className="text-2xl font-extrabold text-foreground mt-1.5">{analytics.total_documents}</p>
                <p className="text-[9px] text-muted-foreground font-semibold mt-1 flex items-center gap-1">
                  <span className="text-emerald-500">↑ Up to date</span> from registry
                </p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <FileText className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-card/25 p-5 rounded-2xl border border-border flex items-center justify-between relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-1 h-full bg-blue-500" />
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Total Semantic Chunks</p>
                <p className="text-2xl font-extrabold text-foreground mt-1.5">{analytics.total_chunks}</p>
                <p className="text-[9px] text-muted-foreground font-semibold mt-1">
                  Average size ~450 tokens
                </p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                <Layers className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-card/25 p-5 rounded-2xl border border-border flex items-center justify-between relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500" />
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Storage Occupied</p>
                <p className="text-2xl font-extrabold text-foreground mt-1.5">{formatBytes(analytics.total_size_bytes)}</p>
                <p className="text-[9px] text-muted-foreground font-semibold mt-1">
                  SQLite database file
                </p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Activity className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-card/25 p-5 rounded-2xl border border-border flex items-center justify-between relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500" />
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Copilot Feedback</p>
                <div className="flex items-center gap-3 mt-2">
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                    <ThumbsUp className="h-3 w-3" /> {chatAnalytics.positive_feedbacks}
                  </span>
                  <span className="text-xs font-bold text-red-400 flex items-center gap-1.5 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full">
                    <ThumbsDown className="h-3 w-3" /> {chatAnalytics.negative_feedbacks}
                  </span>
                </div>
              </div>
              <div className="h-10 w-10 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                <BarChart3 className="h-5 w-5" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Upload form Panel */}
            <div className="glass-panel bg-card/35 p-6 rounded-2xl border-border">
              <div className="flex items-center gap-2 mb-4">
                <Upload className="h-5 w-5 text-indigo-400 animate-bounce" />
                <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Ingest Knowledge</h2>
              </div>
              
              {uploadError && (
                <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-xs text-red-400">
                  <AlertCircle className="h-5 w-5 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <form onSubmit={handleUploadSubmit} className="space-y-4" onDragEnter={handleDrag}>
                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Document Source</label>
                  
                  {/* Premium drag and drop zone */}
                  <div className="flex items-center justify-center w-full">
                    <label 
                      onDragEnter={handleDrag}
                      onDragOver={handleDrag}
                      onDragLeave={handleDrag}
                      onDrop={handleDrop}
                      className={`flex flex-col items-center justify-center w-full h-44 border-2 border-dashed rounded-2xl cursor-pointer transition-all ${
                        dragActive 
                          ? "border-indigo-500 bg-indigo-500/5 shadow-inner" 
                          : "border-border bg-muted/30 hover:bg-muted/60 hover:border-border"
                      }`}
                    >
                      <div className="flex flex-col items-center justify-center pt-5 pb-6 text-center px-4">
                        <div className="h-10 w-10 rounded-full bg-muted border border-border flex items-center justify-center mb-2.5 text-indigo-400">
                          {uploadFile ? <Check className="w-5 h-5 text-emerald-400 animate-pulse" /> : <Upload className="w-5 h-5" />}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {uploadFile ? (
                            <span className="font-bold text-foreground truncate max-w-[200px] block">{uploadFile.name}</span>
                          ) : (
                            <>
                              <span className="font-bold text-indigo-550 dark:text-indigo-400 hover:underline">Click to attach</span> or drop files here
                            </>
                          )}
                        </p>
                        <p className="text-[9px] text-muted-foreground font-semibold mt-1">PDF, DOCX, Spreadsheets up to 50MB</p>
                      </div>
                      <input 
                        id="file-upload" 
                        type="file" 
                        required 
                        className="hidden" 
                        onChange={(e) => {
                          if (e.target.files && e.target.files.length > 0) {
                            setUploadFile(e.target.files[0]);
                          }
                        }}
                      />
                    </label>
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Active Domain Grouping</label>
                  <input
                    type="text"
                    value={uploadCollection}
                    onChange={(e) => setUploadCollection(e.target.value)}
                    placeholder="e.g. Master Data, BRF Workflow"
                    className="block w-full rounded-xl bg-muted border border-border py-3 px-4 text-xs text-foreground placeholder-muted-foreground/60 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={uploadLoading || !uploadFile}
                  className="premium-glow-button w-full rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 py-3 text-xs font-bold text-white shadow-md disabled:opacity-40"
                >
                  {uploadLoading ? (
                    <div className="flex items-center justify-center gap-2">
                      <div className="h-4.5 w-4.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Parsing & Semantic Indexing...</span>
                    </div>
                  ) : "Index Knowledge Source"}
                </button>
              </form>
            </div>

            {/* Ingestion Table Panel */}
            <div className="glass-panel bg-card/35 p-6 rounded-2xl border-border lg:col-span-2 flex flex-col overflow-hidden h-[450px] relative">
              <div className="flex items-center justify-between mb-4.5">
                <div className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-blue-400" />
                  <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Ingestion Registry</h2>
                </div>
                
                {/* Search document */}
                <div className="relative w-48">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                    <Search className="h-3.5 w-3.5 text-muted-foreground" />
                  </span>
                  <input
                    type="text"
                    placeholder="Search docs..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-lg bg-muted border border-border/60 py-2 pl-8 pr-3 text-xs text-foreground placeholder-muted-foreground/60 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Document rows */}
              <div className="flex-1 overflow-y-auto pr-1">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground uppercase tracking-widest font-bold text-[9px]">
                      <th className="py-2.5">Filename</th>
                      <th className="py-2.5">Domain</th>
                      <th className="py-2.5">Size</th>
                      <th className="py-2.5">Status</th>
                      <th className="py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDocs.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-muted-foreground font-medium italic">
                          No indexing documents found.
                        </td>
                      </tr>
                    ) : (
                      filteredDocs.map((doc) => (
                        <tr key={doc.id} className="border-b border-border/40 hover:bg-muted/15">
                          <td className="py-3 font-semibold text-foreground max-w-xs truncate flex items-center">
                            {getFileIcon(doc.filename)}
                            <span>{doc.filename}</span>
                          </td>
                          <td className="py-3 text-muted-foreground font-semibold">{doc.collection_name}</td>
                          <td className="py-3 text-muted-foreground/80">{formatBytes(doc.file_size)}</td>
                          <td className="py-3">
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[9px] font-bold ${
                                doc.status === "active" ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" :
                                doc.status === "failed" ? "bg-red-500/10 text-red-500 border border-red-500/20" :
                                "bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse"
                              }`}
                              title={doc.status === "failed" ? (doc.error_message || "Ingestion failed (no details).") : undefined}
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${
                                doc.status === "active" ? "bg-emerald-500" :
                                doc.status === "failed" ? "bg-red-500" :
                                "bg-amber-500 animate-ping"
                              }`} />
                              {doc.status}
                            </span>
                          </td>
                          <td className="py-3 text-right space-x-2.5">
                            <button
                              onClick={() => handleInspectChunks(doc)}
                              className="text-muted-foreground hover:text-indigo-500 transition-all p-1"
                              title="Inspect document segments/chunks"
                              aria-label={`Inspect chunks for ${doc.filename}`}
                            >
                              <Eye className="h-4 w-4 inline" />
                            </button>
                            
                            {/* Inline modal confirmation delete helper */}
                            {showConfirmDeleteId === doc.id ? (
                              <div className="absolute right-6 mt-1 bg-card border border-red-500/35 p-3.5 rounded-xl z-20 shadow-2xl flex flex-col gap-2 max-w-xs text-left">
                                <p className="text-[10px] text-foreground leading-normal font-semibold">Delete document, SQL chunks, and vectors?</p>
                                <div className="flex gap-2 justify-end">
                                  <button onClick={() => setShowConfirmDeleteId(null)} className="text-[10px] border border-border bg-muted text-muted-foreground px-2 py-1 rounded">No</button>
                                  <button onClick={() => handleDeleteDoc(doc.id)} className="text-[10px] bg-red-600 hover:bg-red-500 text-white px-2 py-1 rounded">Yes, delete</button>
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => setShowConfirmDeleteId(doc.id)}
                                className="text-muted-foreground hover:text-red-500 transition-all p-1"
                                title="Remove document and embeddings"
                                aria-label={`Delete ${doc.filename}`}
                              >
                                <Trash2 className="h-4 w-4 inline" />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        {/* --- Chunk Inspector Overlay Panel --- */}
        {selectedDocForInspection && (
          <div className="absolute inset-0 bg-background/65 backdrop-blur-sm z-50 flex justify-end">
            <div className="w-full max-w-2xl h-full bg-card border-l border-border p-6 flex flex-col shadow-2xl relative animate-slide-in">
              <div className="flex items-center justify-between border-b border-border pb-4 mb-4">
                <div className="flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-indigo-500 dark:text-indigo-400" />
                  <div className="min-w-0">
                    <h3 className="font-bold text-foreground text-sm">Chunk Segment Inspector</h3>
                    <p className="text-[10px] text-muted-foreground truncate">{selectedDocForInspection.filename}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedDocForInspection(null)}
                  className="text-muted-foreground hover:text-foreground transition-all"
                  aria-label="Close chunk inspector"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Chunk list scroll */}
              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {chunksLoading ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                    <p className="text-xs text-slate-550">Loading chunk payloads...</p>
                  </div>
                ) : docChunks.length === 0 ? (
                  <p className="text-center text-xs text-muted-foreground italic py-12">No chunks found for this file.</p>
                ) : (
                  docChunks.map((chunk, idx) => (
                    <div key={chunk.id} className="rounded-xl border border-border/80 bg-muted/45 p-4 space-y-3 hover:border-border transition-all">
                      <div className="flex items-center justify-between border-b border-border/50 pb-2 text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
                        <span>Chunk #{idx + 1} (Index: {chunk.chunk_index})</span>
                        <span className="text-indigo-650 dark:text-indigo-455">Page: {chunk.page_number || 1} | Section: {chunk.section_header || "N/A"}</span>
                      </div>
                      
                      <div className="text-xs text-foreground leading-relaxed font-mono whitespace-pre-wrap bg-muted p-3 rounded-lg border border-border">
                        {chunk.text}
                      </div>

                      {/* Display embedding metadata JSON */}
                      <div className="text-[10px] bg-muted/35 border border-border/40 p-2.5 rounded-lg text-muted-foreground">
                        <span className="font-bold text-foreground uppercase tracking-widest block mb-1">Point Payloads:</span>
                        <pre className="p-0 border-0 bg-transparent text-inherit block text-[9px] leading-tight overflow-x-auto">
                          {JSON.stringify(chunk.chunk_metadata, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
