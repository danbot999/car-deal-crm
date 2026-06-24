import Link from "next/link";

type AppNavProps = {
  active: "home" | "dashboard" | "leads" | "admin" | "market-evidence";
};

export function AppNav({ active }: AppNavProps) {
  const linkClass = (tab: AppNavProps["active"]) =>
    `rounded-full px-5 py-3 text-sm font-bold transition ${
      active === tab
        ? "bg-slate-950 text-white shadow-lg shadow-slate-300/60"
        : "bg-white/80 text-slate-600 hover:bg-white hover:text-slate-950"
    }`;

  return (
    <nav className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-cyan-700">
          Local CRM
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Marketplace research, valuation, and lead due diligence.
        </p>
      </div>
      <div className="flex rounded-full border border-slate-200 bg-white/60 p-1 shadow-sm shadow-slate-200/70">
        <Link className={linkClass("home")} href="/">
          Home
        </Link>
        <Link className={linkClass("admin")} href="/admin">
          Admin
        </Link>
        <Link className={linkClass("dashboard")} href="/dashboard">
          Dashboard
        </Link>
        <Link className={linkClass("market-evidence")} href="/market-evidence">
          Market Evidence
        </Link>
        <Link className={linkClass("leads")} href="/leads">
          Leads
        </Link>
      </div>
    </nav>
  );
}
