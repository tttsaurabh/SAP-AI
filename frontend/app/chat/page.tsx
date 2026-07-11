"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, getAuthToken, getUserRole, getUserEmail, clearAuthToken, Message, Conversation, Citation } from "@/lib/api";
import { 
  MessageSquare, Plus, LogOut, Send, Bot, User as UserIcon, BookOpen, 
  Settings, ThumbsUp, ThumbsDown, Copy, Download, Moon, Sun, 
  ChevronRight, RefreshCw, X, FileText, Check, Terminal, Database
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";

export default function ChatPage() {
  const router = useRouter();
  
  // States
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConv, setActiveConv] = useState<Conversation | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [collections, setCollections] = useState<string[]>(["Default"]);
  const [selectedCollection, setSelectedCollection] = useState("Default");
  const [userEmail, setUserEmail] = useState("");
  const [userRole, setUserRole] = useState("End User");
  
  // Feedback states
  const [feedbackMsgId, setFeedbackMsgId] = useState<number | null>(null);
  const [feedbackScore, setFeedbackScore] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  
  // Active citation states
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Suggested prompt chips
  const suggestions = [
    "Explain MDG Change Request process.",
    "What are the RAP components in ABAP?",
    "Explain Business Partner conversion in S/4HANA.",
    "How is a BADI defined in SAP?"
  ];

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push("/auth");
      return;
    }
    setUserEmail(getUserEmail());
    setUserRole(getUserRole());
    
    loadConversations();
    loadCollections();
  }, [router]);

  useEffect(() => {
    scrollToBottom();
  }, [activeConv?.messages, loading]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const loadConversations = async () => {
    try {
      const data = await api.getConversations();
      setConversations(data);
      if (data.length > 0 && !activeConv) {
        // Load the most recent conversation by default
        loadConversationDetails(data[0].id);
      }
    } catch (err) {
      console.error("Failed to load conversations", err);
    }
  };

  const loadCollections = async () => {
    try {
      const roles = ["Super Admin", "SAP Knowledge Manager"];
      if (roles.includes(getUserRole())) {
        const data = await api.listCollections();
        setCollections(data);
      }
    } catch (err) {
      console.error("Failed to load collections", err);
    }
  };

  const loadConversationDetails = async (id: number) => {
    try {
      const data = await api.getConversationDetails(id);
      setActiveConv(data);
    } catch (err) {
      console.error("Failed to load conversation details", err);
    }
  };

  const handleCreateChat = async () => {
    try {
      const data = await api.createConversation("New Conversation");
      setConversations([data, ...conversations]);
      setActiveConv({ ...data, messages: [] });
    } catch (err) {
      console.error("Failed to create chat", err);
    }
  };

  const handleDeleteChat = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      const remaining = conversations.filter(c => c.id !== id);
      setConversations(remaining);
      if (activeConv?.id === id) {
        if (remaining.length > 0) {
          loadConversationDetails(remaining[0].id);
        } else {
          setActiveConv(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete chat", err);
    }
  };

  const handleSend = async (e?: React.FormEvent, promptText?: string) => {
    if (e) e.preventDefault();
    const messageText = promptText || query;
    if (!messageText.trim() || loading) return;

    let currentConv = activeConv;
    if (!currentConv) {
      try {
        currentConv = await api.createConversation("New Conversation");
        setConversations([currentConv, ...conversations]);
        setActiveConv({ ...currentConv, messages: [] });
      } catch (err) {
        console.error("Failed to auto-create conversation", err);
        return;
      }
    }

    const conversationId = currentConv.id;
    setQuery("");
    setLoading(true);

    // Optimistically push user message to UI
    const updatedMessages = [...(currentConv.messages || [])];
    const dummyUserMsg: Message = {
      id: Date.now(),
      conversation_id: conversationId,
      role: "user",
      content: messageText,
      citations: [],
      created_at: new Date().toISOString()
    };
    updatedMessages.push(dummyUserMsg);
    
    // Add temporary loading message for assistant
    const dummyAssistantMsg: Message = {
      id: Date.now() + 1,
      conversation_id: conversationId,
      role: "assistant",
      content: "",
      citations: [],
      created_at: new Date().toISOString()
    };
    updatedMessages.push(dummyAssistantMsg);
    
    setActiveConv({ ...currentConv, messages: updatedMessages });

    // Begin SSE response stream
    let contentAccumulator = "";
    await api.streamResponse(
      conversationId,
      messageText,
      selectedCollection,
      // onContent chunk update
      (chunk) => {
        contentAccumulator += chunk;
        setActiveConv(prev => {
          if (!prev) return null;
          const msgs = [...prev.messages!];
          msgs[msgs.length - 1].content = contentAccumulator;
          return { ...prev, messages: msgs };
        });
      },
      // onCitations complete update
      (data) => {
        setActiveConv(prev => {
          if (!prev) return null;
          const msgs = [...prev.messages!];
          msgs[msgs.length - 1].id = data.message_id; // Set actual db id
          msgs[msgs.length - 1].citations = data.citations;
          return { ...prev, messages: msgs };
        });
      },
      // onError
      (err) => {
        console.error("Streaming error", err);
        setLoading(false);
      },
      // onDone
      () => {
        setLoading(false);
        loadConversations(); // refresh title list
      }
    );
  };

  const handleLogout = () => {
    clearAuthToken();
    router.push("/auth");
  };

  // Feedback actions
  const submitFeedback = async () => {
    if (!feedbackMsgId) return;
    try {
      await api.submitFeedback({
        message_id: feedbackMsgId,
        score: feedbackScore,
        comments: feedbackComment
      });
      // Close and clear
      setFeedbackMsgId(null);
      setFeedbackComment("");
    } catch (err) {
      console.error("Feedback error", err);
    }
  };

  // Export functions
  const copyToClipboard = (text: string, id: number) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const exportChatMarkdown = () => {
    if (!activeConv?.messages) return;
    let markdown = `# Chat Session: ${activeConv.title}\n\n`;
    activeConv.messages.forEach(m => {
      markdown += `### ${m.role === "user" ? "User" : "SAP Assistant"}\n${m.content}\n\n`;
      if (m.citations.length > 0) {
        markdown += `*Sources cited:*\n`;
        m.citations.forEach((c, idx) => {
          markdown += `- [${idx+1}] ${c.doc_name} (Page ${c.page || 'N/A'}, Section ${c.section || 'N/A'})\n`;
        });
        markdown += `\n`;
      }
    });

    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sap-chat-${activeConv.id}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const isAdminOrManager = ["Super Admin", "SAP Knowledge Manager"].includes(userRole);

  return (
    <div className="flex h-screen w-screen bg-[#05070e] text-[#f1f5f9] overflow-hidden">
      {/* Sidebar Panel */}
      <div className="flex h-full w-80 flex-col border-r border-slate-800/80 bg-slate-950/75 backdrop-blur-xl">
        {/* User profile info header */}
        <div className="flex items-center gap-3 border-b border-slate-800/60 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 shadow-md shadow-purple-600/10">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate text-white">{userEmail || "Consultant"}</p>
            <p className="text-xs font-medium text-slate-500">{userRole}</p>
          </div>
          <div className="flex items-center gap-1.5">
            <button 
              onClick={() => router.push("/workbench")}
              title="SAP Agentic Workbench"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/60 text-slate-400 hover:text-purple-400 hover:border-purple-500/35 transition-all"
            >
              <Terminal className="h-4 w-4" />
            </button>
            {isAdminOrManager && (
              <button 
                onClick={() => router.push("/admin")}
                title="Knowledge Base Admin Panel"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/60 text-slate-400 hover:text-purple-400 hover:border-purple-500/35 transition-all"
              >
                <Settings className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Collection filter dropdown for Admin/Consultant */}
        {isAdminOrManager && (
          <div className="p-4 border-b border-slate-800/40">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">Active Knowledge Domain</label>
            <select
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
              className="w-full text-xs font-medium rounded-lg bg-slate-900 border border-slate-800 text-slate-300 py-2.5 px-3 focus:outline-none focus:ring-1 focus:ring-purple-500"
            >
              {collections.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        )}

        {/* New Chat Button */}
        <div className="p-4 pb-2">
          <button
            onClick={handleCreateChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600/90 to-blue-600/95 py-3 text-sm font-semibold text-white shadow-md shadow-purple-600/10 transition-all hover:opacity-95 active:scale-95"
          >
            <Plus className="h-4 w-4" />
            <span>New Consultation</span>
          </button>
        </div>

        {/* Knowledge Base Admin Button for Admin */}
        {isAdminOrManager && (
          <div className="px-4 pb-4">
            <button
              onClick={() => router.push("/admin")}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-purple-500/25 bg-purple-500/5 hover:bg-purple-500/10 py-2.5 text-xs font-semibold text-purple-300 transition-all active:scale-95"
            >
              <Database className="h-4 w-4 text-purple-400" />
              <span>Upload Knowledge Source</span>
            </button>
          </div>
        )}

        {/* Chat History List */}
        <div className="flex-1 overflow-y-auto px-3 space-y-1">
          {conversations.map((c) => {
            const isActive = activeConv?.id === c.id;
            return (
              <div
                key={c.id}
                onClick={() => loadConversationDetails(c.id)}
                className={`group flex items-center justify-between rounded-xl px-3.5 py-3 text-sm font-medium cursor-pointer transition-all ${
                  isActive 
                    ? "bg-purple-600/15 border border-purple-500/20 text-purple-200" 
                    : "text-slate-400 hover:bg-slate-900/60 hover:text-white"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-purple-400" : "text-slate-500"}`} />
                  <span className="truncate">{c.title}</span>
                </div>
                <button
                  onClick={(e) => handleDeleteChat(c.id, e)}
                  className="opacity-0 group-hover:opacity-100 hover:text-red-400 p-0.5 transition-all"
                  title="Delete chat session"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Logout bottom */}
        <div className="border-t border-slate-800/60 p-4">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3.5 py-3 text-sm font-semibold text-slate-400 hover:bg-red-500/10 hover:text-red-400 transition-all"
          >
            <LogOut className="h-4.5 w-4.5" />
            <span>Sign Out Session</span>
          </button>
        </div>
      </div>

      {/* Main Workspace Panel */}
      <div className="flex flex-1 flex-col h-full overflow-hidden bg-[#05070e] relative">
        {/* Workspace background glows */}
        <div className="absolute top-[10%] right-[10%] h-[350px] w-[350px] rounded-full bg-purple-600/5 blur-[100px] pointer-events-none" />
        <div className="absolute bottom-[10%] left-[10%] h-[400px] w-[400px] rounded-full bg-blue-600/5 blur-[110px] pointer-events-none" />

        {/* Chat Title bar */}
        <div className="flex h-16 items-center justify-between border-b border-slate-800/60 bg-slate-950/20 px-6 backdrop-blur-md z-10">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <h1 className="text-sm font-bold text-white tracking-wide">
              {activeConv ? activeConv.title : "SAP RAG Assistant"}
            </h1>
          </div>
          {activeConv && activeConv.messages && activeConv.messages.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={exportChatMarkdown}
                title="Export session to Markdown"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/50 text-slate-400 hover:text-purple-400 transition-all"
              >
                <Download className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {/* Messaging Container */}
        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-6 z-10">
          {!activeConv || activeConv.messages?.length === 0 ? (
            /* Welcome / Suggesions Workspace */
            <div className="flex flex-col items-center justify-center h-full text-center max-w-2xl mx-auto space-y-8">
              <div className="space-y-3">
                <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-purple-600/25 to-blue-500/20 border border-purple-500/20 shadow-md">
                  <Bot className="h-7 w-7 text-purple-400" />
                </div>
                <h2 className="text-2xl font-bold text-white">SAP Knowledge Copilot</h2>
                <p className="text-sm text-slate-400 leading-relaxed max-w-md">
                  This AI platform searches internal functional specifications, configuration guides, and code standards to provide certified answers with source citations.
                </p>
              </div>

              <div className="w-full space-y-3">
                <p className="text-xs font-bold text-slate-500 uppercase tracking-widest text-left">Suggested SAP Inquiries</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(undefined, s)}
                      className="text-left text-xs font-medium border border-slate-800/80 bg-slate-900/35 hover:bg-slate-900 hover:border-purple-500/40 p-4 rounded-xl text-slate-300 transition-all active:scale-98"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Message list */
            <div className="max-w-4xl mx-auto space-y-6">
              {activeConv.messages?.map((m, idx) => {
                const isAssistant = m.role === "assistant";
                return (
                  <div key={idx} className="flex gap-4">
                    {/* Icon */}
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${
                      isAssistant 
                        ? "bg-purple-600/10 border-purple-500/20 text-purple-400" 
                        : "bg-slate-900 border-slate-800 text-slate-400"
                    }`}>
                      {isAssistant ? <Bot className="h-5 w-5" /> : <UserIcon className="h-5 w-5" />}
                    </div>

                    {/* Message Bubble wrapper */}
                    <div className="flex-1 space-y-2 max-w-[85%]">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          {isAssistant ? "SAP Assistant" : "You"}
                        </span>
                        
                        {/* Copy Code action */}
                        {isAssistant && m.content && (
                          <div className="flex items-center gap-1.5 opacity-60 hover:opacity-100 transition-opacity">
                            <button
                              onClick={() => copyToClipboard(m.content, m.id)}
                              className="text-slate-500 hover:text-purple-400 p-1"
                              title="Copy markdown text"
                            >
                              {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Content text */}
                      <div className="text-sm leading-relaxed text-slate-200 bg-slate-900/15 border border-slate-800/10 p-3 rounded-2xl">
                        {loading && isAssistant && !m.content ? (
                          <div className="flex items-center gap-1.5 py-1">
                            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-purple-500" />
                            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-purple-500 [animation-delay:0.2s]" />
                            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-purple-500 [animation-delay:0.4s]" />
                          </div>
                        ) : (
                          <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                            {m.content}
                          </ReactMarkdown>
                        )}
                      </div>

                      {/* Source Citation Badges */}
                      {isAssistant && m.citations && m.citations.length > 0 && (
                        <div className="space-y-1.5 pt-2">
                          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Document Citations</p>
                          <div className="flex flex-wrap gap-2">
                            {m.citations.map((c, cIdx) => (
                              <button
                                key={cIdx}
                                onClick={() => setSelectedCitation(c)}
                                className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-xs font-semibold text-purple-300 hover:border-purple-500/40 hover:bg-slate-950 transition-all"
                              >
                                <FileText className="h-3.5 w-3.5 shrink-0 text-purple-400" />
                                <span>[{cIdx + 1}] {c.doc_name} {c.page ? `(Page ${c.page})` : ""}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Feedback buttons */}
                      {isAssistant && m.content && !loading && (
                        <div className="flex items-center gap-3 pt-2">
                          <button
                            onClick={() => {
                              setFeedbackMsgId(m.id);
                              setFeedbackScore(1);
                            }}
                            className="text-slate-500 hover:text-emerald-400 transition-all p-1"
                            title="Helpful response"
                          >
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              setFeedbackMsgId(m.id);
                              setFeedbackScore(-1);
                            }}
                            className="text-slate-500 hover:text-red-400 transition-all p-1"
                            title="Unhelpful / hallucinated response"
                          >
                            <ThumbsDown className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar Panel */}
        <div className="border-t border-slate-800/60 bg-slate-950/20 px-6 py-4 z-10 backdrop-blur-md">
          <div className="max-w-4xl mx-auto">
            <form onSubmit={handleSend} className="relative flex items-center">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask a technical or functional SAP question..."
                className="w-full rounded-2xl bg-slate-900/75 border border-slate-800/80 py-4 pl-5 pr-14 text-sm text-white placeholder-slate-500 transition-all focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
              />
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="absolute right-3.5 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 text-white shadow-md shadow-purple-600/10 hover:opacity-95 active:scale-95 disabled:opacity-30 disabled:scale-100 transition-all"
              >
                <Send className="h-4.5 w-4.5" />
              </button>
            </form>
            <div className="mt-2 text-center">
              <span className="text-[10px] text-slate-500 tracking-wider">
                Platform conforms to Grounded boundaries. Responses are generated solely from loaded files.
              </span>
            </div>
          </div>
        </div>

        {/* --- Citation Side Drawer/Overlay --- */}
        {selectedCitation && (
          <div className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm z-50 flex justify-end">
            <div className="w-full max-w-md h-full bg-slate-900 border-l border-slate-800 p-6 flex flex-col shadow-2xl relative animate-slide-in">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-purple-400" />
                  <h3 className="font-bold text-white">Source Verification</h3>
                </div>
                <button 
                  onClick={() => setSelectedCitation(null)}
                  className="text-slate-400 hover:text-white transition-all"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-sm text-slate-300">
                <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-2">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Document Name</p>
                  <p className="font-semibold text-white">{selectedCitation.doc_name}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-1">
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Page Offset</p>
                    <p className="font-semibold text-white">{selectedCitation.page || "N/A"}</p>
                  </div>
                  <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-1">
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Section Chapter</p>
                    <p className="font-semibold text-white">{selectedCitation.section || "N/A"}</p>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-950/40 border border-slate-800/80 p-4 space-y-2.5">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <Terminal className="h-4.5 w-4.5 text-purple-400" />
                    <span>CITED SEGMENT TEXT</span>
                  </div>
                  {selectedCitation.text ? (
                    <p className="italic text-slate-300 leading-relaxed font-mono text-xs">
                      "{selectedCitation.text}"
                    </p>
                  ) : (
                    <p className="italic text-slate-500 leading-relaxed font-mono text-xs">
                      Source text unavailable for this citation.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- Feedback Dialog Modal --- */}
        {feedbackMsgId !== null && (
          <div className="absolute inset-0 bg-slate-950/65 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-4 shadow-2xl">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-white">Provide RAG Response Feedback</h3>
                <button 
                  onClick={() => setFeedbackMsgId(null)}
                  className="text-slate-400 hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  {feedbackScore === 1 
                    ? "Great! What made this response helpful? (e.g. correct ABAP code, precise citation, accurate SAP steps)" 
                    : "Oh no! Please help us correct the RAG. What went wrong? (e.g. incorrect transaction code, hallucinated setup, bad citation)"
                  }
                </p>
                <textarea
                  value={feedbackComment}
                  onChange={(e) => setFeedbackComment(e.target.value)}
                  placeholder="Enter your observations..."
                  rows={4}
                  className="w-full rounded-xl bg-slate-950 border border-slate-800 p-3 text-sm text-white placeholder-slate-500 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setFeedbackMsgId(null)}
                  className="rounded-xl border border-slate-800 px-4 py-2.5 text-xs font-semibold text-slate-400 hover:bg-slate-900 transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={submitFeedback}
                  className="rounded-xl bg-purple-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-purple-500 transition-all"
                >
                  Submit Review
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
