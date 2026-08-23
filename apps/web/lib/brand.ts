// A stale/degraded API payload can omit brand_name; vendor_or_brand (the slug)
// is always present, so it is the fallback that keeps the UI from ever
// rendering the literal string "undefined".
export interface BrandLabeled {
  brand_name?: string;
  vendor_or_brand: string;
}

export function brandLabel(part: BrandLabeled): string {
  return part.brand_name || part.vendor_or_brand;
}
