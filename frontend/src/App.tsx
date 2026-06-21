import { useEffect, useState } from "react";
import SessionInput from "./components/SessionInput";
import SessionView from "./components/SessionView";
import UpdateFooter from "./components/UpdateFooter";
import { parseSessionId } from "./lib/routing";

// Clean-URL routing via the History API: "/" is the input screen, "/session/<id>" a
// session view. Deep links / refresh work because the static server (Vite dev and
// `serve -s` in prod) serves index.html for any path; React reads the path on mount.
function readSessionFromPath(): string | null {
  return parseSessionId(window.location.pathname);
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(
    readSessionFromPath(),
  );

  // keep routing in sync with browser back/forward
  useEffect(() => {
    const onPop = () => setSessionId(readSessionFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function openSession(id: string) {
    window.history.pushState({}, "", `/session/${id}`);
    setSessionId(id);
  }

  function goHome() {
    window.history.pushState({}, "", "/");
    setSessionId(null);
  }

  return (
    <div className="app">
      {sessionId == null ? (
        <SessionInput onOpen={openSession} />
      ) : (
        <SessionView sessionId={sessionId} onHome={goHome} />
      )}
      {/* Version + auto-update UI lives on the welcome screen only — it's clutter inside a shoot.
          The hook re-subscribes and replays the latest update state on remount (via `spa-ready`),
          so anything that completed during a session re-surfaces when you return home. */}
      {sessionId == null && <UpdateFooter />}
    </div>
  );
}
