// Reusable labeled gradient bars. Two variants:
//  - MiniBar: a single thin labeled bar (used in PhotoCard category bars).
//  - AxisGrid: a 2-column grid of labeled bars + numeric value (lightbox axes).
//
// Fill is a left-to-right red->amber->green gradient clipped to value width.
import { useI18n } from "../i18n";

interface MiniBarProps {
  label: string;
  value: number; // 0..1
}

export function MiniBar({ label, value }: MiniBarProps) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="minibar">
      <span className="minibar-label">{label}</span>
      <span className="bar-track">
        <span className="bar-fill" style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}

interface AxisGridProps {
  axes: Record<string, number>;
}

export function AxisGrid({ axes }: AxisGridProps) {
  const { t } = useI18n();
  const entries = Object.entries(axes);
  return (
    <div className="axis-grid">
      {entries.map(([name, value]) => {
        const pct = Math.max(0, Math.min(1, value)) * 100;
        return (
          <div className="axis-row" key={name}>
            <span className="axis-label">{t(`axis:${name}`)}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="axis-value">{Math.round(value * 100)}</span>
          </div>
        );
      })}
    </div>
  );
}
