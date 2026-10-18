export function Carregando() {
  return (
    <div aria-busy="true" className="flex flex-col gap-3">
      <span className="sr-only">Carregando…</span>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          aria-hidden="true"
          className="flex gap-3 rounded-xl border border-linha bg-superficie p-3"
        >
          <div className="h-20 w-20 shrink-0 rounded-lg bg-suave motion-safe:animate-pulse" />
          <div className="flex flex-1 flex-col justify-center gap-2">
            <div className="h-4 w-3/4 rounded bg-suave motion-safe:animate-pulse" />
            <div className="h-3 w-1/2 rounded bg-suave motion-safe:animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}
