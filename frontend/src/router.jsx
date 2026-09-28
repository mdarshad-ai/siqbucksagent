import { useEffect, useState } from "react";

// A tiny client-side router: "/", "/catalogue" and "/stones/:id". The server
// serves index.html for these paths, so links work when opened directly.
const listeners = new Set();

export function navigate(to, { replace = false } = {}) {
  if (to === window.location.pathname + window.location.search) return;
  window.history[replace ? "replaceState" : "pushState"]({}, "", to);
  listeners.forEach((fn) => fn());
  if (!replace) window.scrollTo(0, 0);
}

export function useLocation() {
  const read = () => ({ path: window.location.pathname, search: window.location.search });
  const [location, setLocation] = useState(read);
  useEffect(() => {
    const update = () => setLocation(read());
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return location;
}

export function matchRoute(path) {
  const clean = path.replace(/\/+$/, "") || "/";
  if (clean === "/catalogue") return { name: "catalogue" };
  const stone = clean.match(/^\/stones\/(\d+)$/);
  if (stone) return { name: "stone", id: Number(stone[1]) };
  return { name: "home" };
}

// An <a> that navigates without reloading (ctrl/cmd-click still opens a tab).
export function Link({ to, onClick, children, ...props }) {
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate(to);
      }}
      {...props}
    >
      {children}
    </a>
  );
}
