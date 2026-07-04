export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "brand compact" : "brand"} aria-label="家計簿">
      <span className="brand-mark">
        <i />
        <b />
      </span>
      {!compact && <span className="brand-text">Household Ledger</span>}
    </div>
  );
}
