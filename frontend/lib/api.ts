const API_URL = "http://localhost:8000/api";

export interface Citation {
  doc_name: string;
  page?: number;
  section?: string;
  url?: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export interface User {
  id: number;
  email: string;
  full_name?: string;
  role: string;
}

export interface DocumentInfo {
  id: number;
  filename: string;
  file_path: string;
  file_size: number;
  collection_name: string;
  document_type?: string;
  status: string;
  total_chunks: number;
  created_at: string;
}

export interface ChunkInfo {
  id: number;
  document_id: number;
  text: string;
  chunk_index: number;
  page_number?: number;
  section_header?: string;
  chunk_metadata: Record<string, any>;
}

// Token management helpers
export const getAuthToken = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("sap_token");
  }
  return null;
};

export const setAuthToken = (token: string, role: string, email: string) => {
  if (typeof window !== "undefined") {
    localStorage.setItem("sap_token", token);
    localStorage.setItem("sap_role", role);
    localStorage.setItem("sap_email", email);
  }
};

export const clearAuthToken = () => {
  if (typeof window !== "undefined") {
    localStorage.removeItem("sap_token");
    localStorage.removeItem("sap_role");
    localStorage.removeItem("sap_email");
  }
};

export const getUserRole = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("sap_role") || "Guest";
  }
  return "Guest";
};

export const getUserEmail = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("sap_email") || "";
  }
  return "";
};

// Generic fetch client with headers injected automatically
const fetchClient = async (path: string, options: RequestInit = {}) => {
  const token = getAuthToken();
  const headers = {
    ...options.headers,
  } as Record<string, string>;

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAuthToken();
    if (typeof window !== "undefined" && window.location.pathname !== "/auth") {
      window.location.href = "/auth";
    }
  }

  if (!response.ok) {
    const errText = await response.text();
    let errMsg = "An error occurred";
    try {
      const parsed = JSON.parse(errText);
      errMsg = parsed.detail || errMsg;
    } catch {
      errMsg = errText || errMsg;
    }
    throw new Error(errMsg);
  }

  return response;
};

export const api = {
  // Auth
  login: async (formData: URLSearchParams): Promise<any> => {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Login failed");
    }
    return response.json();
  },

  register: async (userData: any): Promise<User> => {
    const response = await fetch(`${API_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userData),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Registration failed");
    }
    return response.json();
  },

  getProfile: async (): Promise<User> => {
    const res = await fetchClient("/auth/me");
    return res.json();
  },

  // Conversations
  getConversations: async (): Promise<Conversation[]> => {
    const res = await fetchClient("/chat/conversations");
    return res.json();
  },

  createConversation: async (title: string = "New Conversation"): Promise<Conversation> => {
    const res = await fetchClient(`/chat/conversations?title=${encodeURIComponent(title)}`, {
      method: "POST",
    });
    return res.json();
  },

  getConversationDetails: async (convId: number): Promise<Conversation> => {
    const res = await fetchClient(`/chat/conversations/${convId}`);
    return res.json();
  },

  deleteConversation: async (convId: number): Promise<void> => {
    await fetchClient(`/chat/conversations/${convId}`, {
      method: "DELETE",
    });
  },

  submitFeedback: async (feedback: { message_id: number; score: number; comments?: string }): Promise<any> => {
    const res = await fetchClient("/chat/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(feedback),
    });
    return res.json();
  },

  // Documents
  listDocuments: async (): Promise<DocumentInfo[]> => {
    const res = await fetchClient("/documents/");
    return res.json();
  },

  uploadDocument: async (file: File, collectionName: string): Promise<DocumentInfo> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("collection_name", collectionName);

    const token = getAuthToken();
    const headers = {} as Record<string, string>;
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_URL}/documents/upload`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const errText = await res.text();
      let errMsg = "Upload failed";
      try {
        const parsed = JSON.parse(errText);
        errMsg = parsed.detail || errMsg;
      } catch {
        errMsg = errText || errMsg;
      }
      throw new Error(errMsg);
    }
    return res.json();
  },

  deleteDocument: async (docId: number): Promise<void> => {
    await fetchClient(`/documents/${docId}`, {
      method: "DELETE",
    });
  },

  // Admin
  listCollections: async (): Promise<string[]> => {
    const res = await fetchClient("/admin/collections");
    return res.json();
  },

  getDocumentAnalytics: async (): Promise<any> => {
    const res = await fetchClient("/admin/analytics/documents");
    return res.json();
  },

  getConversationAnalytics: async (): Promise<any> => {
    const res = await fetchClient("/admin/analytics/conversations");
    return res.json();
  },

  getDocumentChunks: async (docId: number): Promise<ChunkInfo[]> => {
    const res = await fetchClient(`/admin/chunks?document_id=${docId}`);
    return res.json();
  },

  // SSE Stream helper
  streamResponse: async (
    convId: number,
    query: string,
    collection: string,
    onContent: (chunk: string) => void,
    onCitations: (data: { message_id: number; citations: Citation[] }) => void,
    onError: (err: string) => void,
    onDone: () => void
  ) => {
    const token = getAuthToken();
    const url = `${API_URL}/chat/conversations/${convId}/stream?query=${encodeURIComponent(query)}&collection=${encodeURIComponent(collection)}`;

    try {
      const response = await fetch(url, {
        headers: token ? { "Authorization": `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      if (!reader) throw new Error("No response body reader");

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;

            try {
              const data = JSON.parse(dataStr);
              if (data.type === "content") {
                onContent(data.delta);
              } else if (data.type === "citations") {
                onCitations({ message_id: data.message_id, citations: data.citations });
              } else if (data.type === "done") {
                onDone();
              }
            } catch (e) {
              logger.error("Failed to parse stream packet", e);
            }
          }
        }
      }
    } catch (err: any) {
      onError(err.message || "Streaming connection failed");
    }
  },

  // Agentic Workbench Tools
  analyzeDump: async (dumpText: string): Promise<any> => {
    const res = await fetchClient("/sap-agentic/analyze-dump", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dump_text: dumpText }),
    });
    return res.json();
  },

  searchNotes: async (noteNumber: string, sapBasisVersion: string): Promise<any> => {
    const res = await fetchClient("/sap-agentic/search-notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note_number: noteNumber, sap_basis_version: sapBasisVersion }),
    });
    return res.json();
  },

  authenticateNotes: async (authMode: string, username?: string, password?: string): Promise<any> => {
    const res = await fetchClient("/sap-agentic/authenticate-notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auth_mode: authMode, username, password }),
    });
    return res.json();
  },

  validateCode: async (codeText: string): Promise<any> => {
    const res = await fetchClient("/sap-agentic/validate-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code_text: codeText }),
    });
    return res.json();
  },

  getTransitionGuide: async (): Promise<any> => {
    const res = await fetchClient("/sap-agentic/transition-guide", {
      method: "GET",
    });
    return res.json();
  },

  getIntegrationSpec: async (targetSystem: string): Promise<any> => {
    const res = await fetchClient("/sap-agentic/integration-spec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_system: targetSystem }),
    });
    return res.json();
  },
};

const logger = {
  error: (msg: string, err?: any) => {
    console.error(`[API Client] ${msg}`, err);
  }
};
