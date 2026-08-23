// Shared by the interactive view and its static placeholder.
export const MAX_COMPARE = 6;

export const PRESET_COMPARISONS: { label: string; ids: string[] }[] = [
  { label: "C6 vs H2 (smart-home mesh chips)", ids: ["esp32-c6", "esp32-h2"] },
  { label: "The three XIAOs", ids: ["xiao-esp32c3", "xiao-esp32c6", "xiao-esp32s3"] },
  { label: "S3 vs C3 vs classic ESP32", ids: ["esp32-s3", "esp32-c3", "esp32"] },
];
