// schema.org graphs for the pages that are server-rendered from data the API
// already returns. No offers, prices, ratings or reviews anywhere: the site is
// not a shop and `price_tier` is editorial (see SPEC.md anti-goals).
import type { BrandFacet, Firmware, PartDetail, PartRecord } from "@/lib/api";
import { brandLabel } from "@/lib/brand";
import { faqPage } from "@/lib/faq";
import { firstSentence, typeLabel, typePlural } from "@/lib/format";
import { typeIndexPath } from "@/lib/routes";
import { dataFolderUrl, repoUrl } from "@/lib/github";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

const CONTEXT = "https://schema.org";
const ORG_ID = `${SITE_URL}/#organization`;
const SITE_ID = `${SITE_URL}/#website`;
const DATASET_ID = `${SITE_URL}/#dataset`;
const CC_BY_SA = "https://creativecommons.org/licenses/by-sa/4.0/";

function organization() {
  return {
    "@type": "Organization",
    "@id": ORG_ID,
    name: SITE_NAME,
    url: SITE_URL,
    logo: `${SITE_URL}/icon.svg`,
    sameAs: [repoUrl()],
  };
}

function website() {
  return {
    "@type": "WebSite",
    "@id": SITE_ID,
    name: SITE_NAME,
    url: SITE_URL,
    description: SITE_DESCRIPTION,
    inLanguage: "en",
    publisher: { "@id": ORG_ID },
  };
}

function dataset() {
  return {
    "@type": "Dataset",
    "@id": DATASET_ID,
    name: "esp-atlas — ESP32 SoCs, modules and dev boards",
    description:
      "Datasheet-cited records for the Espressif ESP32 family: SoCs, modules and development boards, " +
      "each with radios, USB, form factor, dimensions, power and per-field source citations. " +
      "Stored as markdown with YAML frontmatter, validated against JSON Schema, queryable through a public API.",
    url: SITE_URL,
    license: CC_BY_SA,
    isAccessibleForFree: true,
    inLanguage: "en",
    keywords: ["ESP32", "ESP32-S3", "ESP32-C3", "ESP32-C6", "Espressif", "development boards", "modules", "SoC", "datasheet", "Wi-Fi", "Bluetooth LE", "Zigbee", "Thread", "Matter"],
    creator: { "@id": ORG_ID },
    distribution: [
      { "@type": "DataDownload", encodingFormat: "text/markdown", contentUrl: dataFolderUrl() },
      { "@type": "DataDownload", encodingFormat: "application/json", contentUrl: `${SITE_URL}/api/parts` },
    ],
  };
}

/** Home page: the site, its publisher and the open dataset behind it. */
/** /how-we-work: the project's own account of itself, as an AboutPage. */
export function howWeWorkGraph(description: string) {
  const url = `${SITE_URL}/how-we-work`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      { "@type": "AboutPage", "@id": url, name: "How esp-atlas works", url, description, isPartOf: { "@id": SITE_ID }, about: { "@id": ORG_ID } },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "How we work" },
        ],
      },
    ],
  };
}

export function homeGraph() {
  return { "@context": CONTEXT, "@graph": [organization(), website(), dataset()] };
}

/** /brands: the list of every vendor/brand in the dataset, as a CollectionPage + ItemList. */
export function brandsIndexGraph(brands: BrandFacet[]) {
  const url = `${SITE_URL}/brands`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      {
        "@type": "CollectionPage",
        "@id": url,
        name: "ESP32 boards and modules by brand",
        url,
        isPartOf: { "@id": SITE_ID },
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: brands.length,
          itemListElement: brands.map((b, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: b.display_name,
            url: `${url}/${encodeURIComponent(b.value)}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "Brands" },
        ],
      },
    ],
  };
}

/** /brands/<slug>: every part the core returns for the brand, as a CollectionPage + ItemList. */
export function brandGraph(slug: string, name: string, parts: PartRecord[]) {
  const url = `${SITE_URL}/brands/${encodeURIComponent(slug)}`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      {
        "@type": "CollectionPage",
        "@id": url,
        name: `${name} — ESP32 boards and modules`,
        url,
        isPartOf: { "@id": SITE_ID },
        about: { "@type": "Brand", name },
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: parts.length,
          itemListElement: parts.map((p, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: p.name,
            url: `${SITE_URL}/parts/${encodeURIComponent(p.id)}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "Brands", item: `${SITE_URL}/brands` },
          { "@type": "ListItem", position: 3, name },
        ],
      },
    ],
  };
}

