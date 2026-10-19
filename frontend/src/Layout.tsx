import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, describe } from "./api";
import { useAuth } from "./auth";
import { BANNER, label, Pill, useToast } from "./components";
import type { Notification } from "./types";

const NAV = [
  { to: "/kg", text: "My KG", verified: true },
  { to: "/directory", text: "Directory", verified: true },
  { to: "/discover", text: "Discover", verified: true },
  { to: "/channels", text: "My channels", verified: true },
  { to: "/requests", text: "Requests", verified: true },
  { to: "/matches", text: "Matches", verified: true },
  { to: "/audit", text: "Audit", verified: false },
];

export function Banner() {
  return <div className="banner" role="note" data-testid="banner">{BANNER}</div>;
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ notifications: Notification[] }>("/v1/notifications"),
    refetchInterval: 4000,
  });
  const markRead = useMutation({
    mutationFn: (id: string) => api(`/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const items = data?.notifications ?? [];
  const unread = items.filter((n) => !n.read).length;
  return (
    <div className="notif">
      <button className="ghost" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="notifications-toggle">
        Notifications {unread > 0 && <span className="badge" data-testid="notifications-unread">{unread}</span>}
      </button>
      {open && (
        <div className="notif-panel" role="dialog" aria-label="Notifications">
          {items.length === 0 && <p className="muted">No notifications.</p>}
          {items.map((n) => (
            <button key={n.id} className={`notif-item ${n.read ? "read" : ""}`} onClick={() => markRead.mutate(n.id)}>
              <strong>{label(n.kind)}</strong>
              <span className="muted small">{new Date(n.created_at).toLocaleString()}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function DemoControls() {
  const qc = useQueryClient();
  const toast = useToast();
  const { me, login } = useAuth();
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api<{ test_mode: boolean }>("/v1/health") });
  const advance = useMutation({
    mutationFn: (seconds: number) => api("/v1/test/clock/advance", { method: "POST", body: { seconds } }),
    onSuccess: async () => {
      // Sessions expire on the registry clock; re-issue this tab's demo session at the new time.
      // Other tabs' sessions expire as they would in reality.
      if (me) await login(me.researcher_id);
      qc.invalidateQueries();
      toast("Demo clock advanced (registry and agents). Other open sessions may need to sign in again.");
    },
    onError: (e) => toast(describe(e), "bad"),
  });
  if (!health?.test_mode) return null;
  return (
    <div className="demo-controls" aria-label="Demo clock">
      <span className="muted small">Demo clock:</span>
      <button className="ghost small" onClick={() => advance.mutate(3600)} data-testid="clock-1h">+1 h</button>
      <button className="ghost small" onClick={() => advance.mutate(24 * 3600)} data-testid="clock-24h">+24 h</button>
    </div>
  );
}

export function Layout() {
  const { me, logout } = useAuth();
  if (!me) return null;
  return (
    <>
      <Banner />
      <header className="topbar">
        <div className="brand">FederatedKG</div>
        <nav aria-label="Main">
          {NAV.filter((n) => me.verified_researcher || !n.verified).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}
              data-testid={`nav-${n.to.slice(1)}`}>
              {n.text}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <DemoControls />
          {me.verified_researcher && <Notifications />}
          <span data-testid="signed-in-as">{me.display_name}</span>
          <Pill value={me.verified_researcher ? "verified" : "unverified"} tone={me.verified_researcher ? "ok" : "bad"} />
          <button className="ghost" onClick={logout} data-testid="sign-out">Sign out</button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </>
  );
}
