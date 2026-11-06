# Bundled Geist fonts

`geist-latin.woff2` and `geist-mono-latin.woff2` are WOFF2 subsets of the
adjacent `Geist.ttf` (version 1.800) and `GeistMono.ttf` (version 1.701). The
included `OFL.txt` covers both source and derived files. Keep the TTF files as
the source for future regeneration.

Regenerate with fontTools 4.58.4 and Brotli 1.2.1:

```sh
for family in Geist GeistMono; do
  case "$family" in
    Geist) output=geist-latin.woff2 ;;
    GeistMono) output=geist-mono-latin.woff2 ;;
  esac
  pyftsubset "$family.ttf" \
    --output-file="$output" --flavor=woff2 \
    --unicodes=U+0000-024F,U+1E00-1EFF,U+2000-206F,U+20A0-20CF,U+2100-214F,U+2190-22FF,U+2500-257F,U+2600-26FF \
    --layout-features='*' --name-IDs='*' --name-legacy --name-languages='*'
done
```

These ranges cover every character present in the site's source content that
the original fonts support. CSS system fallbacks render other characters in
dynamic content, including upstream README text.
