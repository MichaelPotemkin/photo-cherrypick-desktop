import { useQuery } from "@tanstack/react-query";
import { getFeed, type FeedPhoto } from "../api";
import { useI18n } from "../i18n";

interface Props {
  sessionId: string;
}

// The feed-layout planner view: the favorites arranged into a balanced 3-wide gallery grid
// (alternating shot scale, scenes spread out). Read-only — it's a planning aid for posting.
export default function FeedView({ sessionId }: Props) {
  const { t } = useI18n();
  const query = useQuery({
    queryKey: ["feed", sessionId],
    queryFn: () => getFeed(sessionId),
  });

  if (query.isLoading) return <div className="centered muted">{t("feed_planning")}</div>;
  if (query.isError)
    return (
      <div className="centered error">
        {(query.error as Error)?.message ?? t("feed_failed")}
      </div>
    );

  const photos = query.data?.photos ?? [];
  if (photos.length === 0)
    return (
      <div className="empty-state muted">
        {t("feed_empty_pre")}
        <strong>{t("feed_empty_strong")}</strong>
        {t("feed_empty_post")}
      </div>
    );

  return (
    <div className="feed-wrap">
      <p className="feed-hint muted small">{t("feed_hint", { n: photos.length })}</p>
      <div className="feed-grid">
        {photos.map((p: FeedPhoto) => (
          <div
            className={`feed-tile feed-${p.scale}`}
            key={p.id}
            title={`#${p.slot} · ${t(`scale:${p.scale}`)} · ${p.filename}`}
          >
            <img src={p.preview_url} alt={p.filename} loading="lazy" />
            <span className="feed-slot">{p.slot}</span>
            <span className="feed-scale">{t(`scale:${p.scale}`)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
