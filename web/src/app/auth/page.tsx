"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuth } from "~/core/auth";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";

export default function AuthPage() {
  const t = useTranslations("auth");
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isLogin) {
        await login(username, password);
      } else {
        await register(username, email, password, displayName);
      }
      router.push("/chat");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-8 rounded-lg border bg-card p-8 shadow-lg">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight">
            {isLogin ? t("welcomeBack") : t("createAccount")}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {isLogin ? t("signInPrompt") : t("signUpPrompt")}
          </p>
        </div>

        {error && (
          <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">{t("username")}</Label>
              <Input
                id="username"
                type="text"
                placeholder={t("enterUsername")}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loading}
              />
            </div>

            {!isLogin && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="email">{t("email")}</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder={t("enterEmail")}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={loading}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="displayName">{t("displayName")}</Label>
                  <Input
                    id="displayName"
                    type="text"
                    placeholder={t("enterDisplayName")}
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    disabled={loading}
                  />
                </div>
              </>
            )}

            <div className="space-y-2">
              <Label htmlFor="password">{t("password")}</Label>
              <Input
                id="password"
                type="password"
                placeholder={t("enterPassword")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                disabled={loading}
              />
              {!isLogin && (
                <p className="text-xs text-muted-foreground">
                  {t("passwordMinLength")}
                </p>
              )}
            </div>
          </div>

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t("pleaseWait") : isLogin ? t("signIn") : t("signUp")}
          </Button>
        </form>

        <div className="text-center">
          <button
            type="button"
            onClick={() => {
              setIsLogin(!isLogin);
              setError("");
            }}
            className="text-sm text-primary hover:underline"
            disabled={loading}
          >
            {isLogin ? t("noAccount") : t("hasAccount")}
          </button>
        </div>

        <div className="text-center">
          <button
            type="button"
            onClick={() => router.push("/chat")}
            className="text-sm text-muted-foreground hover:underline"
            disabled={loading}
          >
            {t("continueWithout")}
          </button>
        </div>
      </div>
    </div>
  );
}





