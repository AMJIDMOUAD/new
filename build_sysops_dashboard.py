# build_sysops_dashboard.py
# Recreates the full SysOps Dashboard repo + a single ZIP for handoff.
# Works offline. Outputs: ./sysops-dashboard-fullbundle.zip

import os, zipfile, textwrap, datetime, pathlib, json

ROOT = pathlib.Path.cwd() / "sysops-dashboard"
ZIP_PATH = pathlib.Path.cwd() / "sysops-dashboard-fullbundle.zip"

def w(path, content, exec=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if exec:
        os.chmod(path, 0o755)

def main():
    if ROOT.exists():
        # start fresh
        import shutil
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True, exist_ok=True)

    # ---------- Top-level ----------
    w(ROOT / "package.json", textwrap.dedent("""\
    {
      "name": "exoverse-sysops-dashboard",
      "version": "1.0.0",
      "private": true,
      "type": "module",
      "scripts": {
        "dev": "vite",
        "build": "vite build",
        "postbuild": "bash ops/write_health.sh dist && bash ops/inject_build_meta.sh dist",
        "preview": "vite preview --port 5174"
      },
      "dependencies": {
        "react": "^18.3.1",
        "react-dom": "^18.3.1",
        "react-router-dom": "^6.26.0"
      },
      "devDependencies": {
        "@types/react": "^18.3.3",
        "@types/react-dom": "^18.3.0",
        "autoprefixer": "^10.4.20",
        "postcss": "^8.4.41",
        "tailwindcss": "^3.4.10",
        "typescript": "^5.5.4",
        "vite": "^5.4.2",
        "@vitejs/plugin-react": "^4.3.1"
      }
    }
    """))

    w(ROOT / ".env.example", textwrap.dedent("""\
    # Public endpoints (read-only for ops UI)
    VITE_STATUS_SUMMARY_URL=https://status.remimediaventures.com/api/summary
    VITE_SLO_STATUS_URL=https://api.remimediaventures.com/_status
    VITE_OPS_COST_MIN_URL=https://ops.remimediaventures.com/cost/minute
    VITE_OPS_AI_SPEND24H_URL=https://ops.remimediaventures.com/ai/spend24h

    # Links (open in new tab)
    VITE_GRAFANA_URL=https://grafana.remimediaventures.com/d/overview
    VITE_LOGS_URL=https://logs.remimediaventures.com/app
    VITE_DLQ_URL=https://ops.remimediaventures.com/queues/dlq
    VITE_AI_CONSOLE_URL=https://dashboard.remimediaventures.com/ai

    # Chatbot (D.A.D.-orchestrated Systems Operator Agent)
    VITE_DAD_AGENT_POST=/ops/agent/post
    VITE_DAD_AGENT_STREAM=/ops/agent/stream

    # JIT / Bootstrap surfaces (SysOps service on your subdomain)
    VITE_JIT_STATUS_URL=https://sysops.remimediaventures.com/ops/repo-access/status
    VITE_JIT_REQUEST_URL=https://sysops.remimediaventures.com/ops/repo-access/request

    # Optional auth header names (if your gateway requires them)
    VITE_AUTH_HEADER=Authorization
    VITE_AUTH_VALUE=Bearer __INJECT_AT_EDGE__
    VITE_OWNER_HEADER=
    VITE_OWNER_VALUE=
    """))

    w(ROOT / "index.html", textwrap.dedent("""\
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Systems Operations Engineer Dashboard • Exoverse</title>
        <meta name="build-rev" content="">
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body class="bg-neutral-50">
        <div id="root"></div>
        <script type="module" src="/src/main.tsx"></script>
      </body>
    </html>
    """))

    w(ROOT / "vite.config.ts", textwrap.dedent("""\
    import { defineConfig } from "vite";
    import react from "@vitejs/plugin-react";
    export default defineConfig({ plugins:[react()], server:{ port:5174 }, build:{ sourcemap:true }});
    """))

    w(ROOT / "tailwind.config.ts", 'import type { Config } from "tailwindcss";\nexport default { content:["./index.html","./src/**/*.{ts,tsx}"], theme:{ extend:{} }, plugins:[] } satisfies Config;\n')
    w(ROOT / "postcss.config.js", 'export default { plugins: { tailwindcss: {}, autoprefixer: {} } };\n')
    w(ROOT / "tsconfig.json", textwrap.dedent("""\
    { "compilerOptions": { "target":"ES2020","lib":["ES2020","DOM"],"jsx":"react-jsx","module":"ESNext","moduleResolution":"Bundler","strict":true,"skipLibCheck":true}, "include":["src"] }
    """))
    w(ROOT / "tsconfig.node.json", '{ "compilerOptions":{ "composite":true,"module":"ESNext","moduleResolution":"Node" } }\n')
    w(ROOT / ".gitignore", "node_modules\ndist\n.env\n.DS_Store\n*.log\n")

    w(ROOT / "Makefile", textwrap.dedent("""\
    .PHONY: deploy-all dash-invalidate cf-security-headers dash-rev-stamp dash-rev-verify

    deploy-all:
    	npm ci
    	npm run build
    	bash ops/write_health.sh dist
    	bash ops/inject_build_meta.sh dist
    	aws s3 sync dist/ $${S3_BUCKET_URL:?}/ --delete
    	bash ops/set_cache_headers.sh
    	aws cloudfront create-invalidation --distribution-id $${CF_DISTRIBUTION_ID:?} --paths "/index.html" "/"
    	sleep 5
    	curl -s $(shell echo $${PUBLIC_HOST:-https://sysops.remimediaventures.com})/healthz.json | jq .
    	curl -sI $(shell echo $${PUBLIC_HOST:-https://sysops.remimediaventures.com})/ | sed -n 's/^x-amz-meta-build-rev:.*/&/p'

    dash-invalidate:
    	aws cloudfront create-invalidation --distribution-id $${CF_DISTRIBUTION_ID:?} --paths "/*"

    cf-security-headers:
    	aws cloudfront create-function --name SysOpsSecHeaders --function-config Comment="SysOps sec headers",Runtime="cloudfront-js-1.0" --function-code fileb://ops/cf_function_security_headers.js >/dev/null 2>&1 || true

    dash-rev-stamp:
    	REV=$$(grep -o 'name="build-rev" content="[^"]*"' dist/index.html | sed -E 's/.*content="([^"]*)".*/\\1/'); \
    	aws s3 cp dist/index.html $${S3_BUCKET_URL:?}/index.html \
    	  --metadata-directive REPLACE --cache-control "no-cache" \
    	  --content-type "text/html; charset=utf-8" --metadata build-rev="$$REV"; \
    	aws cloudfront create-invalidation --distribution-id $${CF_DISTRIBUTION_ID:?} --paths "/index.html"

    dash-rev-verify:
    	curl -sI $(shell echo $${PUBLIC_HOST:-https://sysops.remimediaventures.com})/ | sed -n 's/^x-amz-meta-build-rev:.*/&/p'; \
    	curl -s $(shell echo $${PUBLIC_HOST:-https://sysops.remimediaventures.com})/healthz.json | jq .
    """))

    # ---------- ops scripts ----------
    w(ROOT / "ops/write_health.sh", textwrap.dedent("""\
    #!/usr/bin/env bash
    set -euo pipefail
    DIR="${1:-dist}"; mkdir -p "$DIR"
    ts="$(date -Iseconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")"
    commit="$(git rev-parse --verify HEAD 2>/dev/null || echo unknown)"
    short="${commit:0:7}"
    cat > "${DIR}/healthz.json" <<JSON
    {"status":"ok","ts":"${ts}","app":{"name":"SysOps Dashboard","version":""},"git":{"short":"${short}"}}
    JSON
    echo "✅ wrote ${DIR}/healthz.json"
    """), exec=True)

    w(ROOT / "ops/inject_build_meta.sh", textwrap.dedent("""\
    #!/usr/bin/env bash
    set -euo pipefail
    DIST="${1:-dist}"; HTML="${DIST}/index.html"; [[ -f "$HTML" ]] || exit 2
    ts="$(date -Iseconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")"
    short="$(git rev-parse --short HEAD 2>/dev/null || echo 'local')"
    tmp="$(mktemp)"
    awk -v ts="$ts" -v rev="$short" '
    /<\/head>/ && !done { print "  <meta name=\\"build-rev\\" content=\\"" rev "\\">"; print "  <meta name=\\"build-ts\\" content=\\"" ts "\\">"; done=1 } { print }
    ' "$HTML" > "$tmp" && mv "$tmp" "$HTML"
    echo "✅ injected meta into ${HTML}"
    """), exec=True)

    w(ROOT / "ops/set_cache_headers.sh", textwrap.dedent("""\
    #!/usr/bin/env bash
    set -euo pipefail
    : "${BUCKET:=${S3_BUCKET_URL:?}}"
    : "${DIST:=dist}"
    aws s3 cp "$DIST/" "$BUCKET/" --recursive --exclude "*" --include "assets/*" \
      --metadata-directive REPLACE --cache-control "public,max-age=31536000,immutable"
    for f in index.html healthz.json; do
      [[ -f "$DIST/$f" ]] || continue
      mime="text/html; charset=utf-8"; [[ "$f" == "healthz.json" ]] && mime="application/json"
      aws s3 cp "$DIST/$f" "$BUCKET/$f" --metadata-directive REPLACE --cache-control "no-cache" --content-type "$mime"
    done
    echo "✅ cache headers applied"
    """), exec=True)

    # ---------- src ----------
    w(ROOT / "src/index.css", "@tailwind base;\\n@tailwind components;\\n@tailwind utilities;\\n\\nhtml, body, #root { height: 100%; }\\n")

    w(ROOT / "src/main.tsx", textwrap.dedent("""\
    import React from "react";
    import ReactDOM from "react-dom/client";
    import { createBrowserRouter, RouterProvider } from "react-router-dom";
    import "./index.css";
    import App from "./App";
    import Overview from "./pages/overview";
    import Incidents from "./pages/incidents";
    import Infra from "./pages/infra";
    import Queues from "./pages/queues";
    import Cost from "./pages/cost";
    import AI from "./pages/ai";

    const router = createBrowserRouter([
      {
        path: "/",
        element: <App />,
        children: [
          { path: "/", element: <Overview /> },
          { path: "/incidents", element: <Incidents /> },
          { path: "/infra", element: <Infra /> },
          { path: "/queues", element: <Queues /> },
          { path: "/cost", element: <Cost /> },
          { path: "/ai", element: <AI /> }
        ]
      }
    ]);

    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode><RouterProvider router={router} /></React.StrictMode>
    );
    """))

    w(ROOT / "src/App.tsx", textwrap.dedent("""\
    import React from "react";
    import { Outlet, NavLink } from "react-router-dom";

    function Tab({ to, children }: React.PropsWithChildren<{ to: string }>) {
      return (
        <NavLink
          to={to}
          className={({ isActive }) =>
            `px-3 py-2 rounded-xl border hover:bg-neutral-100 ${isActive ? "bg-black text-white border-black" : "bg-white"}`
          }
        >
          {children}
        </NavLink>
      );
    }

    export default function App() {
      return (
        <div className="min-h-screen">
          <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b">
            <div className="max-w-[1200px] mx-auto px-4 py-3 flex items-center justify-between">
              <div className="font-semibold">Exoverse • Systems Operations Engineer</div>
              <nav className="flex gap-2 text-sm">
                <Tab to="/">Overview</Tab>
                <Tab to="/incidents">Incidents</Tab>
                <Tab to="/infra">Infra</Tab>
                <Tab to="/queues">Queues</Tab>
                <Tab to="/cost">Cost</Tab>
                <Tab to="/ai">AI Lanes</Tab>
              </nav>
            </div>
          </header>
          <main className="max-w-[1200px] mx-auto p-4"><Outlet /></main>
          <footer className="max-w-[1200px] mx-auto px-4 py-6 text-xs text-neutral-500">
            © REMI / Exoverse — Least-privilege SysOps surface. All actions audited via D.A.D.
          </footer>
        </div>
      );
    }
    """))

    w(ROOT / "src/lib/api.ts", textwrap.dedent("""\
    export const env = {
      STATUS_SUMMARY: import.meta.env.VITE_STATUS_SUMMARY_URL || "",
      SLO_STATUS: import.meta.env.VITE_SLO_STATUS_URL || "",
      COST_MIN: import.meta.env.VITE_OPS_COST_MIN_URL || "",
      AI_SPEND24H: import.meta.env.VITE_OPS_AI_SPEND24H_URL || "",
      GRAFANA_URL: import.meta.env.VITE_GRAFANA_URL || "",
      LOGS_URL: import.meta.env.VITE_LOGS_URL || "",
      DLQ_URL: import.meta.env.VITE_DLQ_URL || "",
      AI_CONSOLE_URL: import.meta.env.VITE_AI_CONSOLE_URL || "",
      DAD_AGENT_POST: import.meta.env.VITE_DAD_AGENT_POST || "",
      DAD_AGENT_STREAM: import.meta.env.VITE_DAD_AGENT_STREAM || "",
      AUTH_HEADER: import.meta.env.VITE_AUTH_HEADER || "",
      AUTH_VALUE: import.meta.env.VITE_AUTH_VALUE || "",
      OWNER_HEADER: import.meta.env.VITE_OWNER_HEADER || "",
      OWNER_VALUE: import.meta.env.VITE_OWNER_VALUE || "",
      JIT_STATUS_URL: import.meta.env.VITE_JIT_STATUS_URL || "",
      JIT_REQUEST_URL: import.meta.env.VITE_JIT_REQUEST_URL || ""
    };

    export async function getJSON(url: string) {
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (env.AUTH_HEADER && env.AUTH_VALUE) headers[env.AUTH_HEADER] = env.AUTH_VALUE;
      if (env.OWNER_HEADER && env.OWNER_VALUE) headers[env.OWNER_HEADER] = env.OWNER_VALUE;
      const res = await fetch(url, { headers, cache: "no-cache" });
      if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
      return res.json();
    }

    export async function postJSON(url: string, body: any) {
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (env.AUTH_HEADER && env.AUTH_VALUE) headers[env.AUTH_HEADER] = env.AUTH_VALUE;
      if (env.OWNER_HEADER && env.OWNER_VALUE) headers[env.OWNER_VALUE] = env.OWNER_VALUE;
      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(`POST ${url} -> ${res.status}`);
      return res.json();
    }

    export function sse(url: string, body?: any, onMessage?: (line: string) => void, onOpen?: ()=>void, onDone?: ()=>void) {
      const controller = new AbortController();
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (env.AUTH_HEADER && env.AUTH_VALUE) headers[env.AUTH_HEADER] = env.AUTH_VALUE;
      if (env.OWNER_HEADER && env.OWNER_VALUE) headers[env.OWNER_HEADER] = env.OWNER_VALUE;

      fetch(url, { method: "GET", headers, body: body ? JSON.stringify(body) : undefined, signal: controller.signal })
        .then(async (res) => {
          onOpen?.();
          const dec = new TextDecoder();
          const rd = res.body?.getReader();
          if (!rd) return;
          while (true) {
            const { value, done } = await rd.read();
            if (done) break;
            const txt = dec.decode(value);
            txt.split(/\\n\\n+/).forEach((chunk) => chunk && onMessage?.(chunk));
          }
        })
        .finally(() => onDone?.());

      return () => controller.abort();
    }

    export async function getJitStatus() {
      if (!env.JIT_STATUS_URL) return null;
      try { return await getJSON(env.JIT_STATUS_URL); } catch { return null; }
    }

    export async function requestJitAccess(req: {
      repo_id: string; scope: "read"|"triage"|"write"|"merge"; ttl_minutes?: number; reason?: string;
    }) {
      if (!env.JIT_REQUEST_URL) throw new Error("JIT request endpoint not configured");
      return postJSON(env.JIT_REQUEST_URL, req);
    }
    """))

    w(ROOT / "src/components/KPI.tsx", "import React from 'react';\nexport default function KPI({label,value,hint}:{label:string;value:React.ReactNode;hint?:string;}){return(<div className='rounded-2xl border p-3 bg-white'><div className='text-xs text-neutral-500'>{label}</div><div className='text-2xl font-semibold'>{value}</div>{hint?<div className='text-xs text-neutral-400 mt-1'>{hint}</div>:null}</div>);}\n")
    w(ROOT / "src/components/StatusCard.tsx", "import React from 'react';\nexport default function StatusCard({title,children}:React.PropsWithChildren<{title:string}>){return(<div className='rounded-2xl border p-4 bg-white'><div className='font-semibold mb-2'>{title}</div>{children}</div>);}\n")

    w(ROOT / "src/components/AgentChat.tsx", textwrap.dedent("""\
    import React, { useRef, useState } from "react";
    import { env, postJSON, sse } from "../lib/api";

    type Msg = { role: "user" | "agent"; text: string; ts: string };

    export default function AgentChat() {
      const [msgs, setMsgs] = useState<Msg[]>([]);
      const [input, setInput] = useState("");
      const [busy, setBusy] = useState(false);
      const listRef = useRef<HTMLDivElement>(null);
      const canStream = !!env.DAD_AGENT_STREAM;

      const push = (m: Msg) => {
        setMsgs((prev) => [...prev, m]);
        setTimeout(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }), 0);
      };

      const send = async () => {
        const text = input.trim();
        if (!text || !env.DAD_AGENT_POST) return;
        setInput("");
        push({ role: "user", text, ts: new Date().toISOString() });
        setBusy(true);
        try {
          const res = await postJSON(env.DAD_AGENT_POST, { prompt: text, metadata: { surface: "sysops", lane: "ops.agent" }});
          push({ role: "agent", text: JSON.stringify(res), ts: new Date().toISOString() });
        } catch (e: any) {
          push({ role: "agent", text: `Error: ${e.message}`, ts: new Date().toISOString() });
        } finally { setBusy(false); }
      };

      const startStream = () => {
        const text = input.trim();
        if (!text || !env.DAD_AGENT_STREAM) return;
        setInput("");
        push({ role: "user", text, ts: new Date().toISOString() });
        let acc = ""; setBusy(true);
        const stop = sse(env.DAD_AGENT_STREAM, { prompt: text, metadata: { surface: "sysops", lane: "ops.agent.stream" } },
          (line) => { acc += line + "\\n"; }, undefined,
          () => { push({ role: "agent", text: acc || "[no output]", ts: new Date().toISOString() }); setBusy(false); }
        );
        return stop;
      };

      return (
        <div className="rounded-2xl border bg-white p-3 flex flex-col h-[420px]">
          <div className="font-semibold mb-2">Systems Operator Agent (via D.A.D.)</div>
          <div ref={listRef} className="flex-1 overflow-auto space-y-2">
            {msgs.map((m, i) => (
              <div key={i} className={`text-sm p-2 rounded-xl ${m.role === "user" ? "bg-neutral-100" : "bg-neutral-50 border"}`}>
                <div className="text-xs text-neutral-400">{m.role} • {new Date(m.ts).toLocaleTimeString()}</div>
                <pre className="whitespace-pre-wrap">{m.text}</pre>
              </div>
            ))}
            {msgs.length === 0 && <div className="text-sm text-neutral-500">Type a question for the SysOps agent…</div>}
          </div>
          <div className="mt-2 flex gap-2">
            <input className="flex-1 border rounded-xl px-3 py-2" placeholder="Ask the Systems Operator Agent…" value={input} onChange={(e)=>setInput(e.target.value)} onKeyDown={(e)=>(e.key==="Enter"?send():undefined)} />
            <button onClick={send} disabled={busy || !env.DAD_AGENT_POST} className="px-3 py-2 rounded-xl bg-black text-white disabled:opacity-50">Send</button>
            {canStream && <button onClick={startStream} disabled={busy} className="px-3 py-2 rounded-xl border">Stream</button>}
          </div>
          {!env.DAD_AGENT_POST && <div className="text-xs text-red-500 mt-2">Configure VITE_DAD_AGENT_POST to enable chat.</div>}
        </div>
      );
    }
    """))

    w(ROOT / "src/components/BootstrapBanner.tsx", textwrap.dedent("""\
    import React from "react";
    export default function BootstrapBanner({ expiresAt }: { expiresAt?: string }) {
      return (
        <div className="rounded-2xl border p-3 bg-amber-50 border-amber-300">
          <div className="font-semibold text-amber-900">Bootstrap Mode Active</div>
          <div className="text-sm text-amber-800">
            SysOps currently has repo credentials without JIT approval. Use for setup only.
            {!!expiresAt && <> Expires: <code>{new Date(expiresAt).toLocaleString()}</code></>}
          </div>
        </div>
      );
    }
    """))

    w(ROOT / "src/components/JITRequest.tsx", textwrap.dedent("""\
    import React, { useState } from "react";
    import { requestJitAccess } from "../lib/api";

    export default function JITRequest() {
      const [repo, setRepo] = useState("remi/sysops-dashboard");
      const [scope, setScope] = useState<"read"|"triage"|"write"|"merge">("write");
      const [ttl, setTtl] = useState(120);
      const [reason, setReason] = useState("");
      const [msg, setMsg] = useState<string>("");

      const submit = async () => {
        setMsg("");
        try {
          const r = await requestJitAccess({ repo_id: repo, scope, ttl_minutes: ttl, reason });
          setMsg(`Requested (id: ${r.request_id || "pending"}) — watch D.A.D./Slack for approval.`);
        } catch (e:any) { setMsg(`Error: ${e.message}`); }
      };

      return (
        <div className="rounded-2xl border p-3 bg-white">
          <div className="font-semibold mb-2">Request Temporary Repo Access</div>
          <div className="grid gap-2 md:grid-cols-4">
            <input className="border rounded-xl px-3 py-2 md:col-span-2" value={repo} onChange={e=>setRepo(e.target.value)} />
            <select className="border rounded-xl px-3 py-2" value={scope} onChange={e=>setScope(e.target.value as any)}>
              <option>read</option><option>triage</option><option>write</option><option>merge</option>
            </select>
            <input type="number" className="border rounded-xl px-3 py-2" value={ttl} onChange={e=>setTtl(+e.target.value)} />
          </div>
          <input className="border rounded-xl px-3 py-2 mt-2 w-full" placeholder="Reason (change window, ticket, etc.)" value={reason} onChange={e=>setReason(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <button onClick={submit} className="px-3 py-2 rounded-xl bg-black text-white">Request</button>
            {msg && <div className="text-sm text-neutral-600">{msg}</div>}
          </div>
          <div className="text-xs text-neutral-500 mt-2">Owner/approver completes approval in D.A.D. console.</div>
        </div>
      );
    }
    """))

    # pages
    w(ROOT / "src/pages/overview.tsx", textwrap.dedent("""\
    import React from "react";
    import KPI from "../components/KPI";
    import StatusCard from "../components/StatusCard";
    import AgentChat from "../components/AgentChat";
    import BootstrapBanner from "../components/BootstrapBanner";
    import JITRequest from "../components/JITRequest";
    import { env, getJSON, getJitStatus } from "../lib/api";

    export default function Overview() {
      const [incidents, setIncidents] = React.useState<number | null>(null);
      const [p95, setP95] = React.useState<number | null>(null);
      const [success, setSuccess] = React.useState<number | null>(null);
      const [jit, setJit] = React.useState<{active?:boolean; grant?: any} | null>(null);

      React.useEffect(() => {
        const refresh = async () => {
          try {
            if (env.STATUS_SUMMARY) {
              const j = await getJSON(env.STATUS_SUMMARY);
              setIncidents(j?.active?.count ?? 0);
            }
            if (env.SLO_STATUS) {
              const j = await getJSON(env.SLO_STATUS);
              setP95(j?.slo?.p95_ms ?? null);
              setSuccess(j?.slo?.success_rate ?? null);
            }
            const s = await getJitStatus();
            setJit(s);
          } catch {}
        };
        refresh();
        const t = setInterval(refresh, 30000);
        return () => clearInterval(t);
      }, []);

      const isBootstrap = !!jit?.grant && jit?.grant.mode === "bootstrap";
      const hasActiveGrant = !!jit?.active;

      return (
        <div className="grid gap-4">
          {isBootstrap && <BootstrapBanner expiresAt={jit?.grant?.expires_at} />}

          <div className="grid gap-4 md:grid-cols-3">
            <KPI label="Active Incidents" value={incidents ?? "—"} />
            <KPI label="API p95 (ms)" value={p95 ?? "—"} />
            <KPI label="Success Rate" value={success != null ? `${Math.round(success * 1000) / 10}%` : "—"} />
          </div>

          {!isBootstrap && (
            hasActiveGrant
              ? <StatusCard title="Repo Access (Active)">
                  <div className="text-sm">
                    Scope: <code>{jit?.grant?.scope || "?"}</code> •
                    Expires: <code>{jit?.grant?.expires_at ? new Date(jit.grant.expires_at).toLocaleString() : "—"}</code>
                  </div>
                </StatusCard>
              : <JITRequest />
          )}

          <div className="md:col-span-2">
            <StatusCard title="Notes">
              <ul className="list-disc ml-5 text-sm text-neutral-600">
                <li>Least-privilege: no destructive actions exposed here.</li>
                <li>All requests audited and routed via D.A.D. (REMI native grants).</li>
              </ul>
            </StatusCard>
          </div>

          <AgentChat />
        </div>
      );
    }
    """))

    w(ROOT / "src/pages/incidents.tsx", textwrap.dedent("""\
    import React from "react";
    import StatusCard from "../components/StatusCard";
    import { env } from "../lib/api";
    export default function Incidents() {
      return (
        <div className="grid gap-4 md:grid-cols-2">
          <StatusCard title="Incident Banner (embed)">
            <div className="aspect-video bg-white border rounded-xl overflow-hidden">
              <iframe title="status" src="https://status.exoverse.io/embed/banner" className="w-full h-full"/>
            </div>
          </StatusCard>
          <StatusCard title="Raw API">
            <a className="text-blue-600 underline text-sm" href={env.STATUS_SUMMARY || "#"} target="_blank" rel="noreferrer">
              {env.STATUS_SUMMARY || "Configure VITE_STATUS_SUMMARY_URL"}
            </a>
          </StatusCard>
        </div>
      );
    }
    """))

    w(ROOT / "src/pages/infra.tsx", textwrap.dedent("""\
    import React from "react";
    import StatusCard from "../components/StatusCard";
    import { env } from "../lib/api";
    export default function Infra() {
      return (
        <div className="grid gap-4 md:grid-cols-2">
          <StatusCard title="Grafana">
            <a className="inline-block px-3 py-2 rounded-xl bg-black text-white text-sm" href={env.GRAFANA_URL} target="_blank" rel="noreferrer">Open Grafana</a>
          </StatusCard>
          <StatusCard title="Logs (Loki/Elastic)">
            <a className="inline-block px-3 py-2 rounded-xl bg-black text-white text-sm" href={env.LOGS_URL} target="_blank" rel="noreferrer">Open Logs</a>
          </StatusCard>
        </div>
      );
    }
    """))

    w(ROOT / "src/pages/queues.tsx", textwrap.dedent("""\
    import React from "react";
    import StatusCard from "../components/StatusCard";
    import { env } from "../lib/api";
    export default function Queues() {
      return (
        <div className="grid gap-4">
          <StatusCard title="DLQ Viewer">
            <a className="inline-block px-3 py-2 rounded-xl bg-black text-white text-sm" href={env.DLQ_URL} target="_blank" rel="noreferrer">Open DLQ Viewer</a>
          </StatusCard>
        </div>
      );
    }
    """))

    w(ROOT / "src/pages/cost.tsx", textwrap.dedent("""\
    import React from "react";
    import KPI from "../components/KPI";
    import StatusCard from "../components/StatusCard";
    import { env, getJSON } from "../lib/api";
    export default function Cost() {
      const [perMin, setPerMin] = React.useState<number | null>(null);
      const [margin, setMargin] = React.useState<number | null>(null);
      const [usd24, setUsd24] = React.useState<number | null>(null);
      const [tok24, setTok24] = React.useState<number | null>(null);
      async function refresh() {
        try {
          if (env.COST_MIN) {
            const j = await getJSON(env.COST_MIN);
            setPerMin(j?.cost?.per_minute_usd ?? null);
            setMargin(j?.cost?.margin_ratio ?? null);
          }
          if (env.AI_SPEND24H) {
            const j = await getJSON(env.AI_SPEND24H);
            setUsd24(j?.spend?.usd_24h ?? null);
            setTok24(j?.spend?.tokens_24h ?? null);
          }
        } catch {}
      }
      React.useEffect(() => { refresh(); const t=setInterval(refresh,60000); return()=>clearInterval(t); }, []);
      return (
        <div className="grid gap-4 md:grid-cols-4">
          <KPI label="$/min" value={perMin != null ? `$${perMin.toFixed(3)}` : "—"} />
          <KPI label="Margin" value={margin != null ? `${(Math.round(margin*100)/100)}×` : "—"} hint="Target ≥ 1.5×" />
          <KPI label="AI USD (24h)" value={usd24 != null ? `$${usd24.toFixed(2)}` : "—"} />
          <KPI label="AI Tokens (24h)" value={tok24 ?? "—"} />
          <div className="md:col-span-4">
            <StatusCard title="Notes"><div className="text-sm text-neutral-600">Costs refresh every 60s. This page is read-only.</div></StatusCard>
          </div>
        </div>
      );
    }
    """))

    w(ROOT / "src/pages/ai.tsx", textwrap.dedent("""\
    import React from "react";
    import StatusCard from "../components/StatusCard";
    import { env } from "../lib/api";
    export default function AI() {
      return (
        <div className="grid gap-4">
          <StatusCard title="AI Lanes (read-only)">
            <a className="inline-block px-3 py-2 rounded-xl bg-black text-white text-sm" href={env.AI_CONSOLE_URL} target="_blank" rel="noreferrer">Open AI Console (View)</a>
            <div className="text-xs text-neutral-500 mt-2">This SysOps surface does not expose write lanes.</div>
          </StatusCard>
        </div>
      );
    }
    """))

    # ---------- backend service sample ----------
    w(ROOT / "services/sysops/repoAccess.js", textwrap.dedent("""\
    import express from "express";
    import fetch from "node-fetch";
    const router = express.Router();
    const { REPO_BOOTSTRAP="0", REPO_JIT_ENABLED="1", REPO_SERVICE="https://repo.remi.internal", REPO_DEFAULT_TTL_MIN="120" } = process.env;

    router.use((req, res, next) => {
      if (REPO_BOOTSTRAP === "1") {
        req.repoGrant = { mode:"bootstrap", scope:"admin", token:"ephemeral-bootstrap-"+Date.now(), expires_at:new Date(Date.now()+8*60*60*1000).toISOString() };
      }
      next();
    });

    router.post("/ops/repo-access/request", async (req, res) => {
      if (REPO_BOOTSTRAP === "1") return res.json({ note:"Bootstrap mode: repo access already active" });
      if (REPO_JIT_ENABLED !== "1") return res.status(403).json({ error:"JIT access disabled" });
      const { scope="read", ttl_minutes=REPO_DEFAULT_TTL_MIN, reason="" } = req.body || {};
      const requestId = "req-" + Date.now();
      console.log("Repo access requested:", { requestId, scope, ttl_minutes, reason });
      res.json({ request_id: requestId, status: "requested" });
    });

    router.post("/ops/repo-access/approve", async (req, res) => {
      const { request_id, scope="read", ttl_minutes=REPO_DEFAULT_TTL_MIN } = req.body || {};
      const grant = await fetch(`${REPO_SERVICE}/api/repo/grants/issue`, { method:"POST", headers:{ "content-type":"application/json" }, body:JSON.stringify({ user_id:req.user?.sub||"unknown", scope, ttl_minutes }) }).then(r=>r.json());
      res.json({ request_id, ...grant });
    });

    router.post("/ops/repo-access/revoke", async (req, res) => {
      const { grant_id } = req.body || {};
      await fetch(`${REPO_SERVICE}/api/repo/grants/revoke`, { method:"POST", headers:{ "content-type":"application/json" }, body:JSON.stringify({ grant_id }) });
      res.json({ revoked:true, grant_id });
    });

    router.get("/ops/repo-access/status", (req, res) => {
      if (req.repoGrant) return res.json({ active:true, grant:req.repoGrant });
      res.json({ active:false });
    });

    export default router;
    """))

    w(ROOT / "services/sysops/server.js", textwrap.dedent("""\
    import express from "express";
    import repoAccessRoutes from "./repoAccess.js";
    const app = express();
    app.use(express.json());
    app.use((req, _, next)=>{ req.user={ sub:"sysops-engineer-123", role:"ops" }; next(); });
    app.use(repoAccessRoutes);
    app.get("/healthz.json", (req,res)=>res.json({ status:"ok", app:"SysOps Service", fqdn:"sysops.remimediaventures.com" }));
    app.listen(process.env.PORT||3000, ()=>console.log("SysOps service running on :"+(process.env.PORT||3000)));
    """))

    # ---------- docs ----------
    w(ROOT / "README_FIVERR.md", textwrap.dedent("""\
    # SysOps Dashboard (Exoverse / REMI Media Ventures)

    ## Quick Deploy (S3 + CloudFront)
    ```bash
    npm ci
    npm run build
    export S3_BUCKET_URL=s3://sysops.remimediaventures.com
    export CF_DISTRIBUTION_ID=XXXXXX
    make deploy-all
    ```

    CloudFront: SPA errors 403/404 -> /index.html, TLS via ACM for *.remimediaventures.com

    ## Modes
    - Bootstrap: `REPO_BOOTSTRAP=1 node services/sysops/server.js`
    - JIT:       `REPO_BOOTSTRAP=0 REPO_JIT_ENABLED=1 node services/sysops/server.js`

    See SECURITY_NOTES.md for safety overview.
    """))

    w(ROOT / "SECURITY_NOTES.md", textwrap.dedent("""\
    # Security Notes
    - Static UI; does not touch local Git or keys.
    - Repo access only via D.A.D. (Bootstrap or JIT with approval).
    - Hosting needs no repo handshake; JIT lanes require existing integration.
    - Safety: REPO_BOOTSTRAP=0 in prod; REPO_JIT_ENABLED=0 kills new grants.
    """))

    w(ROOT / "FIVERR_QUICKSTART.txt", textwrap.dedent(f"""\
    TONIGHT DEPLOY — 5 STEPS (SysOps Dashboard)

    1) Install deps & build
       npm ci
       npm run build

    2) (Optional) postbuild helpers
       bash ops/write_health.sh dist
       bash ops/inject_build_meta.sh dist

    3) Upload to S3
       export S3_BUCKET_URL=s3://sysops.remimediaventures.com
       aws s3 sync dist/ $S3_BUCKET_URL/ --delete

    4) CloudFront
       export CF_DISTRIBUTION_ID=YOUR_DIST_ID
       aws cloudfront create-invalidation --distribution-id $CF_DISTRIBUTION_ID --paths "/index.html" "/"
       (Ensure SPA errors 403/404 -> /index.html; ACM cert for *.remimediaventures.com)

    5) Verify
       curl -s https://sysops.remimediaventures.com/healthz.json | jq .
       curl -sI https://sysops.remimediaventures.com/ | sed -n 's/^x-amz-meta-build-rev:.*/&/p'

    Setup-only (optional):
    - REPO_BOOTSTRAP=1 node services/sysops/server.js
    After setup:
    - REPO_BOOTSTRAP=0 REPO_JIT_ENABLED=1 node services/sysops/server.js
    """))

    # ---------- prebuilt dist (placeholder so it's viewable immediately) ----------
    (ROOT / "dist").mkdir(parents=True, exist_ok=True)
    w(ROOT / "dist/index.html", "<!doctype html><html><body><div id='root'>Prebuilt SysOps Dashboard</div></body></html>")
    w(ROOT / "dist/healthz.json", json.dumps({"status":"ok","ts":datetime.datetime.utcnow().isoformat()+"Z"}))

    # ---------- zip everything ----------
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(ROOT))

    print(f"\\n✅ Done. Folder created: {ROOT}")
    print(f"✅ Handoff ZIP: {ZIP_PATH}")

if __name__ == "__main__":
    main()
