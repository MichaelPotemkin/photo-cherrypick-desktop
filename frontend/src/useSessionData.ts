import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import {
  acceptSuggestions,
  getGroups,
  getSession,
  renameSession,
  type GroupsResponse,
} from "./api";
import { PROGRESS_POLL_MS } from "./constants";

// The data layer for SessionView (#80): the session-detail poll, the ready-gated groups query, and the
// rename / accept-suggestions mutations with their optimistic update + cache reconciliation. Extracted
// so the view component is left with UI state + layout instead of query plumbing.
export function useSessionData(
  sessionId: string,
  groupMode: "burst" | "scene",
  groupsKey: QueryKey,
) {
  // Poll the session detail until status is ready/error.
  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "ready" || s === "error" ? false : PROGRESS_POLL_MS;
    },
  });
  const status = sessionQuery.data?.status;
  const ready = status === "ready";

  // Groups: only fetched once the session is ready. Kept loaded even in feed mode so the header keeps
  // its counts/title; the feed has its own query.
  const groupsQuery = useQuery({
    queryKey: groupsKey,
    queryFn: () => getGroups(sessionId, groupMode),
    enabled: ready,
  });

  const queryClient = useQueryClient();

  // Rename: optimistic title update, then reconcile both queries.
  const renameMut = useMutation({
    mutationFn: (title: string) => renameSession(sessionId, title),
    onMutate: (title: string) => {
      queryClient.setQueryData<GroupsResponse>(groupsKey, (old) =>
        old ? { ...old, session: { ...old.session, title } } : old,
      );
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: groupsKey });
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });

  // Accept all suggestions: favorite every undecided best-of-burst pick.
  const acceptMut = useMutation({
    mutationFn: () => acceptSuggestions(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: groupsKey });
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });

  return { sessionQuery, status, ready, groupsQuery, renameMut, acceptMut };
}
