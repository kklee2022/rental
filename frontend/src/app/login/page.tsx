"use client";

import { ArrowRight, LockKeyhole, ShieldCheck, Truck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button, ErrorBanner, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { status, signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [router, status]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const message = await signIn(username, password);
    setSubmitting(false);
    if (message) {
      setError(message);
      return;
    }
    router.replace("/");
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <div className="login-context__grain" />
        <div className="login-brand">
          <div className="brand-mark brand-mark--light">MR</div>
          <div>
            <strong>機械租賃 ERP</strong>
            <span>營運控制台</span>
          </div>
        </div>
        <div className="login-context__copy">
          <span className="eyebrow eyebrow--light">Operations workspace</span>
          <h1>由報價到回倉，在同一個營運節奏內完成。</h1>
          <div className="login-proof">
            <div>
              <Truck size={20} />
              <span>逐台資產與租期分配</span>
            </div>
            <div>
              <ShieldCheck size={20} />
              <span>審批、合約與審計鏈</span>
            </div>
            <div>
              <LockKeyhole size={20} />
              <span>租戶隔離與角色權限</span>
            </div>
          </div>
        </div>
        <div className="login-context__footer">
          <span>Hong Kong</span>
          <span>Asia/Hong_Kong</span>
        </div>
      </section>

      <section className="login-form-panel">
        <div className="login-form-wrap">
          <span className="eyebrow">安全登入</span>
          <h2>進入營運工作台</h2>
          <p className="login-lead">使用你的租戶成員帳戶。</p>
          {error ? <ErrorBanner>{error}</ErrorBanner> : null}
          <form className="stack-form" onSubmit={handleSubmit}>
            <Field label="使用者名稱">
              <Input
                autoComplete="username"
                autoFocus
                onChange={(event) => setUsername(event.target.value)}
                required
                value={username}
              />
            </Field>
            <Field label="密碼">
              <Input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </Field>
            <Button
              className="login-submit"
              disabled={submitting || status === "loading"}
              type="submit"
              variant="primary"
            >
              {submitting ? "正在登入" : "登入"}
              <ArrowRight size={17} />
            </Button>
          </form>
          <p className="login-note">登入憑證由 Django 驗證。</p>
        </div>
      </section>
    </main>
  );
}
