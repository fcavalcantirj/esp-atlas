"""esp-atlas CLI — thin front end over esp_atlas_core: search, wizard, ask."""
import click

from esp_atlas_core.ask import ask as core_ask
from esp_atlas_core.index_build import build_index
from esp_atlas_core.llm import GroqConfigError, GroqRateLimitError
from esp_atlas_core.search import search as core_search
from esp_atlas_core.validate import validate_file as core_validate_file
from esp_atlas_core.validate import validate_markdown as core_validate_markdown
from esp_atlas_core.wizard import wizard as core_wizard


@click.group()
@click.option("--db", "db_path", default=None, type=click.Path(), help="Path to esp-atlas.db (default: repo root)")
@click.pass_context
def cli(ctx, db_path):
    """esp-atlas: search, wizard, and ask over the esp-atlas ESP32 dataset."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path


@cli.command("build-index")
@click.pass_context
def build_index_cmd(ctx):
    """Build esp-atlas.db from data/**/*.md."""
    build_id = build_index(db_path=ctx.obj["db_path"])
    click.echo(f"Built esp-atlas.db (build {build_id})")


@cli.command()
@click.argument("query", required=False, default="")
@click.option("--radio", default=None, help="Minimum Wi-Fi standard, e.g. wifi-4 (also matches wifi-6)")
@click.option("--band", default=None, type=float, help="Wi-Fi band in GHz, e.g. 5")
@click.option("--form", default=None, help="Form factor, e.g. xiao")
@click.option("--protocol", default=None, help="802.15.4 protocol substring, e.g. zigbee")
@click.option("--type", "type_", default=None, type=click.Choice(["soc", "module", "board"]))
@click.option("--soc", default=None, help="Only parts built on this SoC id, e.g. esp32-c6")
@click.option("--brand", default=None, help="Only parts from this vendor/brand slug, e.g. adafruit")
@click.pass_context
def search(ctx, query, radio, band, form, protocol, type_, soc, brand):
    """Search the esp-atlas dataset (structured filters + free-text)."""
    filters = {}
    if radio:
        filters["radio"] = radio
    if band is not None:
        filters["band"] = band
    if form:
        filters["form"] = form
    if protocol:
        filters["protocol"] = protocol
    if type_:
        filters["type"] = type_
    if soc:
        filters["soc"] = soc
    if brand:
        filters["brand"] = brand

    try:
        results = core_search(query, filters=filters, db_path=ctx.obj["db_path"])
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    _print_records(results)


def _print_records(results):
    if not results:
        click.echo("No matches.")
        return
    for r in results:
        click.echo(f"{r['id']}  [{r['type']}]  {r['name']}")
        specs = []
        if r["wifi_standard"]:
            specs.append(f"wifi={r['wifi_standard']}" + (f" ({r['wifi_bands']} GHz)" if r["wifi_bands"] else ""))
        if r["ble_version"]:
            specs.append(f"ble={r['ble_version']}")
        if r["ieee802154"]:
            specs.append(f"802.15.4={r['ieee802154_protocols'] or 'yes'}")
        if r["form_factor"]:
            specs.append(f"form={r['form_factor']}")
        if specs:
            click.echo("    " + ", ".join(specs))
        click.echo(f"    {r['_path']}")


@cli.command()
@click.option("--protocol", default=None, help="802.15.4 protocol, e.g. zigbee/thread/matter")
@click.option("--radio", default=None, help="Minimum Wi-Fi standard, e.g. wifi-4 (also matches wifi-6)")
@click.option("--band", default=None, type=float, help="Wi-Fi band in GHz")
@click.option("--usb-native", "usb_native", is_flag=True, default=False, help="Require native USB")
@click.option("--form", default=None, help="Form factor, e.g. xiao")
@click.option("--type", "type_", default=None, type=click.Choice(["soc", "module", "board"]))
@click.option(
    "--budget",
    default=None,
    type=click.Choice(["cheap", "medium", "expensive"]),
    help="spending ceiling against each board's editorial price_tier",
)
@click.option("--guided/--no-guided", default=None, help="Force (or skip) interactive prompts")
@click.pass_context
def wizard(ctx, protocol, radio, band, usb_native, form, type_, budget, guided):
    """Guided or flag-driven part recommendation. Deterministic, no LLM."""
    any_flag = any([protocol, radio, band is not None, usb_native, form, type_, budget])
    if guided or (guided is None and not any_flag):
        needs = _prompt_needs()
    else:
        needs = {}
        if protocol:
            needs["protocol"] = protocol
        if radio:
            needs["radio"] = radio
        if band is not None:
            needs["band"] = band
        if usb_native:
            needs["usb_native"] = True
        if form:
            needs["form"] = form
        if type_:
            needs["type"] = type_
        if budget:
            needs["budget"] = budget

    try:
        results = core_wizard(needs, db_path=ctx.obj["db_path"])
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    _print_wizard_results(results)


def _prompt_needs():
    needs = {}
    protocol = click.prompt("802.15.4 protocol (zigbee/thread/matter, blank to skip)", default="", show_default=False)
    if protocol:
        needs["protocol"] = protocol
    radio = click.prompt("Wi-Fi standard (wifi-4/wifi-6, blank to skip)", default="", show_default=False)
    if radio:
        needs["radio"] = radio
    if click.confirm("Need native USB (no external UART bridge chip)?", default=False):
        needs["usb_native"] = True
    form = click.prompt("Form factor (e.g. xiao, devkit, blank to skip)", default="", show_default=False)
    if form:
        needs["form"] = form
    budget = click.prompt(
        "Budget (cheap/medium/expensive, blank to skip)",
        default="",
        show_default=False,
        type=click.Choice(["", "cheap", "medium", "expensive"]),
    )
    if budget:
        needs["budget"] = budget
    return needs


def _print_wizard_results(results):
    if not results:
        click.echo("No matches.")
        return
    for r in results:
        click.echo(f"{r['id']}  [{r['type']}]  {r['name']}  (score {r['score']})")
        for reason in r["reasons"]:
            click.echo(f"    - {reason}")


@cli.command()
@click.argument("question")
@click.pass_context
def ask(ctx, question):
    """Ask a natural-language question — grounded, cited, calls Groq."""
    try:
        result = core_ask(question, db_path=ctx.obj["db_path"])
    except GroqConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    except GroqRateLimitError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(result["answer"])
    click.echo()
    if result["citations"]:
        click.echo("Sources:")
        for c in result["citations"]:
            click.echo(f"  - {c['part']} ({c['file']}): {c['source_url']}")
    else:
        click.echo("Sources: none")


@cli.command()
@click.argument("paths", nargs=-1, required=True)
def validate(paths):
    """Validate one or more .md records against schema/, source, id/brand, and
    inheritance rules — the same checks CI runs. Pass `-` to read a full markdown
    document (frontmatter + body) from stdin instead of a file path."""
    total = failed = 0
    for p in paths:
        total += 1
        if p == "-":
            label = "<stdin>"
            result = core_validate_markdown(click.get_text_stream("stdin").read())
        else:
            label = p
            try:
                result = core_validate_file(p)
            except OSError as exc:
                result = {"ok": False, "errors": [str(exc)]}

        if result["ok"]:
            click.echo(f"PASS  {label}")
        else:
            failed += 1
            click.echo(f"FAIL  {label}")
            for err in result["errors"]:
                click.echo(f"    - {err}")

    click.echo()
    click.echo(f"{total - failed}/{total} valid, {failed} error(s)")
    if failed:
        raise SystemExit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
