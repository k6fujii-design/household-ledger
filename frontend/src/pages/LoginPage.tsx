import { LogIn } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import { api } from "../api/client";
import { BrandMark } from "../components/BrandMark";

export function LoginPage({ onLogin }: { onLogin: () => Promise<void> }) {
  const [email, setEmail] = useState("f@example.com");
  const [password, setPassword] = useState("password");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.login(email, password);
      await onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ログインに失敗しました");
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel">
        <BrandMark />
        <h1>共有家計簿</h1>
        <p>ふたりの支払いを、さっと記録して気持ちよく精算。</p>
        <form className="form" onSubmit={submit}>
          {error && <div className="error">{error}</div>}
          <label>メールアドレス<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>パスワード<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <button type="submit"><LogIn size={18} />ログイン</button>
        </form>
        <div className="hint">初期ログイン: f@example.com または o@example.com / password</div>
      </section>
    </main>
  );
}
