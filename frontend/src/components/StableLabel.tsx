// Keeps a control's width constant when its label changes — across languages (a label can be much
// longer in UK/RU than EN) or across a state toggle (Hide sorted ↔ Show all). The live `text` is
// shown; every string in `reserve` is laid out in the same grid cell but hidden, so the box always
// sizes to the widest. This measures in the real font at runtime, so there are no hardcoded pixel
// widths to drift when a translation — or the system font — changes.
export default function StableLabel({
  text,
  reserve,
}: {
  text: string;
  reserve: string[];
}) {
  return (
    <span className="stable-label">
      <span>{text}</span>
      {reserve.map((r, i) => (
        <span key={i} className="stable-ghost" aria-hidden="true">
          {r}
        </span>
      ))}
    </span>
  );
}
