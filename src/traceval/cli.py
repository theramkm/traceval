import json
from pathlib import Path

import typer

from traceval.analyze import run_analysis
from traceval.compile import generate_evals
from traceval.ingest import ingest_file
from traceval.store import TraceStore

app = typer.Typer(name="traceval", help="Trace-to-Eval Compiler")


@app.command()
def version() -> None:
    """Print the version of traceval."""
    from traceval import __version__

    typer.echo(f"traceval version {__version__}")


@app.command()
def ingest(
    path: str,
    format: str = typer.Option("auto", help="auto|otel|langfuse|langsmith|generic"),
    output: str = typer.Option("traces.db", "-o", help="SQLite database output path"),
    json_output: bool = typer.Option(
        False, "--json", help="Print a machine-readable JSON summary to stdout"
    ),
) -> None:
    """Ingest trace logs into SQLite database."""
    db = TraceStore(output)
    try:
        ok_count, span_count, warn_count, log_file = ingest_file(
            Path(path), db, format_name=format
        )
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "traces": ok_count,
                        "spans": span_count,
                        "warnings": warn_count,
                        "log": str(log_file) if warn_count > 0 else None,
                        "db": output,
                    }
                )
            )
        elif warn_count > 0:
            typer.echo(
                f"Ingested {ok_count} traces ({span_count} spans). "
                f"{warn_count} traces had warnings (see {log_file})."
            )
        else:
            typer.echo(f"Ingested {ok_count} traces ({span_count} spans).")
    finally:
        db.close()


@app.command()
def analyze(
    db_path: str,
    rules: str = typer.Option(None, help="Custom rules file.py"),
    evals: str = typer.Option(None, help="Existing evals/ directory to check coverage"),
    output: str = typer.Option("analysis/", "-o", help="Output analysis directory"),
    json_output: bool = typer.Option(
        False, "--json", help="Print a machine-readable JSON summary to stdout"
    ),
) -> None:
    """Analyze ingested traces (labeling, clustering, coverage)."""
    db_p = Path(db_path)
    if not db_p.exists():
        typer.echo(f"Error: database file {db_path} does not exist.", err=True)
        raise typer.Exit(1)

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        db_p,
        rules_path=Path(rules) if rules else None,
        evals_dir=Path(evals) if evals else None,
        output_dir=out_dir,
    )

    total = summary["total_traces"]
    clusters = summary["clusters"]

    # Any cluster whose dominant outcome is not success is a failure cluster.
    # Named with (label) suffix.
    failure_clusters = [
        c for c in clusters if "(" in c["name"] and "success" not in c["name"]
    ]
    top_fail = (
        max(failure_clusters, key=lambda c: c["trace_count"])
        if failure_clusters
        else None
    )

    # Save json report
    report_json_path = out_dir / "report.json"
    report_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "outcomes": {k: v / total for k, v in summary["outcomes"].items()}
                    if total
                    else {},
                    "clusters": len(clusters),
                    "top_failure_cluster": (
                        {"name": top_fail["name"], "traces": top_fail["trace_count"]}
                        if top_fail
                        else None
                    ),
                    "report_html": str(out_dir / "report.html"),
                    "report_json": str(report_json_path),
                }
            )
        )
        return

    if total == 0:
        typer.echo("No traces found to analyze.")
        return

    # Print outcomes formatted
    outcomes_list = []
    for k, v in summary["outcomes"].items():
        pct = round((v / total) * 100)
        outcomes_list.append(f"{k} {pct}%")
    outcomes_str = " · ".join(outcomes_list)
    typer.echo(f"Outcomes: {outcomes_str}")

    typer.echo(f"Clusters: {len(clusters)} task clusters found.")

    if top_fail:
        typer.echo(
            f'Top failure cluster: "{top_fail["name"]}" '
            f"({top_fail['trace_count']} traces)"
        )

    typer.echo(f"Report written to {out_dir / 'report.html'}")


@app.command()
def generate(
    db_path: str,
    output: str = typer.Option("evals/", "-o", help="Output evals directory"),
    per_cluster: int = typer.Option(3, help="Max representative cases per cluster"),
    include_failures: bool = typer.Option(
        False, "--include-failures", help="Include failure cases"
    ),
    redact_hook: str = typer.Option(
        None, help="Custom PII redaction hook (module:function)"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print a machine-readable JSON summary to stdout"
    ),
) -> None:
    """Generate eval cases, rubrics, and pytest harness from traces."""
    db_p = Path(db_path)
    if not db_p.exists():
        typer.echo(f"Error: database file {db_path} does not exist.", err=True)
        raise typer.Exit(1)

    out_dir = Path(output)
    counts = generate_evals(
        db_p,
        out_dir,
        per_cluster=per_cluster,
        include_failures=include_failures,
        redact_hook_str=redact_hook,
    )

    if json_output:
        typer.echo(json.dumps({**counts, "output_dir": output}))
        return

    typer.echo(
        f"Wrote {counts['cases']} eval cases across {counts['clusters']} clusters "
        f"→ {output}/cases/*.yaml"
    )
    typer.echo(f"Wrote judge rubrics → {output}/rubrics/*.md")
    typer.echo(
        f"Wrote pytest harness → {output}/test_generated.py, {output}/conftest.py"
    )


