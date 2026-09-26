import { useEffect, useState } from "react";
import { api } from "./adminApi.js";

function TempPasswordNotice({ email, password, onDismiss }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      // Clipboard blocked - the password is still visible to copy by hand.
    }
  }

  return (
    <div className="admin-card temp-password">
      <h3>Temporary password for {email}</h3>
      <p>
        Send this to them privately. It's shown <strong>only once</strong>. They'll
        be asked to choose their own password when they first log in at <code>/admin</code>.
      </p>
      <div className="admin-row">
        <code className="temp-password-value">{password}</code>
        <button className="btn" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <button className="btn btn-primary" onClick={onDismiss}>
          Done
        </button>
      </div>
    </div>
  );
}

export default function UsersTab({ me }) {
  const [users, setUsers] = useState([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("staff");
  const [temp, setTemp] = useState(null); // {email, password}
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/users").then(setUsers).catch((err) => setError(err.message));
  }, []);

  function replaceUser(updated) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
  }

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const addUser = (e) => {
    e.preventDefault();
    run(async () => {
      const res = await api("/users", { method: "POST", body: { email, role } });
      setUsers((prev) => [...prev, res.user].sort((a, b) => a.email.localeCompare(b.email)));
      setTemp({ email: res.user.email, password: res.temp_password });
      setEmail("");
      setRole("staff");
    });
  };

  const changeRole = (u, newRole) =>
    run(async () => replaceUser(await api(`/users/${u.id}`, { method: "PATCH", body: { role: newRole } })));

  const resetPassword = (u) => {
    if (!window.confirm(`Reset the password for ${u.email}? They'll be logged out.`)) return;
    run(async () => {
      const res = await api(`/users/${u.id}/reset-password`, { method: "POST" });
      replaceUser(res.user);
      setTemp({ email: u.email, password: res.temp_password });
    });
  };

  const removeUser = (u) => {
    if (!window.confirm(`Remove ${u.email}? They won't be able to log in.`)) return;
    run(async () => {
      await api(`/users/${u.id}`, { method: "DELETE" });
      setUsers((prev) => prev.filter((x) => x.id !== u.id));
    });
  };

  return (
    <section>
      {temp && <TempPasswordNotice {...temp} onDismiss={() => setTemp(null)} />}

      <form className="admin-card admin-row add-user" onSubmit={addUser}>
        <input
          className="grow"
          type="email"
          placeholder="New user's email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="staff">Staff — inventory only</option>
          <option value="owner">Owner — everything</option>
        </select>
        <button className="btn btn-primary" disabled={busy}>
          Add user
        </button>
      </form>

      {error && <div className="admin-error">{error}</div>}

      <div className="admin-card admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isMe = u.id === me.id;
              return (
                <tr key={u.id}>
                  <td className="cell-strong">
                    {u.email} {isMe && <span className="admin-muted">(you)</span>}
                  </td>
                  <td>
                    {isMe ? (
                      u.role
                    ) : (
                      <select value={u.role} onChange={(e) => changeRole(u, e.target.value)} disabled={busy}>
                        <option value="staff">staff</option>
                        <option value="owner">owner</option>
                      </select>
                    )}
                  </td>
                  <td className="admin-muted">
                    {u.must_change_password ? "Hasn't set a password yet" : "Active"}
                  </td>
                  <td className="actions">
                    {!isMe && (
                      <>
                        <button className="btn" onClick={() => resetPassword(u)} disabled={busy}>
                          Reset password
                        </button>
                        <button className="btn btn-danger" onClick={() => removeUser(u)} disabled={busy}>
                          Remove
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="admin-hint">
        Owners can manage users and edit Siq's and Bucks's personas. Staff can manage inventory.
      </p>
    </section>
  );
}
