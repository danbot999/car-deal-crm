export const flipStatuses = [
  "WATCHING",
  "BOUGHT",
  "IN_REPAIR",
  "LISTED",
  "SOLD",
  "PASSED"
] as const;

export type FlipStatus = (typeof flipStatuses)[number];

export const flipStatusLabels: Record<FlipStatus, string> = {
  WATCHING: "Watching",
  BOUGHT: "Bought",
  IN_REPAIR: "In repair",
  LISTED: "Listed",
  SOLD: "Sold",
  PASSED: "Passed"
};

export const adminPriorities = ["LOW", "MEDIUM", "HIGH"] as const;

export type AdminPriority = (typeof adminPriorities)[number];

export const adminPriorityLabels: Record<AdminPriority, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High"
};

export type AdminStats = {
  carsTracked: number;
  carsBought: number;
  carsSold: number;
  activeInventory: number;
  totalSpentCents: number;
  openCapitalCents: number;
  revenueCents: number;
  realizedProfitCents: number;
  journalCount: number;
};
