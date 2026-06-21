import type { DecisionAction, Group, Photo, ViewMode } from "../api";
import { useI18n } from "../i18n";
import { buildGroupLabel } from "../lib/groupLabel";
import PhotoCard from "./PhotoCard";

interface Props {
  groups: Group[];
  mode: ViewMode; // burst | scene (feed renders elsewhere) — picks the localized label wording
  selectedPhotoId: string | null;
  // Register a card's DOM node so the keyboard handler can scroll it into view.
  registerCard: (photoId: string, el: HTMLDivElement | null) => void;
  onOpen: (groupIdx: number, photoId: string) => void;
  onDecide: (photoId: string, action: DecisionAction) => void;
}

export default function GroupGrid({
  groups,
  mode,
  selectedPhotoId,
  registerCard,
  onOpen,
  onDecide,
}: Props) {
  const { t } = useI18n();

  if (groups.length === 0) {
    return <div className="empty-state muted">{t("empty_hidden")}</div>;
  }

  return (
    <div className="group-list">
      {groups.map((group) => (
        <section className="group" key={group.idx}>
          <h3 className="group-header">
            {t("group")} {group.idx + 1} — {buildGroupLabel(t, mode, group.photos.length)}{" "}
            <span className="muted small">{group.when}</span>
            {group.close_call && (
              <span className="close-call-badge" data-tip={t("close_call_title")}>
                {t("close_call")}
              </span>
            )}
          </h3>
          <div className="group-cards">
            {group.photos.map((photo: Photo) => (
              <PhotoCard
                key={photo.id}
                photo={photo}
                selected={photo.id === selectedPhotoId}
                cardRef={(el) => registerCard(photo.id, el)}
                onOpen={() => onOpen(group.idx, photo.id)}
                onDecide={(action) => onDecide(photo.id, action)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
