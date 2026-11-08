import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function luminance(hex: string): number {
  const [r, g, b] = hex.match(/[a-f\d]{2}/gi)!.map((part) => {
    const channel = parseInt(part, 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

test("card popularity and its provenance inherit the accessible theme accent", () => {
  const rule = css.match(/\.popularity-glance\s*\{([^}]+)\}/)![1];
  assert.match(rule, /color:\s*var\(--popularity-accent\)/);
  const scope = css.match(/\.popularity-glance-scope\s*\{([^}]+)\}/)![1];
  assert.doesNotMatch(scope, /(?:^|;)\s*color:/);
  assert.match(scope, /white-space:\s*normal/);
});

for (const theme of [":root", '[data-theme="dark"]']) {
  test(`popularity accent meets AA small-text contrast in ${theme}`, () => {
    const tokens = css.slice(css.indexOf(`${theme} {`)).split("}")[0];
    const token = (name: string) => tokens.match(new RegExp(`--${name}:\\s*(#[a-fA-F0-9]{6})`))![1];
    const popularity = token("popularity-accent");
    assert.notEqual(popularity, token("accent"), "repository metadata must differ from recipe orange");
    const [red, green, blue] = popularity.slice(1).match(/.{2}/g)!.map((part) => parseInt(part, 16));
    assert.ok(green > red && blue > red, "keep metadata in the restrained cool palette, not orange");
    const foreground = luminance(popularity);
    for (const background of ["bg", "surface", "accent-soft"]) {
      const value = luminance(token(background));
      const contrast = (Math.max(foreground, value) + 0.05) / (Math.min(foreground, value) + 0.05);
      assert.ok(contrast >= 4.5, `${theme} ${background}: ${contrast.toFixed(2)}:1`);
    }
  });
}
