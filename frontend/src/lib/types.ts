import type { components, paths } from "./api-types";

export type Schemas = components["schemas"];
export type ApiPaths = paths;

export type Account = Schemas["AccountResponse"];
export type AccountTenant = Account["tenants"][number];
export type CurrentTenant = Schemas["CurrentTenantResponse"];
export type Customer = Schemas["Customer"];
export type Contact = Schemas["Contact"];
export type Site = Schemas["Site"];
export type EquipmentCategory = Schemas["EquipmentCategory"];
export type EquipmentModel = Schemas["EquipmentModel"];
export type Location = Schemas["Location"];
export type Asset = Schemas["Asset"];
export type AssetStatusEvent = Schemas["AssetStatusEvent"];
export type RatePlan = Schemas["RatePlan"];
export type RateComponent = Schemas["RateComponent"];
export type Quote = Schemas["Quote"];
export type QuoteLine = Schemas["QuoteLine"];
export type RentalOrder = Schemas["RentalOrder"];
export type RentalLine = Schemas["RentalLine"];
export type ReservationAllocation = Schemas["ReservationAllocation"];
export type Contract = Schemas["Contract"];
export type Invoice = Schemas["Invoice"];
export type InvoiceLine = Schemas["InvoiceLine"];
export type Payment = Schemas["Payment"];
export type Deposit = Schemas["Deposit"];
export type ImportBatch = Schemas["ImportBatch"];
export type ImportRow = Schemas["ImportRow"];
export type BillingReport = Schemas["BillingReport"];
export type FleetReport = Schemas["FleetReport"];
export type RentalReport = Schemas["RentalReport"];
export type TransportJob = Schemas["TransportJob"];
export type TransportJobAsset = Schemas["TransportJobAsset"];
export type AssetLogisticsEvent = Schemas["AssetLogisticsEvent"];
export type DeliveryReceipt = Schemas["DeliveryReceipt"];
export type InventoryCount = Schemas["InventoryCount"];
export type InventoryCountLine = Schemas["InventoryCountLine"];
export type LogisticsAttachment = Schemas["LogisticsAttachment"];
export type MobileLogisticsSummary = Schemas["MobileLogisticsSummary"];

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
