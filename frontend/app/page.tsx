"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAuthToken } from "@/lib/api";

export default function HomeRedirect() {
  const router = useRouter();

  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      router.push("/chat");
    } else {
      router.push("/auth");
    }
  }, [router]);

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-[#05070e]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-purple-500 border-t-transparent"></div>
        <p className="text-sm font-medium text-slate-400">Loading SAP AI Knowledge Assistant...</p>
      </div>
    </div>
  );
}
