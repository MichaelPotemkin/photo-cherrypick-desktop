import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createSession, deleteSession, listSessions } from "../api";
import type { SessionListItem } from "../api";
import { useI18n, tVariants } from "../i18n";
import { inTauri, pickFolder } from "../lib/tauri";
import HelpButton from "./HelpGuide";
import LangToggle from "./LangToggle";
import StableLabel from "./StableLabel";
import ConfirmModal from "./ConfirmModal";

interface Props {
  onOpen: (id: string) => void;
}

function relTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function folderName(path: string): string {
  const parts = path.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || path;
}

export default function SessionInput({ onOpen }: Props) {
  const { t } = useI18n();
  const [path, setPath] = useState("");
  // Session queued for deletion, surfaced as a confirm popup (null = none).
  const [pendingDelete, setPendingDelete] = useState<SessionListItem | null>(null);

  function statusLabel(s: SessionListItem): string {
    if (s.status === "processing")
      return t("status_analyzing", { done: s.n_done, total: s.n_total });
    if (s.status === "pending") return t("status_queued");
    if (s.status === "error") return t("status_error");
    return t("status_kept_maybe", { fav: s.counts.favorite, maybe: s.counts.maybe });
  }

  const mutation = useMutation({
    mutationFn: (p: string) => createSession(p),
    onSuccess: (data) => onOpen(data.id),
  });

  const queryClient = useQueryClient();
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: listSessions,
    refetchInterval: 4000, // keep processing statuses fresh
  });

  const delMutation = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = path.trim();
    if (!trimmed || mutation.isPending) return;
    mutation.mutate(trimmed);
  }

  async function choose() {
    const picked = await pickFolder();
    if (picked) {
      setPath(picked);
      mutation.mutate(picked); // native dialog → analyze immediately
    }
  }

  const items = sessions.data ?? [];

  return (
    <div className="input-screen">
      <div className="input-card">
        <div className="input-card-top">
          <h1>{t("app_title")}</h1>
          <div className="input-top-actions">
            <HelpButton />
            <LangToggle />
          </div>
        </div>
        <p className="muted">{t("home_tagline")}</p>
        <form onSubmit={submit} className="folder-form">
          <div className="folder-input-row">
            <input
              type="text"
              className="url-input"
              placeholder="/Users/you/Shoots/2026-06-14"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              autoFocus
            />
            {/* Native folder picker (Tauri only — a browser can't read an absolute path).
                Picking a folder analyzes it immediately, so the user never has to type. */}
            {inTauri() && (
              <button
                type="button"
                className="btn browse-btn"
                onClick={choose}
                disabled={mutation.isPending}
                data-tip={t("choose_folder_title")}
              >
                <StableLabel text={t("choose_folder")} reserve={tVariants("choose_folder")} />
              </button>
            )}
          </div>
          <button
            type="submit"
            className="btn btn-accent analyze-btn"
            disabled={mutation.isPending || !path.trim()}
            data-tip={t("analyze_folder_title")}
          >
            {mutation.isPending ? t("analyzing") : t("analyze_folder")}
          </button>
        </form>
        {mutation.isError && (
          <p className="error">
            {(mutation.error as Error)?.message ?? t("failed_create")}
          </p>
        )}

        {items.length > 0 && (
          <div className="session-list">
            <div className="muted small session-list-head">{t("recent_sessions")}</div>
            {items.map((s) => (
              <div key={s.id} className={`session-row status-${s.status}`}>
                <button
                  className="session-row-open"
                  onClick={() => onOpen(s.id)}
                  title={s.source_url}
                >
                  <span className="session-row-main">
                    <span className="session-row-title">
                      {s.title || folderName(s.source_url)}
                    </span>
                    <span className="muted small">
                      {t("n_photos", { n: s.n_total })} · {statusLabel(s)}
                    </span>
                  </span>
                  <span className="muted small session-row-when">
                    {relTime(s.created_at)}
                  </span>
                </button>
                <button
                  className="session-row-del"
                  data-tip={t("delete_session")}
                  aria-label={t("delete_session")}
                  disabled={delMutation.isPending}
                  onClick={() => setPendingDelete(s)}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {pendingDelete && (
        <ConfirmModal
          danger
          message={t("delete_confirm", {
            name: pendingDelete.title || folderName(pendingDelete.source_url),
          })}
          confirmLabel={t("delete_session")}
          cancelLabel={t("cancel")}
          onConfirm={() => {
            delMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
