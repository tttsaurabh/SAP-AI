"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getAuthToken, getUserRole, DocumentInfo, ChunkInfo } from "@/lib/api";
import { 
  FileText, ArrowLeft, Upload, Trash2, Search, Database, Layers,
  Activity, BarChart3, AlertCircle, ThumbsUp, ThumbsDown, Eye, X, BookOpen
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
  
  // Chunk inspector states
  const [selectedDocForInspection, setSelectedDocForInspection] = useState<DocumentInfo | null>(null);
  const [docChunks, setDocChunks] = useState<ChunkInfo[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  useEffect(() => {
    const token = getAuthToken();
    const role = getUserRole();
    const adminRoles = ["Super Admin", "SAP Knowledge Manager"];
    
    if (!token || !adminRoles.includes(role)) {
      router.push("/chat");
      return;
    }

    loadDocuments();
    loadAnalytics();
  }, [router]);

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

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadError("");
    setUploadLoading(true);

    try {
      await api.uploadDocument(uploadFile, uploadCollection);
      setUploadFile(null);
      // Reset input element
      const fileInput = document.getElementById("file-upload") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
      
      // Refresh items
      loadDocuments();
      loadAnalytics();
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload document");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleDeleteDoc = async (id: number) => {
    if (!confirm("Are you sure you want to delete this document? This will remove all associated chunks and vector embeddings.")) return;
    try {
      await api.deleteDocument(id);
      setDocuments(documents.filter(d => d.id !== id));
      loadAnalytics();
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

  const filteredDocs = documents.filter(d => 
    d.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.collection_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-screen w-screen bg-[#05070e] text-[#f1f5f9] overflow-hidden">
      {/* Admin Content Workspace */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Glow Effects */}
        <div className="absolute top-[10%] left-[10%] h-[300px] w-[300px] rounded-full bg-purple-600/5 blur-[90px] pointer-events-none" />
        <div className="absolute bottom-[10%] right-[10%] h-[350px] w-[350px] rounded-full bg-blue-600/5 blur-[100px] pointer-events-none" />

        {/* Title Navbar */}
        <div className="flex h-16 items-center justify-between border-b border-slate-800/60 bg-slate-950/20 px-6 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/chat")}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/50 text-slate-400 hover:text-white transition-all"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-purple-400" />
              <h1 className="text-sm font-bold text-white tracking-wider">SAP AI Knowledge Manager</h1>
            </div>
          </div>
        </div>

        {/* Admin Scroll Workspace */}
        <div className="flex-1 overflow-y-auto px-8 py-8 space-y-8 z-10">
          
          {/* Analytics Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-card bg-slate-900/40 p-5 rounded-2xl border border-slate-800/65 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Indexed Documents</p>
                <p className="text-2xl font-extrabold text-white mt-1">{analytics.total_documents}</p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <FileText className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-slate-900/40 p-5 rounded-2xl border border-slate-800/65 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total Chunks</p>
                <p className="text-2xl font-extrabold text-white mt-1">{analytics.total_chunks}</p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                <Layers className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-slate-900/40 p-5 rounded-2xl border border-slate-800/65 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Storage Occupied</p>
                <p className="text-2xl font-extrabold text-white mt-1">{formatBytes(analytics.total_size_bytes)}</p>
              </div>
              <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Activity className="h-5 w-5" />
              </div>
            </div>

            <div className="glass-card bg-slate-900/40 p-5 rounded-2xl border border-slate-800/65 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">User Reviews Rate</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm font-semibold text-emerald-400 flex items-center gap-1">
                    <ThumbsUp className="h-4 w-4" /> {chatAnalytics.positive_feedbacks}
                  </span>
                  <span className="text-sm font-semibold text-red-400 flex items-center gap-1">
                    <ThumbsDown className="h-4 w-4" /> {chatAnalytics.negative_feedbacks}
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
            <div className="glass-panel bg-slate-900/50 p-6 rounded-2xl border-slate-800">
              <div className="flex items-center gap-2 mb-4">
                <Upload className="h-5 w-5 text-purple-400 animate-bounce" />
                <h2 className="text-base font-bold text-white">Ingest New SAP Knowledge</h2>
              </div>
              
              {uploadError && (
                <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-xs text-red-400">
                  <AlertCircle className="h-5 w-5 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <form onSubmit={handleUploadSubmit} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-400">File Attachment (PDF, DOCX, CSV, spreadsheets)</label>
                  <div className="flex items-center justify-center w-full">
                    <label className="flex flex-col items-center justify-center w-full h-36 border-2 border-slate-800 border-dashed rounded-xl cursor-pointer bg-slate-950/40 hover:bg-slate-900/60 hover:border-purple-500/40 transition-all">
                      <div className="flex flex-col items-center justify-center pt-5 pb-6">
                        <Upload className="w-8 h-8 mb-2 text-slate-500" />
                        <p className="text-xs text-slate-400"><span className="font-semibold text-purple-400">Click to upload</span> or drag and drop</p>
                        <p className="text-[10px] text-slate-500 mt-1">{uploadFile ? uploadFile.name : "Supported up to 50MB"}</p>
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
                  <label className="text-xs font-semibold text-slate-400">Collection Grouping (e.g. Master Data, ABAP)</label>
                  <input
                    type="text"
                    value={uploadCollection}
                    onChange={(e) => setUploadCollection(e.target.value)}
                    placeholder="e.g. Master Data"
                    className="block w-full rounded-xl bg-slate-950 border border-slate-800/80 py-3 px-4 text-xs text-white placeholder-slate-500 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={uploadLoading || !uploadFile}
                  className="w-full rounded-xl bg-purple-600 hover:bg-purple-500 py-3 text-xs font-bold text-white shadow-md transition-all disabled:opacity-40"
                >
                  {uploadLoading ? (
                    <div className="flex items-center justify-center gap-2">
                      <div className="h-4.5 w-4.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Parsing & Indexing vectors...</span>
                    </div>
                  ) : "Index Document"}
                </button>
              </form>
            </div>

            {/* Ingestion Table Panel */}
            <div className="glass-panel bg-slate-900/50 p-6 rounded-2xl border-slate-800 lg:col-span-2 flex flex-col overflow-hidden h-[420px]">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-blue-400" />
                  <h2 className="text-base font-bold text-white">Ingestion Registry</h2>
                </div>
                
                {/* Search document */}
                <div className="relative w-48">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                    <Search className="h-3.5 w-3.5 text-slate-500" />
                  </span>
                  <input
                    type="text"
                    placeholder="Search docs..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-lg bg-slate-950 border border-slate-800/60 py-1.5 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              {/* Document rows */}
              <div className="flex-1 overflow-y-auto pr-1">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 uppercase tracking-widest font-bold">
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
                        <td colSpan={5} className="py-8 text-center text-slate-500 font-medium italic">
                          No indexing documents found.
                        </td>
                      </tr>
                    ) : (
                      filteredDocs.map((doc) => (
                        <tr key={doc.id} className="border-b border-slate-800/40 hover:bg-slate-900/25">
                          <td className="py-3 font-semibold text-slate-200 max-w-xs truncate">{doc.filename}</td>
                          <td className="py-3 text-slate-400">{doc.collection_name}</td>
                          <td className="py-3 text-slate-500">{formatBytes(doc.file_size)}</td>
                          <td className="py-3">
                            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                              doc.status === "active" ? "bg-emerald-500/10 text-emerald-400" :
                              doc.status === "failed" ? "bg-red-500/10 text-red-400" :
                              "bg-amber-500/10 text-amber-400 animate-pulse"
                            }`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${
                                doc.status === "active" ? "bg-emerald-500" :
                                doc.status === "failed" ? "bg-red-500" :
                                "bg-amber-500 animate-ping"
                              }`} />
                              {doc.status}
                            </span>
                          </td>
                          <td className="py-3 text-right space-x-2">
                            <button
                              onClick={() => handleInspectChunks(doc)}
                              className="text-slate-400 hover:text-blue-400 transition-all p-1"
                              title="Inspect document segments/chunks"
                            >
                              <Eye className="h-4 w-4 inline" />
                            </button>
                            <button
                              onClick={() => handleDeleteDoc(doc.id)}
                              className="text-slate-400 hover:text-red-400 transition-all p-1"
                              title="Remove document and embeddings"
                            >
                              <Trash2 className="h-4 w-4 inline" />
                            </button>
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
          <div className="absolute inset-0 bg-slate-950/65 backdrop-blur-sm z-50 flex justify-end">
            <div className="w-full max-w-2xl h-full bg-slate-900 border-l border-slate-800 p-6 flex flex-col shadow-2xl relative animate-slide-in">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
                <div className="flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-purple-400" />
                  <div className="min-w-0">
                    <h3 className="font-bold text-white text-sm">Chunk Segment Inspector</h3>
                    <p className="text-[10px] text-slate-500 truncate">{selectedDocForInspection.filename}</p>
                  </div>
                </div>
                <button 
                  onClick={() => setSelectedDocForInspection(null)}
                  className="text-slate-400 hover:text-white transition-all"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Chunk list scroll */}
              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {chunksLoading ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-500 border-t-transparent" />
                    <p className="text-xs text-slate-500">Loading chunk payloads...</p>
                  </div>
                ) : docChunks.length === 0 ? (
                  <p className="text-center text-xs text-slate-500 italic py-12">No chunks found for this file.</p>
                ) : (
                  docChunks.map((chunk, idx) => (
                    <div key={chunk.id} className="rounded-xl border border-slate-800/80 bg-slate-950/45 p-4 space-y-3 hover:border-slate-800 transition-all">
                      <div className="flex items-center justify-between border-b border-slate-800/50 pb-2 text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                        <span>Chunk #{idx + 1} (Index: {chunk.chunk_index})</span>
                        <span className="text-purple-400">Page: {chunk.page_number || 1} | Section: {chunk.section_header || "N/A"}</span>
                      </div>
                      
                      <div className="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap bg-slate-950 p-3 rounded-lg border border-slate-900/60">
                        {chunk.text}
                      </div>

                      {/* Display embedding metadata JSON */}
                      <div className="text-[10px] bg-slate-900/35 border border-slate-800/40 p-2.5 rounded-lg text-slate-500">
                        <span className="font-bold text-slate-400 uppercase tracking-widest block mb-1">Point Payloads:</span>
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
