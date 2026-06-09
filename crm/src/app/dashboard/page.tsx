import { AutoRefresh } from "@/components/AutoRefresh";
import { Dashboard } from "@/components/Dashboard";
import { getDashboardData } from "@/lib/listings";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function DashboardPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const filters = {
    q: firstParam(params.q),
    status: firstParam(params.status),
    minPrice: firstParam(params.minPrice),
    maxPrice: firstParam(params.maxPrice),
    valuation: firstParam(params.valuation)
  };
  const data = await getDashboardData(filters);

  return (
    <>
      <AutoRefresh />
      <Dashboard filters={filters} listings={data.listings} stats={data.stats} />
    </>
  );
}
