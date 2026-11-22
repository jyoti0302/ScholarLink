export function ResultSkeleton() {
  return (
    <div className="animate-pulse rounded-lg border border-slate-200 bg-white p-6">
      <div className="h-5 w-1/3 rounded bg-slate-200" />
      <div className="mt-2 h-3 w-1/4 rounded bg-slate-100" />
      <div className="mt-5 h-3 w-full rounded bg-slate-100" />
      <div className="mt-2 h-3 w-5/6 rounded bg-slate-100" />
      <div className="mt-5 h-10 w-full rounded bg-slate-100" />
    </div>
  );
}

export function StatePanel({ title, message, tone = "neutral" }: { title: string; message: string; tone?: "neutral" | "error" }) {
  const cls = tone === "error" ? "border-red-200 bg-red-50 text-red-900" : "border-slate-200 bg-white text-slate-700";
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-lg border p-8 text-center ${cls}`}>
      <h3 className="font-serif text-lg">{title}</h3>
      <p className="mt-2 text-sm">{message}</p>
    </div>
  );
}
