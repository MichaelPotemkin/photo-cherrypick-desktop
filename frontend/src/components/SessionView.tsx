import { useCallback, useMemo, useRef, useState } from "react";
import {
  type DecisionAction,
  type Group,
  type GroupsResponse,
  type ViewMode,
} from "../api";
import { exportWithCheck } from "../lib/exportWithCheck";
import { useDecision } from "../useDecision";
import { useSessionData } from "../useSessionData";
import { useI18n } from "../i18n";
import { useKeyboard, type ClosedHandlers, type OpenHandlers } from "../useKeyboard";
import Progress from "./Progress";
import CountsHeader from "./CountsHeader";
import GroupGrid from "./GroupGrid";
import FeedView from "./FeedView";
import Lightbox from "./Lightbox";
import ErrorState from "./ErrorState";

interface Props {
  sessionId: string;
  onHome: () => void;
}

// A flat, ordered entry for keyboard navigation across visible cards.
interface FlatEntry {
  photoId: string;
  groupIdx: number;
}

export default function SessionView({ sessionId, onHome }: Props) {
  const { t } = useI18n();
  // View mode: "burst" (cull pass), "scene" (gallery-grouping pass), or "feed" (planned grid of
  // favorites). Part of the query key so toggling refetches the right shape; "feed" renders its own
  // component and does not use the groups query.
  const [mode, setMode] = useState<ViewMode>("burst");
  const groupMode = mode === "feed" ? "burst" : mode;
  const groupsKey = useMemo(
    () => ["groups", sessionId, groupMode] as const,
    [sessionId, groupMode],
  );

  // Data layer (session poll + ready-gated groups query + rename/accept mutations) lives in a hook so
  // this component is left with UI state + layout (#80).
  const { sessionQuery, status, ready, groupsQuery, renameMut, acceptMut } = useSessionData(
    sessionId,
    groupMode,
    groupsKey,
  );

  const decide = useDecision(groupsKey);

  // --- UI state ----------------------------------------------------------
  const [hideSorted, setHideSorted] = useState(false);
  const [selectedPhotoId, setSelectedPhotoId] = useState<string | null>(null);
  // Lightbox state: which group + index within that group. (Zoom is a hover interaction
  // handled locally inside the Lightbox.)
  const [lightbox, setLightbox] = useState<{ groupIdx: number; index: number } | null>(
    null,
  );

  // Switching mode renumbers groups, so drop any open lightbox / selection that points into the
  // old layout.
  const changeMode = useCallback(
    (next: ViewMode) => {
      if (next === mode) return;
      setLightbox(null);
      setSelectedPhotoId(null);
      setMode(next);
    },
    [mode],
  );

  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const registerCard = useCallback((photoId: string, el: HTMLDivElement | null) => {
    if (el) cardRefs.current.set(photoId, el);
    else cardRefs.current.delete(photoId);
  }, []);

  const data: GroupsResponse | undefined = groupsQuery.data;

  // Undecided best-of-burst suggestions (drives the "Accept picks (N)" button). Comes from the
  // server (always the burst-suggested count) so it matches what Accept does, even in scene/feed view.
  const nSuggestions = data?.session.n_suggestions ?? 0;

  // Current state of a photo by id (for toggle behaviour).
  const photoState = useCallback(
    (photoId: string): DecisionAction | "none" => {
      for (const g of data?.groups ?? []) {
        const p = g.photos.find((ph) => ph.id === photoId);
        if (p) return p.state;
      }
      return "none";
    },
    [data],
  );

  // Toggle a decision: pressing the key for the already-applied state clears it (→ undo).
  const toggleDecide = useCallback(
    (photoId: string, action: "favorite" | "maybe" | "delete") => {
      decide(photoId, photoState(photoId) === action ? "undo" : action);
    },
    [decide, photoState],
  );

  // Visible groups after applying the hide-sorted filter.
  const visibleGroups: Group[] = useMemo(() => {
    if (!data) return [];
    if (!hideSorted) return data.groups;
    return data.groups
      .map((g) => ({
        ...g,
        photos: g.photos.filter((p) => p.state === "none"),
      }))
      .filter((g) => g.photos.length > 0);
  }, [data, hideSorted]);

  // Flat list of visible cards in display order (for arrow navigation).
  const flat: FlatEntry[] = useMemo(() => {
    const out: FlatEntry[] = [];
    for (const g of visibleGroups) {
      for (const p of g.photos) out.push({ photoId: p.id, groupIdx: g.idx });
    }
    return out;
  }, [visibleGroups]);

  // Lookup helpers (by full data, not just visible — lightbox keeps showing a
  // photo even if it would be hidden by the filter after a decision).
  const groupByIdx = useCallback(
    (idx: number): Group | undefined => data?.groups.find((g) => g.idx === idx),
    [data],
  );

  function selectIndex(i: number) {
    if (flat.length === 0) return;
    const clamped = Math.max(0, Math.min(flat.length - 1, i));
    const entry = flat[clamped];
    setSelectedPhotoId(entry.photoId);
    const el = cardRefs.current.get(entry.photoId);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  const selectedFlatIndex = useMemo(
    () => flat.findIndex((e) => e.photoId === selectedPhotoId),
    [flat, selectedPhotoId],
  );

  // --- Lightbox open/navigation -----------------------------------------
  const openLightbox = useCallback(
    (groupIdx: number, photoId: string) => {
      const g = groupByIdx(groupIdx);
      if (!g) return;
      const index = g.photos.findIndex((p) => p.id === photoId);
      if (index < 0) return;
      setSelectedPhotoId(photoId);
      setLightbox({ groupIdx, index });
    },
    [groupByIdx],
  );

  function closeLightbox() {
    setLightbox(null);
  }

  function lightboxMove(delta: number) {
    setLightbox((lb) => {
      if (!lb) return lb;
      const g = groupByIdx(lb.groupIdx);
      if (!g) return lb;
      const next = Math.max(0, Math.min(g.photos.length - 1, lb.index + delta));
      setSelectedPhotoId(g.photos[next].id);
      return { ...lb, index: next };
    });
  }

  function lightboxJump(index: number) {
    setLightbox((lb) => {
      if (!lb) return lb;
      const g = groupByIdx(lb.groupIdx);
      if (!g) return lb;
      setSelectedPhotoId(g.photos[index]?.id ?? null);
      return { ...lb, index };
    });
  }

  // Jump the lightbox to the adjacent group, opening that group's suggested (or first) photo.
  const lightboxGroupMove = useCallback(
    (delta: number) => {
      if (!data || !lightbox) return;
      const groups = data.groups;
      const pos = groups.findIndex((g) => g.idx === lightbox.groupIdx);
      if (pos < 0) return;
      const np = Math.max(0, Math.min(groups.length - 1, pos + delta));
      const g = groups[np];
      const si = Math.max(0, g.photos.findIndex((p) => p.suggested));
      setSelectedPhotoId(g.photos[si].id);
      setLightbox({ groupIdx: g.idx, index: si });
    },
    [data, lightbox],
  );

  // In the grid, move the selection to the next/prev group's suggested (or first) photo.
  const selectGroupMove = useCallback(
    (delta: number) => {
      if (visibleGroups.length === 0) return;
      let pos = selectedPhotoId
        ? visibleGroups.findIndex((g) => g.photos.some((p) => p.id === selectedPhotoId))
        : 0;
      if (pos < 0) pos = 0;
      const np = Math.max(0, Math.min(visibleGroups.length - 1, pos + delta));
      const g = visibleGroups[np];
      const target = g.photos.find((p) => p.suggested) ?? g.photos[0];
      setSelectedPhotoId(target.id);
      cardRefs.current.get(target.id)?.scrollIntoView({ block: "start", behavior: "smooth" });
    },
    [visibleGroups, selectedPhotoId],
  );

  const currentLightboxPhotoId = useMemo(() => {
    if (!lightbox) return null;
    const g = groupByIdx(lightbox.groupIdx);
    return g?.photos[lightbox.index]?.id ?? null;
  }, [lightbox, groupByIdx]);

  // --- Keyboard handlers -------------------------------------------------
  const closedHandlers: ClosedHandlers = useMemo(
    () => ({
      onLeft: () => selectIndex((selectedFlatIndex < 0 ? 0 : selectedFlatIndex) - 1),
      onRight: () => selectIndex(selectedFlatIndex < 0 ? 0 : selectedFlatIndex + 1),
      onPrevGroup: () => selectGroupMove(-1),
      onNextGroup: () => selectGroupMove(1),
      onFavorite: () => selectedPhotoId != null && toggleDecide(selectedPhotoId, "favorite"),
      onMaybe: () => selectedPhotoId != null && toggleDecide(selectedPhotoId, "maybe"),
      onDelete: () => selectedPhotoId != null && toggleDecide(selectedPhotoId, "delete"),
      onUndo: () => selectedPhotoId != null && decide(selectedPhotoId, "undo"),
      onAcceptSuggestion: () => {
        // Favorite the suggested photo of the selected card's group.
        if (selectedFlatIndex < 0) return;
        const entry = flat[selectedFlatIndex];
        const g = groupByIdx(entry.groupIdx);
        const suggested = g?.photos.find((p) => p.suggested);
        if (suggested) decide(suggested.id, "favorite");
      },
      onNextUndecided: () => {
        // Jump selection to the next visible photo with state "none".
        const start = selectedFlatIndex < 0 ? -1 : selectedFlatIndex;
        for (let i = 1; i <= flat.length; i++) {
          const idx = (start + i) % flat.length;
          const g = groupByIdx(flat[idx].groupIdx);
          const p = g?.photos.find((ph) => ph.id === flat[idx].photoId);
          if (p?.state === "none") {
            selectIndex(idx);
            return;
          }
        }
      },
      onOpen: () => {
        if (selectedFlatIndex < 0) return;
        const entry = flat[selectedFlatIndex];
        openLightbox(entry.groupIdx, entry.photoId);
      },
      onToggleHide: () => setHideSorted((v) => !v),
    }),
    [selectedFlatIndex, selectedPhotoId, flat, groupByIdx, decide, toggleDecide, openLightbox, selectGroupMove],
  );

  const openHandlers: OpenHandlers = useMemo(
    () => ({
      onLeft: () => lightboxMove(-1),
      onRight: () => lightboxMove(1),
      onPrevGroup: () => lightboxGroupMove(-1),
      onNextGroup: () => lightboxGroupMove(1),
      onFavorite: () =>
        currentLightboxPhotoId != null && toggleDecide(currentLightboxPhotoId, "favorite"),
      onMaybe: () =>
        currentLightboxPhotoId != null && toggleDecide(currentLightboxPhotoId, "maybe"),
      onDelete: () =>
        currentLightboxPhotoId != null && toggleDecide(currentLightboxPhotoId, "delete"),
      onUndo: () =>
        currentLightboxPhotoId != null && decide(currentLightboxPhotoId, "undo"),
      onClose: closeLightbox,
    }),
    [currentLightboxPhotoId, decide, toggleDecide, lightboxGroupMove],
  );

  useKeyboard({
    lightboxOpen: lightbox != null,
    closed: closedHandlers,
    open: openHandlers,
    active: mode !== "feed",
  });

  // --- Render ------------------------------------------------------------
  if (sessionQuery.isError) {
    return (
      <ErrorState
        title={t("failed_load_session")}
        detail={(sessionQuery.error as Error)?.message}
        onRetry={() => sessionQuery.refetch()}
        action={{ label: t("back_new_session"), onClick: onHome }}
      />
    );
  }

  if (!sessionQuery.data) {
    return <div className="centered muted">{t("loading")}</div>;
  }

  if (status === "error") {
    return (
      <ErrorState
        title={t("analysis_failed")}
        detail={sessionQuery.data.error ?? t("unknown_error")}
        action={{ label: t("back_new_session"), onClick: onHome }}
      />
    );
  }

  if (!ready) {
    return <Progress session={sessionQuery.data} />;
  }

  if (groupsQuery.isLoading || !data) {
    return <div className="centered muted">{t("loading_groups")}</div>;
  }

  if (groupsQuery.isError) {
    return (
      <ErrorState
        title={t("failed_load_groups")}
        detail={(groupsQuery.error as Error)?.message}
        onRetry={() => groupsQuery.refetch()}
        action={{ label: t("back_new_session"), onClick: onHome }}
      />
    );
  }

  const lightboxGroup = lightbox ? groupByIdx(lightbox.groupIdx) : undefined;

  return (
    <div className="session-view">
      <CountsHeader
        title={data.session.title}
        nTotal={data.session.n_total}
        nGroups={data.groups.length}
        counts={data.session.counts}
        mode={mode}
        onSetMode={changeMode}
        hideSorted={hideSorted}
        onToggleHide={() => setHideSorted((v) => !v)}
        onExportZip={() => exportWithCheck(sessionId, "zip", t("export_none_found"))}
        nSuggestions={nSuggestions}
        onAcceptSuggestions={() => acceptMut.mutate()}
        onRename={(title) => renameMut.mutate(title)}
        onHome={onHome}
      />

      <main className="session-main">
        {mode === "feed" ? (
          <FeedView sessionId={sessionId} />
        ) : (
          <GroupGrid
            groups={visibleGroups}
            mode={mode}
            selectedPhotoId={selectedPhotoId}
            registerCard={registerCard}
            onOpen={openLightbox}
            onDecide={(photoId: string, action: DecisionAction) => decide(photoId, action)}
          />
        )}
      </main>

      {lightbox && lightboxGroup && (
        <Lightbox
          group={lightboxGroup}
          mode={mode}
          index={lightbox.index}
          groupNumber={data.groups.findIndex((g) => g.idx === lightbox.groupIdx) + 1}
          groupCount={data.groups.length}
          onClose={closeLightbox}
          onPrev={() => lightboxMove(-1)}
          onNext={() => lightboxMove(1)}
          onPrevGroup={() => lightboxGroupMove(-1)}
          onNextGroup={() => lightboxGroupMove(1)}
          onJump={lightboxJump}
          onDecide={(action: DecisionAction) =>
            currentLightboxPhotoId != null && decide(currentLightboxPhotoId, action)
          }
        />
      )}
    </div>
  );
}
