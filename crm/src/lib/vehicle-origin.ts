export const vehicleOrigins = ["all", "german", "japanese", "other"] as const;

export type VehicleOrigin = (typeof vehicleOrigins)[number];

export const vehicleOriginLabels: Record<VehicleOrigin, string> = {
  all: "All",
  german: "German",
  japanese: "Japanese",
  other: "Other"
};

export const germanVehicleBrands = [
  "BMW",
  "Mercedes",
  "Mercedes-Benz",
  "Audi",
  "Volkswagen",
  "VW",
  "Porsche",
  "Opel"
] as const;

export const japaneseVehicleBrands = [
  "Toyota",
  "Nissan",
  "Mazda",
  "Honda",
  "Suzuki",
  "Subaru",
  "Mitsubishi",
  "Lexus",
  "Daihatsu",
  "Isuzu",
  "Infiniti",
  "Hino"
] as const;

export function isVehicleOrigin(value: string): value is VehicleOrigin {
  return vehicleOrigins.includes(value as VehicleOrigin);
}
