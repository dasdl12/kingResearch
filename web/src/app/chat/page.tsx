// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { GithubOutlined } from "@ant-design/icons";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Suspense, useEffect } from "react";
import { LogIn, LogOut, User } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "~/components/ui/button";

import { Logo } from "../../components/deer-flow/logo";
import { Tooltip } from "../../components/deer-flow/tooltip";
import { ResearchHistoryDialog } from "../settings/dialogs/research-history-dialog";
import { SettingsDialog } from "../settings/dialogs/settings-dialog";
import { useAuth } from "~/core/auth";
import { resetChatState } from "~/core/store/store";
import { restoreChatFromThreadId } from "~/core/api/restore-chat";

const Main = dynamic(() => import("./main"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center">
      {/* Using translation key from chat.page.loading */}
      Loading KingResearch...
    </div>
  ),
});

export default function HomePage() {
  const t = useTranslations("chat.page");
  const { user, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // Handle URL parameters for restoring history or starting new chat
  useEffect(() => {
    const threadId = searchParams.get("thread_id");
    const newChat = searchParams.get("newChat");
    
    if (newChat === "true") {
      // Reset state for new chat
      resetChatState();
      // Clean up URL
      router.replace("/chat");
    } else if (threadId) {
      // Restore chat from history
      restoreChatFromThreadId(threadId).then((success) => {
        if (!success) {
          console.error("Failed to restore chat");
        }
        // Clean up URL after restore
        router.replace("/chat");
      });
    }
  }, [searchParams, router]);

  return (
    <div className="flex h-screen w-screen justify-center overscroll-none">
      <header className="fixed top-0 left-0 flex h-12 w-full items-center justify-between px-4">
        <Logo />
        <div className="flex items-center gap-1">
          {user && (
            <div className="flex items-center gap-2 px-2">
              <span className="text-sm text-muted-foreground">
                {user.display_name || user.username}
              </span>
              <Tooltip title={`Logged in as ${user.username}`}>
                <div className="flex items-center justify-center w-8 h-8">
                  <User className="h-4 w-4" />
                </div>
              </Tooltip>
            </div>
          )}
          
          <Tooltip title={t("starOnGitHub")}>
            <Button variant="ghost" size="icon" asChild>
              <Link
                href="https://github.com/bytedance/deer-flow"
                target="_blank"
              >
                <GithubOutlined />
              </Link>
            </Button>
          </Tooltip>
          <Suspense>
            <ResearchHistoryDialog />
          </Suspense>
          <Suspense>
            <SettingsDialog />
          </Suspense>
          
          {user ? (
            <Tooltip title="Sign Out">
              <Button variant="ghost" size="icon" onClick={logout}>
                <LogOut className="h-4 w-4" />
              </Button>
            </Tooltip>
          ) : (
            <Tooltip title="Sign In">
              <Button variant="ghost" size="icon" onClick={() => router.push("/auth")}>
                <LogIn className="h-4 w-4" />
              </Button>
            </Tooltip>
          )}
        </div>
      </header>
      <Main />
    </div>
  );
}