@app.command()
def run(
    evals_dir: str,
    target: str = typer.Option(..., help="Target URL or module:fn"),
    judge: str = typer.Option("fake", help="fake|openai"),
    compare: str = typer.Option(None, help="Compare with previous run JSON report"),
    only: str = typer.Option(None, help="Filter by cluster or case ID"),
    runs_dir: str = typer.Option(
        None, help="Directory for run reports (default: <evals_dir>/runs)"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print a machine-readable JSON summary to stdout"
    ),
) -> None:
    """Run generated evals against target."""
    import pytest

    args = [
        evals_dir,
        "--target",
        target,
        "--judge",
        judge,
    ]
    if compare:
        args.extend(["--compare", compare])
    if only:
        args.extend(["--only", only])
    if runs_dir:
        args.extend(["--runs-dir", runs_dir])

    if json_output:
        import contextlib
        import io

        reports_dir = Path(runs_dir) if runs_dir else Path(evals_dir) / "runs"
        before = set(reports_dir.glob("run_*.json")) if reports_dir.exists() else set()

        # Swallow pytest's and the suite's rich terminal output: stdout must
        # carry exactly one JSON object.
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exit_code = int(pytest.main(args))

        after = set(reports_dir.glob("run_*.json")) if reports_dir.exists() else set()
        new_reports = sorted(after - before)
        report_path = new_reports[-1] if new_reports else None

        summary = {"total": 0, "passed": 0, "failed": 0}
        if report_path:
            with open(report_path, encoding="utf-8") as f:
                summary = json.load(f).get("summary", summary)

        typer.echo(
            json.dumps(
                {
                    "total": summary.get("total", 0),
                    "passed": summary.get("passed", 0),
                    "failed": summary.get("failed", 0),
                    "report": str(report_path) if report_path else None,
                    "exit_code": exit_code,
                }
            )
        )
        raise typer.Exit(code=exit_code)

    # Run pytest programmatically
    exit_code = pytest.main(args)
    raise typer.Exit(code=exit_code)


@app.command()
def calibrate(
    run_report: str,
    sample: int = typer.Option(20, help="Number of judged cases to label"),
    seed: int = typer.Option(0, help="Sampling seed (deterministic)"),
    output: str = typer.Option(
        "calibration.json", "-o", "--output", help="Calibration report output path"
    ),
    min_agreement: float = typer.Option(
        0.8, help="Flag clusters whose judge-vs-human agreement falls below this"
    ),
) -> None:
    """Validate the LLM judge against human labels on a sample of run results.

    Presents sampled agent outputs for blind pass/fail labeling (judge
    verdicts are hidden until the end), then reports judge-vs-human
    agreement overall and per cluster.
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from traceval.run.calibrate import (
        compute_agreement,
        extract_judged_results,
        sample_judged,
    )

    report_path = Path(run_report)
    if not report_path.exists():
        typer.echo(f"Run report not found: {run_report}", err=True)
        raise typer.Exit(code=1)
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    judged = extract_judged_results(report)
    if not judged:
        typer.echo(
            "No judge-scored results with recorded outputs in this report. "
            "Reports written before traceval 0.2.0 lack the input/output "
            "fields calibrate needs: regenerate the suite (traceval generate) "
            "and rerun (traceval run) first.",
            err=True,
        )
        raise typer.Exit(code=1)

    picked = sample_judged(judged, sample, seed)

    console = Console()
    console.print(
        f"\n[bold]Calibrating judge on {len(picked)} sampled case(s).[/bold] "
        "Label each output pass/fail; judge verdicts stay hidden until the end.\n"
    )

    labeled = []
    for idx, item in enumerate(picked, 1):
        console.print(
            Panel(
                str(item["input"]),
                title=f"[{idx}/{len(picked)}] {item['case_id']} -- input",
                border_style="blue",
            )
        )
        console.print(
            Panel(
                str(item["output"]) or "(empty output)",
                title="agent output",
                border_style="cyan",
            )
        )
        human_passed = typer.confirm("Human verdict -- pass?")
        labeled.append({**item, "human_passed": human_passed})

    stats = compute_agreement(labeled, min_agreement=min_agreement)

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Cluster", style="magenta")
    table.add_column("Labeled", justify="right")
    table.add_column("Agreement", justify="right")
    for cluster, cstats in sorted(stats["per_cluster"].items()):
        pct = f"{cstats['agreement']:.0%}"
        style = "red" if cluster in stats["flagged_clusters"] else "green"
        table.add_row(cluster, str(cstats["total"]), f"[{style}]{pct}[/{style}]")

    console.print("\n[bold purple]Judge Calibration Summary[/bold purple]")
    console.print(table)
    console.print(
        f"Overall agreement: {stats['agreement']:.0%} on {stats['total']} case(s) | "
        f"false-pass (judge OK, human not): {stats['false_pass']} | "
        f"false-fail: {stats['false_fail']}"
    )
    if stats["flagged_clusters"]:
        console.print(
            f"[bold red]⚠️ Judge unreliable (< {min_agreement:.0%} agreement) for "
            f"clusters: {', '.join(stats['flagged_clusters'])}. Review their "
            "rubrics before trusting automated scores.[/bold red]"
        )
    else:
        console.print(
            f"[green]Judge agreement is at or above {min_agreement:.0%} for all "
            "sampled clusters.[/green]"
        )

    out_path = Path(output)
    out_path.write_text(
        json.dumps({"stats": stats, "labels": labeled}, indent=2),
        encoding="utf-8",
    )
    console.print(f"Calibration report written to: {out_path}")


if __name__ == "__main__":
    app()
