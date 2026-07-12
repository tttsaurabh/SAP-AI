"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, getAuthToken, getUserRole, getUserEmail, clearAuthToken, Message, Conversation, Citation } from "@/lib/api";
import { 
  MessageSquare, Plus, LogOut, Send, Bot, User as UserIcon, BookOpen,
  Settings, ThumbsUp, ThumbsDown, Copy, Download, Moon, Sun,
  ChevronRight, RefreshCw, X, FileText, Check, Terminal, Database, ArrowDown, Search, Layers
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
  const [sidebarSearch, setSidebarSearch] = useState("");
  
  // Feedback states
  const [feedbackMsgId, setFeedbackMsgId] = useState<number | null>(null);
  const [feedbackScore, setFeedbackScore] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  
  // Active citation states
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // FAB Scroll-to-bottom visibility
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Suggested prompt chips with icons for high-end look
  const suggestions = [
    { text: "Explain MDG Change Request process.", desc: "Governance Workflow" },
    { text: "What are the RAP components in ABAP?", desc: "Modern Programming Model" },
    { text: "Explain Business Partner conversion in S/4HANA.", desc: "Data Migration" },
    { text: "How is a BADI defined in SAP?", desc: "Extensibility Options" }
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

  // Monitor scrolling to toggle Scroll-to-Bottom FAB
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    // Show button if user is scrolled up by more than 400px
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight > 400);
  };

  const loadConversations = async () => {
    try {
      const data = await api.getConversations();
      setConversations(data);
      if (data.length > 0 && !activeConv) {
        loadConversationDetails(data[0].id);
      }
    } catch (err) {
      console.error("Failed to load conversations", err);
    }
  };

  const loadCollections = async () => {
    try {
      const roles = ["Super Admin", "SAP Knowledge Manager", "SAP Consultant"];
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
      console.error("Failed to delete conversation", err);
    }
  };

  const handleSend = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const queryText = customQuery || query;
    if (!queryText.trim() || loading) return;

    if (!activeConv) {
      try {
        const data = await api.createConversation(queryText.slice(0, 30) + "...");
        setConversations([data, ...conversations]);
        setActiveConv({ ...data, messages: [] });
        executeStream(data.id, queryText);
      } catch (err) {
        console.error("Failed to auto-create conversation", err);
      }
    } else {
      executeStream(activeConv.id, queryText);
    }
    setQuery("");
  };

  const executeStream = (convId: number, queryText: string) => {
    setLoading(true);
    
    // Add user message immediately
    const userMsg: Message = {
      id: Date.now(),
      conversation_id: convId,
      role: "user",
      content: queryText,
      citations: [],
      created_at: new Date().toISOString()
    };
    
    setActiveConv(prev => {
      if (!prev) return null;
      return {
        ...prev,
        messages: [...(prev.messages || []), userMsg]
      };
    });

    // Setup temporary assistant message for stream update
    const assistantMsgId = Date.now() + 1;
    const tempAssistantMsg: Message = {
      id: assistantMsgId,
      conversation_id: convId,
      role: "assistant",
      content: "",
      citations: [],
      created_at: new Date().toISOString()
    };

    setActiveConv(prev => {
      if (!prev) return null;
      return {
        ...prev,
        messages: [...(prev.messages || []), tempAssistantMsg]
      };
    });

    let currentContent = "";
    api.streamResponse(
      convId,
      queryText,
      selectedCollection,
      // onMessageChunk
      (chunk) => {
        currentContent += chunk;
        setActiveConv(prev => {
          if (!prev) return null;
          return {
            ...prev,
            messages: (prev.messages || []).map(m => 
              m.id === assistantMsgId ? { ...m, content: currentContent } : m
            )
          };
        });
      },
      // onCitations
      ({ citations }) => {
        setActiveConv(prev => {
          if (!prev) return null;
          return {
            ...prev,
            messages: (prev.messages || []).map(m => 
              m.id === assistantMsgId ? { ...m, citations } : m
            )
          };
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

  const submitFeedback = async () => {
    if (!feedbackMsgId) return;
    try {
      await api.submitFeedback({
        message_id: feedbackMsgId,
        score: feedbackScore,
        comments: feedbackComment
      });
      setFeedbackMsgId(null);
      setFeedbackComment("");
    } catch (err) {
      console.error("Feedback error", err);
    }
  };

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

  const isAdminOrManager = ["Super Admin", "SAP Knowledge Manager", "SAP Consultant"].includes(userRole);
  
  // Filter sidebar chats based on search query
  const filteredConversations = conversations.filter(c => 
    c.title.toLowerCase().includes(sidebarSearch.toLowerCase())
  );

  return (
    <div className="flex h-screen w-screen bg-[#05070e] text-[#f1f5f9] overflow-hidden font-sans">
      
      {/* Sidebar Panel */}
      <div className="flex h-full w-80 flex-col border-r border-slate-900 bg-slate-950/75 backdrop-blur-xl">
        
        {/* User profile info header */}
        <div className="flex items-center gap-3 border-b border-slate-900/60 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 shadow-md shadow-indigo-500/10 border border-indigo-400/20">
            <Layers className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate text-white">{userEmail || "Consultant"}</p>
            <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-wide">{userRole}</p>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <button
                onClick={() => router.push("/workbench")}
                title="SAP Agentic Workbench (simulation/demo mode — not connected to a real SAP system)"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/40 text-slate-400 hover:text-indigo-400 hover:border-indigo-500/35 transition-all"
                aria-label="Open SAP Agentic Workbench (simulation/demo mode)"
              >
                <Terminal className="h-4 w-4" />
              </button>
              <span className="pointer-events-none absolute -top-1.5 -right-1.5 rounded-full bg-amber-500 px-1 text-[7px] font-bold leading-tight text-slate-950">
                DEMO
              </span>
            </div>
            {isAdminOrManager && (
              <button
                onClick={() => router.push("/admin")}
                title="Knowledge Base Admin Panel"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/40 text-slate-400 hover:text-indigo-400 hover:border-indigo-500/35 transition-all"
                aria-label="Open knowledge base admin panel"
              >
                <Settings className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Collection filter dropdown for Admin/Consultant */}
        {isAdminOrManager && (
          <div className="p-4 border-b border-slate-900/50 bg-slate-950/20">
            <label className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block mb-1.5">Active Knowledge Domain</label>
            <div className="relative">
              <select
                value={selectedCollection}
                onChange={(e) => setSelectedCollection(e.target.value)}
                className="w-full text-xs font-semibold rounded-lg bg-slate-900/70 border border-slate-800 text-slate-200 py-2.5 pl-3 pr-8 focus:outline-none focus:ring-1 focus:ring-indigo-500 appearance-none cursor-pointer"
              >
                {collections.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-500">
                <ChevronRight className="h-3 w-3 rotate-90" />
              </div>
            </div>
          </div>
        )}

        {/* New Chat Button */}
        <div className="p-4 pb-2">
          <button
            onClick={handleCreateChat}
            className="premium-glow-button flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-600/10 transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>New Consultation</span>
          </button>
        </div>

        {/* Search bar inside Sidebar */}
        <div className="px-4 py-2">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search conversation..."
              value={sidebarSearch}
              onChange={(e) => setSidebarSearch(e.target.value)}
              className="w-full rounded-lg bg-slate-950 border border-slate-800 py-2 pl-9 pr-3 text-xs text-white placeholder-slate-550 focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Chat History List */}
        <div className="flex-1 overflow-y-auto px-3 py-1 space-y-1">
          {filteredConversations.map((c) => {
            const isActive = activeConv?.id === c.id;
            return (
              <div
                key={c.id}
                onClick={() => loadConversationDetails(c.id)}
                className={`group flex items-center justify-between rounded-xl px-3.5 py-3 text-xs font-semibold cursor-pointer transition-all border ${
                  isActive 
                    ? "bg-indigo-600/15 border-indigo-500/25 text-white" 
                    : "border-transparent text-slate-400 hover:bg-slate-900/40 hover:text-white"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-indigo-400" : "text-slate-500"}`} />
                  <span className="truncate">{c.title}</span>
                </div>
                <button
                  onClick={(e) => handleDeleteChat(c.id, e)}
                  className="opacity-0 group-hover:opacity-100 hover:text-red-400 p-0.5 transition-all"
                  title="Delete chat session"
                  aria-label={`Delete conversation "${c.title}"`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Logout bottom */}
        <div className="border-t border-slate-900 bg-slate-950/20 p-4">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3.5 py-3 text-xs font-bold text-slate-400 hover:bg-red-500/10 hover:text-red-400 transition-all"
          >
            <LogOut className="h-4.5 w-4.5" />
            <span>Sign Out Session</span>
          </button>
        </div>
      </div>

      {/* Main Workspace Panel */}
      <div className="flex flex-1 flex-col h-full overflow-hidden bg-[#05070e] relative">
        {/* Animated drifting gradient backgrounds */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
          <div className="absolute top-[10%] right-[10%] h-[400px] w-[400px] rounded-full bg-purple-600/5 blur-[120px] animate-drift-one" />
          <div className="absolute bottom-[10%] left-[10%] h-[450px] w-[450px] rounded-full bg-blue-600/5 blur-[120px] animate-drift-two" />
        </div>

        {/* Chat Title bar */}
        <div className="flex h-16 items-center justify-between border-b border-slate-900 bg-slate-950/20 px-6 backdrop-blur-md z-10">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <h1 className="text-xs font-extrabold text-white tracking-wider uppercase">
              {activeConv ? activeConv.title : "SAP RAG Assistant"}
            </h1>
            {selectedCollection !== "Default" && (
              <span className="ml-2 px-2 py-0.5 text-[9px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full">
                {selectedCollection}
              </span>
            )}
          </div>
          {activeConv && activeConv.messages && activeConv.messages.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={exportChatMarkdown}
                title="Export session to Markdown"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/40 text-slate-400 hover:text-indigo-400 transition-all"
                aria-label="Export chat session to Markdown"
              >
                <Download className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {/* Messaging Container */}
        <div 
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-6 py-8 space-y-6 z-10"
        >
          {!activeConv || activeConv.messages?.length === 0 ? (
            /* Welcome / Suggestions Workspace (Empty State) */
            <div className="flex flex-col items-center justify-center h-full text-center max-w-2xl mx-auto space-y-8 animate-fade-in">
              <div className="space-y-3.5">
                {/* Logo wrapper */}
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600/20 to-indigo-500/20 border border-indigo-500/20 shadow-lg shadow-indigo-500/5">
                  <Bot className="h-8 w-8 text-indigo-400 animate-pulse" />
                </div>
                <h2 className="text-2xl font-black tracking-tight text-white">SAP Knowledge Copilot</h2>
                <p className="text-xs text-slate-400 leading-relaxed max-w-md mx-auto">
                  Ask technical, functional, or system configurations questions. The engine uses semantic retrieval to formulate precise, citation-backed answers.
                </p>
              </div>

              <div className="w-full space-y-4">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest text-left">Suggested SAP Inquiries</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(undefined, s.text)}
                      className="group text-left border border-slate-800 bg-slate-950/40 hover:bg-slate-900/50 hover:border-indigo-500/35 p-4 rounded-xl text-slate-300 transition-all hover:-translate-y-0.5"
                    >
                      <p className="text-xs font-bold text-white group-hover:text-indigo-400 transition-colors">{s.text}</p>
                      <p className="text-[10px] text-slate-500 mt-1 font-semibold">{s.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            /* Message list */
            <div className="max-w-3xl mx-auto space-y-6">
              {activeConv.messages?.map((m, idx) => {
                const isAssistant = m.role === "assistant";
                return (
                  <div 
                    key={idx} 
                    className={`flex gap-4 ${isAssistant ? "justify-start" : "justify-end"}`}
                  >
                    {/* Bot Avatar Icon */}
                    {isAssistant && (
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border bg-gradient-to-tr from-blue-900/20 to-indigo-900/20 border-indigo-500/30 text-indigo-400 shadow-md">
                        <Bot className="h-5 w-5" />
                      </div>
                    )}

                    {/* Message Bubble wrapper */}
                    <div className={`flex-1 space-y-1.5 max-w-[85%] ${!isAssistant && "text-right"}`}>
                      <div className="flex items-center justify-between px-1">
                        <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500">
                          {isAssistant ? "SAP AI Agent" : "Consultant"}
                        </span>
                        
                        {/* Copy Code action */}
                        {isAssistant && m.content && (
                          <div className="flex items-center gap-1.5 opacity-50 hover:opacity-100 transition-all">
                            <button
                              onClick={() => copyToClipboard(m.content, m.id)}
                              className="text-slate-400 hover:text-indigo-400 p-0.5"
                              title="Copy markdown text"
                              aria-label="Copy message text"
                            >
                              {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Content text - distinct styling for user/bot */}
                      <div className={`text-sm leading-relaxed p-4 rounded-2xl border ${
                        isAssistant 
                          ? "bg-slate-900/30 border-slate-800 text-slate-200" 
                          : "bg-gradient-to-r from-blue-700/25 to-indigo-700/20 border-indigo-500/20 text-white rounded-tr-none ml-auto max-w-fit text-left shadow-lg shadow-indigo-650/5"
                      }`}>
                        {loading && isAssistant && !m.content ? (
                          <div className="flex items-center gap-1.5 py-1.5">
                            <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500" />
                            <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:0.2s]" />
                            <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:0.4s]" />
                          </div>
                        ) : (
                          <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                            {m.content}
                          </ReactMarkdown>
                        )}
                      </div>

                      {/* Timestamp/Sub-text */}
                      <div className="px-1 flex justify-between items-center text-[9px] text-slate-600 font-semibold mt-1">
                        <span>{m.created_at ? new Date(m.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ""}</span>
                      </div>

                      {/* Source Citation Badges */}
                      {isAssistant && m.citations && m.citations.length > 0 && (
                        <div className="space-y-1.5 pt-2">
                          <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Document Citations</p>
                          <div className="flex flex-wrap gap-2">
                            {m.citations.map((c, cIdx) => (
                              <button
                                key={cIdx}
                                onClick={() => setSelectedCitation(c)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/50 hover:bg-indigo-600/10 hover:border-indigo-500/30 px-3 py-1.5 text-xs text-slate-400 hover:text-indigo-300 font-medium transition-all"
                              >
                                <FileText className="h-3 w-3 text-indigo-400" />
                                <span>{c.doc_name.slice(0, 20)}... (P. {c.page || "1"})</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Feedback buttons */}
                      {isAssistant && m.content && (
                        <div className="flex justify-start gap-2 pt-2 border-t border-slate-900/60 mt-2">
                          <button
                            onClick={() => {
                              setFeedbackMsgId(m.id);
                              setFeedbackScore(1);
                            }}
                            className="rounded-lg hover:bg-slate-900 hover:text-emerald-400 text-slate-500 p-1.5 transition-all"
                            title="Helpful response"
                            aria-label="Mark response as helpful"
                          >
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              setFeedbackMsgId(m.id);
                              setFeedbackScore(-1);
                            }}
                            className="rounded-lg hover:bg-slate-900 hover:text-red-400 text-slate-500 p-1.5 transition-all"
                            title="Unhelpful / hallucinated response"
                            aria-label="Mark response as unhelpful"
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

        {/* Scroll-to-bottom Floating Action Button */}
        {showScrollBottom && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-24 right-8 z-30 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition-all animate-bounce"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-5 w-5" />
          </button>
        )}

        {/* Input Bar Panel */}
        <div className="border-t border-slate-900 bg-slate-950/20 px-6 py-4.5 z-10 backdrop-blur-md">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSend} className="relative flex items-center">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask a technical or functional SAP question..."
                className="w-full rounded-2xl bg-slate-900/60 border border-slate-800/80 py-4 pl-5 pr-14 text-sm text-white placeholder-slate-500 transition-all focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="absolute right-3.5 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-600/10 hover:opacity-95 active:scale-95 disabled:opacity-30 disabled:scale-100 transition-all"
                aria-label="Send message"
              >
                <Send className="h-4.5 w-4.5" />
              </button>
            </form>
            <div className="mt-2.5 text-center">
              <span className="text-[10px] font-semibold text-slate-600 tracking-wider">
                This platform is strictly grounded. Responses are formulated solely from loaded knowledge sources.
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
                  <FileText className="h-5 w-5 text-indigo-400" />
                  <h3 className="font-bold text-white">Source Verification</h3>
                </div>
                <button
                  onClick={() => setSelectedCitation(null)}
                  className="text-slate-400 hover:text-white transition-all"
                  aria-label="Close citation drawer"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-sm text-slate-300">
                <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-2">
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Document Name</p>
                  <p className="font-semibold text-white">{selectedCitation.doc_name}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-1">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Page Offset</p>
                    <p className="font-semibold text-white">{selectedCitation.page || "N/A"}</p>
                  </div>
                  <div className="rounded-xl bg-slate-950 p-4 border border-slate-800 space-y-1">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Section Chapter</p>
                    <p className="font-semibold text-white">{selectedCitation.section || "N/A"}</p>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-950/40 border border-slate-800/80 p-4 space-y-2.5">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <Terminal className="h-4.5 w-4.5 text-indigo-400" />
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
                  aria-label="Close feedback dialog"
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
                  className="w-full rounded-xl bg-slate-950 border border-slate-800 p-3 text-sm text-white placeholder-slate-550 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
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
                  className="rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-indigo-550 transition-all"
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
