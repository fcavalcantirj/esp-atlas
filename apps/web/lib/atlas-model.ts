import type { Firmware, PartRecord, Recipe } from "./api.ts";

export interface AtlasCatalog {
  parts: PartRecord[];
  firmware: Firmware[];
  recipes: Recipe[];
}

export interface AtlasNode {
  key: string;
  id: string;
  kind: "soc" | "module" | "board" | "firmware";
  name: string;
  part?: PartRecord;
  firmware?: Firmware;
}

export interface AtlasEdge {
  key: string;
  from: string;
  to: string;
  kind: "lineage" | "recipe";
  recipe?: Recipe;
}

export interface AtlasGap {
  kind: "missing-reference" | "invalid-reference" | "unsupported-part-type" | "duplicate-record";
  recordId: string;
  referenceId?: string;
  message: string;
}

export interface AtlasModel {
  catalog: AtlasCatalog;
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  gaps: AtlasGap[];
  nodesByKey: Map<string, AtlasNode>;
  partsById: Map<string, PartRecord>;
  firmwareById: Map<string, Firmware>;
  recipesById: Map<string, Recipe>;
  recipesByBoard: Map<string, Recipe[]>;
  recipesByFirmware: Map<string, Recipe[]>;
}

function indexRecords<T extends { id: string }>(records: T[], label: string, gaps: AtlasGap[]): Map<string, T> {
  const index = new Map<string, T>();
  for (const record of records) {
    if (index.has(record.id)) {
      gaps.push({ kind: "duplicate-record", recordId: record.id, message: `Duplicate ${label} ID: ${record.id}.` });
    } else index.set(record.id, record);
  }
  return index;
}

function append(index: Map<string, Recipe[]>, id: string, recipe: Recipe) {
  const recipes = index.get(id);
  if (recipes) recipes.push(recipe);
  else index.set(id, [recipe]);
}

/** A graph of recorded relationships, not a compatibility prediction. Records
 * remain intact so a consumer can show the exact notes, sources and trust tier. */
export function buildAtlasModel(catalog: AtlasCatalog): AtlasModel {
  const nodes: AtlasNode[] = [];
  const edges: AtlasEdge[] = [];
  const gaps: AtlasGap[] = [];
  const partsById = indexRecords(catalog.parts, "part", gaps);
  const firmwareById = indexRecords(catalog.firmware, "firmware", gaps);
  const recipesById = indexRecords(catalog.recipes, "recipe", gaps);
  const recipesByBoard = new Map<string, Recipe[]>();
  const recipesByFirmware = new Map<string, Recipe[]>();

  for (const part of partsById.values()) {
    if (part.type !== "soc" && part.type !== "module" && part.type !== "board") {
      gaps.push({ kind: "unsupported-part-type", recordId: part.id, message: `Part ${part.id} has unsupported type ${part.type}.` });
      continue;
    }
    nodes.push({ key: `part:${part.id}`, id: part.id, kind: part.type, name: part.name, part });
  }
  for (const firmware of firmwareById.values()) {
    nodes.push({ key: `firmware:${firmware.id}`, id: firmware.id, kind: "firmware", name: firmware.name, firmware });
  }
  const nodesByKey = new Map(nodes.map((node) => [node.key, node]));

  function reference(recordId: string, id: string | null, kind: AtlasNode["kind"]): AtlasNode | null {
    const node = id ? nodesByKey.get(`${kind === "firmware" ? "firmware" : "part"}:${id}`) : undefined;
    if (!node) {
      gaps.push({ kind: "missing-reference", recordId, ...(id ? { referenceId: id } : {}),
        message: `${recordId} references ${id ? `missing ${kind} ${id}` : `no ${kind} record`}.` });
      return null;
    }
    if (node.kind !== kind) {
      gaps.push({ kind: "invalid-reference", recordId, referenceId: id ?? undefined,
        message: `${recordId} references ${node.id} as ${kind}, but its type is ${node.kind}.` });
      return null;
    }
    return node;
  }

  for (const node of nodes) {
    const part = node.part;
    if (!part || node.kind === "soc") continue;
    // The API resolves a board's inherited soc_ref even when it has a module.
    // Draw its direct parent only; module self refs and SoC self refs are metadata.
    const usesModule = node.kind === "board" && part.module_ref !== null;
    const parent = reference(part.id, usesModule ? part.module_ref : part.soc_ref, usesModule ? "module" : "soc");
    if (parent) edges.push({ key: `lineage:${JSON.stringify([parent.key, node.key])}`,
      from: parent.key, to: node.key, kind: "lineage" });
  }

  for (const recipe of recipesById.values()) {
    append(recipesByBoard, recipe.board, recipe);
    append(recipesByFirmware, recipe.firmware, recipe);
    const board = reference(recipe.id, recipe.board, "board");
    const firmware = reference(recipe.id, recipe.firmware, "firmware");
    if (board && firmware) edges.push({ key: `recipe:${recipe.id}`, from: board.key, to: firmware.key, kind: "recipe", recipe });
  }

  return { catalog, nodes, edges, gaps, nodesByKey, partsById, firmwareById, recipesById, recipesByBoard, recipesByFirmware };
}

/** Selection must agree on the recipe ID and both recorded endpoints. */
export function exactRecipe(catalog: AtlasCatalog, recipeId: string, boardId: string, firmwareId: string): Recipe | null {
  return catalog.recipes.find((recipe) => recipe.id === recipeId && recipe.board === boardId && recipe.firmware === firmwareId) ?? null;
}
