export function ErpFlagBadge({ flag }: { flag: string }) {
  const styles: Record<string, string> = {
    M: 'bg-[#dbeafe] text-[#1e40af]',
    D: 'bg-[#fef3c7] text-[#92400e]',
    C: 'bg-[#d1fae5] text-[#065f46]',
  }
  return (
    <span
      className={`inline-block min-w-[1.1rem] rounded-[10px] px-[7px] py-px text-center text-[11px] font-bold ${styles[flag] ?? 'bg-[#f1f5f9] text-[#475569]'}`}
    >
      {flag}
    </span>
  )
}
