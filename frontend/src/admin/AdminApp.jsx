import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./adminApi.js";
import InventoryTab from "./InventoryTab.jsx";
import AgentsTab from "./AgentsTab.jsx";
import UsersTab from "./UsersTab.jsx";
import SettingsTab from "./SettingsTab.jsx";
import RequestsTab from "./RequestsTab.jsx";
import "./admin.css";

function LoginForm({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api("/login", { method: "POST", body: { email, password } });
      setToken(session.token);
      onLoggedIn(session.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-card admin-auth" onSubmit={submit}>
      <h2>Admin login</h2>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <div className="admin-error">{error}</div>}
      <button className="btn btn-primary" disabled={busy}>
        {busy ? "Logging in..." : "Log in"}
      </button>
    </form>
  );
}

export function ChangePasswordForm({ forced, onDone, onCancel }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (next !== confirm) {
      setError("The new passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = await api("/me/password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setToken(session.token);
      onDone(session.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-card admin-auth" onSubmit={submit}>
      <h2>{forced ? "Set your password" : "Change password"}</h2>
      {forced && (
        <p className="admin-muted">
          You logged in with a temporary password. Choose your own to continue.
        </p>
      )}
      <label>
        {forced ? "Temporary password" : "Current password"}
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
      </label>
      <label>
        New password (at least 10 characters)
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} minLength={10} required />
      </label>
      <label>
        Confirm new password
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </label>
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-row">
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Saving..." : "Save password"}
        </button>
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

const TABS = [
  { id: "inventory", label: "Inventory", ownerOnly: false },
  { id: "requests", label: "Requests", ownerOnly: false },
  { id: "agents", label: "Agents", ownerOnly: true },
  { id: "users", label: "Users", ownerOnly: true },
  { id: "settings", label: "Settings", ownerOnly: true },
];

export default function AdminApp() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const [tab, setTab] = useState("inventory");
  const [changingPassword, setChangingPassword] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setChangingPassword(false);
  }, []);

  // Keep the Requests badge fresh while the admin page is open.
  useEffect(() => {
    if (!user || user.must_change_password) return;
    const poll = () => api("/reservations/summary").then((s) => setPendingCount(s.pending)).catch(() => {});
    poll();
    const timer = setInterval(poll, 60000);
    return () => clearInterval(timer);
  }, [user]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!getToken()) return;
    api("/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, [logout]);

  let body;
  if (checking) {
    body = <div className="admin-muted">Loading...</div>;
  } else if (!user) {
    body = <LoginForm onLoggedIn={setUser} />;
  } else if (user.must_change_password) {
    body = <ChangePasswordForm forced onDone={setUser} />;
  } else if (changingPassword) {
    body = (
      <ChangePasswordForm
        onDone={(u) => {
          setUser(u);
          setChangingPassword(false);
        }}
        onCancel={() => setChangingPassword(false)}
      />
    );
  } else {
    const tabs = TABS.filter((t) => !t.ownerOnly || user.role === "owner");
    const active = tabs.some((t) => t.id === tab) ? tab : "inventory";
    body = (
      <>
        <nav className="admin-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={`admin-tab ${active === t.id ? "admin-tab-active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === "requests" && pendingCount > 0 && <span className="tab-badge">{pendingCount}</span>}
            </button>
          ))}
        </nav>
        {active === "inventory" && <InventoryTab />}
        {active === "requests" && <RequestsTab onPendingCount={setPendingCount} />}
        {active === "agents" && <AgentsTab />}
        {active === "users" && <UsersTab me={user} />}
        {active === "settings" && <SettingsTab />}
      </>
    );
  }

  return (
    <div className="admin-root">
      <header className="admin-header">
        <div>
          <h1>The Gem Exchange</h1>
          <span className="admin-muted">Admin</span>
        </div>
        <div className="admin-row">
          <a className="btn btn-link" href="/">
            View shop
          </a>
          {user && !user.must_change_password && (
            <>
              <span className="admin-muted admin-user">
                {user.email} · {user.role}
              </span>
              <button className="btn" onClick={() => setChangingPassword(true)}>
                Change password
              </button>
            </>
          )}
          {user && (
            <button className="btn" onClick={logout}>
              Log out
            </button>
          )}
        </div>
      </header>
      <main>{body}</main>
    </div>
  );
}
