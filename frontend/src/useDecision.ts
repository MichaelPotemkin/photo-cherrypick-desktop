import { useCallback, useRef } from "react";
import {
  useMutation,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import {
  postDecision,
  type Counts,
  type DecisionAction,
  type GroupsResponse,
  type Photo,
  type PhotoState,
} from "./api";

// Maps a decision action to the resulting photo state. `undo` clears to "none".
function actionToState(action: DecisionAction): PhotoState {
  return action === "undo" ? "none" : action;
}

// Apply a single state transition as a delta to the authoritative counts. We must NOT recompute
// counts from the cached groups: in scene mode the cache holds only keepers (trashed photos are
// excluded server-side), so a full re-tally would zero out the real trash count. A delta off the
// server's session-wide counts stays correct regardless of which photos the cache contains.
function applyCountDelta(counts: Counts, from: PhotoState, to: PhotoState): Counts {
  if (from === to) return counts;
  const next = { ...counts };
  next[from] = Math.max(0, next[from] - 1);
  next[to] = next[to] + 1;
  return next;
}

interface DecisionVars {
  photoId: string;
  action: DecisionAction;
}

/**
 * Decision mutation with optimistic cache updates of state + counts, plus a
 * per-photo in-flight guard: a second click for a photo that already has a
 * request in flight is ignored.
 *
 * Returns `decide(photoId, action)` — safe to call from cards or the lightbox.
 */
export function useDecision(groupsKey: QueryKey) {
  const qc = useQueryClient();
  // Set of photo ids that currently have an in-flight request.
  const inFlight = useRef<Set<string>>(new Set());

  const mutation = useMutation({
    mutationFn: ({ photoId, action }: DecisionVars) =>
      postDecision(photoId, action),

    onMutate: async ({ photoId, action }: DecisionVars) => {
      // Capture the key at mutate time: the user may switch mode (changing groupsKey) before this
      // settles, and rollback must target the query the snapshot actually came from.
      const key = groupsKey;
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<GroupsResponse>(key);
      const nextState = actionToState(action);

      qc.setQueryData<GroupsResponse>(key, (old) => {
        if (!old) return old;
        let fromState: PhotoState = "none";
        const groups = old.groups.map((g) => ({
          ...g,
          photos: g.photos.map((p: Photo) => {
            if (p.id !== photoId) return p;
            fromState = p.state;
            return { ...p, state: nextState };
          }),
        }));
        return {
          ...old,
          groups,
          session: {
            ...old.session,
            counts: applyCountDelta(old.session.counts, fromState, nextState),
          },
        };
      });

      return { previous, key };
    },

    onError: (_err, _vars, ctx) => {
      // Roll back to the snapshot taken in onMutate, against the same query key.
      if (ctx?.previous) qc.setQueryData(ctx.key, ctx.previous);
    },

    onSettled: (_data, _err, vars, ctx) => {
      inFlight.current.delete(vars.photoId);
      // Reconcile with the server: in scene mode a now-trashed photo must drop out of its cluster
      // (the server excludes it), and counts re-sync. Refetch is cheap (localhost) and react-query
      // dedupes; the optimistic update already gave instant feedback.
      if (ctx?.key) qc.invalidateQueries({ queryKey: ctx.key });
    },
  });

  const decide = useCallback(
    (photoId: string, action: DecisionAction) => {
      // Guard: ignore a click while a request is in flight for this photo.
      if (inFlight.current.has(photoId)) return;
      inFlight.current.add(photoId);
      mutation.mutate({ photoId, action });
    },
    [mutation],
  );

  return decide;
}