/** /firmware: every flashable firmware project in the dataset, as a CollectionPage + ItemList. */
export function firmwareIndexGraph(firmware: Firmware[]) {
  const url = `${SITE_URL}/firmware`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      {
        "@type": "CollectionPage",
        "@id": url,
        name: "ESP32 firmware — what runs on what",
        url,
        isPartOf: { "@id": SITE_ID },
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: firmware.length,
          itemListElement: firmware.map((fw, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: fw.name,
            url: `${url}/${encodeURIComponent(fw.id)}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "Firmware" },
        ],
      },
    ],
  };
}

/** /firmware/<id>: the firmware itself plus every board it's a recipe for, as a SoftwareApplication + ItemList. */
export function firmwareGraph(firmware: Firmware, boards: PartRecord[]) {
  const url = `${SITE_URL}/firmware/${encodeURIComponent(firmware.id)}`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      {
        "@type": "SoftwareApplication",
        "@id": `${url}#software`,
        name: firmware.name,
        url,
        sameAs: firmware.url,
        applicationCategory: firmware.category,
        ...(firmware.license ? { license: firmware.license } : {}),
        ...(firmware.maintainer ? { author: { "@type": "Person", name: firmware.maintainer } } : {}),
        isPartOf: { "@id": SITE_ID },
      },
      ...(boards.length
        ? [
            {
              "@type": "ItemList",
              "@id": `${url}#boards`,
              name: `Boards ${firmware.name} runs on`,
              numberOfItems: boards.length,
              itemListElement: boards.map((b, i) => ({
                "@type": "ListItem",
                position: i + 1,
                name: b.name,
                url: `${SITE_URL}/parts/${encodeURIComponent(b.id)}`,
              })),
            },
          ]
        : []),
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "Firmware", item: `${SITE_URL}/firmware` },
          { "@type": "ListItem", position: 3, name: firmware.name },
        ],
      },
    ],
  };
}

/** A typed index (/boards, /modules, /socs): the list as a CollectionPage, mirroring /brands. */
export function partTypeIndexGraph(type: string, name: string, path: string, parts: PartRecord[]) {
  const url = `${SITE_URL}${path}`;
  return {
    "@context": CONTEXT,
    "@graph": [
      organization(),
      website(),
      {
        "@type": "CollectionPage",
        "@id": url,
        name,
        url,
        isPartOf: { "@id": SITE_ID },
        mainEntity: {
          "@type": "ItemList",
          numberOfItems: parts.length,
          itemListElement: parts.map((p, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: p.name,
            url: `${SITE_URL}/parts/${encodeURIComponent(p.id)}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: typePlural(type) },
        ],
      },
    ],
  };
}

/**
 * Part page: a cited technical reference article about one part, plus the
 * breadcrumb trail that is visible on the page (Home › Boards › part — every
 * ancestor crumb is a link, and BreadcrumbList must mirror what users see).
 */
export function partGraph(part: PartDetail) {
  const url = `${SITE_URL}/parts/${encodeURIComponent(part.id)}`;
  const verified = part.sources.map((s) => s.verified).filter(Boolean).sort();
  const citation = Array.from(new Set(part.sources.map((s) => s.url).filter(Boolean)));
  const description = firstSentence(part.body) || `${part.name}: datasheet-verified ESP32 ${part.type} specs on ${SITE_NAME}.`;

  const article = {
    "@type": "TechArticle",
    "@id": `${url}#article`,
    headline: part.name,
    description,
    url,
    mainEntityOfPage: url,
    inLanguage: "en",
    image: `${url}/opengraph-image`,
    license: CC_BY_SA,
    isPartOf: { "@id": SITE_ID },
    author: { "@id": ORG_ID },
    publisher: { "@id": ORG_ID },
    ...(verified.length ? { dateModified: verified[verified.length - 1] } : {}),
    ...(citation.length ? { citation } : {}),
    about: {
      "@type": "Product",
      name: part.name,
      brand: { "@type": "Brand", name: brandLabel(part) },
      manufacturer: { "@type": "Organization", name: brandLabel(part) },
      category: `ESP32 ${typeLabel(part.type)}`,
    },
  };

  const indexPath = typeIndexPath(part.type);
  const breadcrumb = {
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
      ...(indexPath ? [{ "@type": "ListItem", position: 2, name: typePlural(part.type), item: `${SITE_URL}${indexPath}` }] : []),
      { "@type": "ListItem", position: indexPath ? 3 : 2, name: part.name },
    ],
  };

  // A SoC page lists every module and board built on the chip (the visible
  // "Boards and modules on …" section); the same list as an ItemList.
  const hub =
    part.type === "soc" && part.related.length > 0
      ? [
          {
            "@type": "ItemList",
            "@id": `${url}#parts`,
            name: `Boards and modules on ${part.name}`,
            numberOfItems: part.related.length,
            itemListElement: part.related.map((r, i) => ({
              "@type": "ListItem",
              position: i + 1,
              name: r.name,
              url: `${SITE_URL}/parts/${encodeURIComponent(r.id)}`,
            })),
          },
        ]
      : [];

  const faq = part.type === "soc" && part.faq.length > 0 ? [faqPage(url, part.faq)] : [];

  return { "@context": CONTEXT, "@graph": [organization(), website(), article, breadcrumb, ...hub, ...faq] };
}
