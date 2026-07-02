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
) -> None:
    """Ingest trace logs into SQLite database."""
    db = TraceStore(output)
    try:
        ok_count, span_count, warn_count, log_file = ingest_file(
            Path(path), db, format_name=format
        )
        if warn_count > 0:
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
) -> None:
    """Analyze ingested traces (labeling, clustering, coverage)."""
    db_p = Path(db_path)
    if not db_p.exists():
        typer.echo(f"Error: database file {db_path} does not exist.")
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

    clusters = summary["clusters"]
    typer.echo(f"Clusters: {len(clusters)} task clusters found.")

    # Any cluster whose dominant outcome is not success is a failure cluster.
    # Named with (label) suffix.
    failure_clusters = [
        c for c in clusters if "(" in c["name"] and "success" not in c["name"]
    ]
    if failure_clusters:
        top_fail = max(failure_clusters, key=lambda c: c["trace_count"])
        typer.echo(
            f'Top failure cluster: "{top_fail["name"]}" '
            f"({top_fail['trace_count']} traces)"
        )

    # Save json report
    report_json_path = out_dir / "report.json"
    report_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
) -> None:
    """Generate eval cases, rubrics, and pytest harness from traces."""
    db_p = Path(db_path)
    if not db_p.exists():
        typer.echo(f"Error: database file {db_path} does not exist.")
        raise typer.Exit(1)

    out_dir = Path(output)
    cases_count, clusters_count = generate_evals(
        db_p,
        out_dir,
        per_cluster=per_cluster,
        include_failures=include_failures,
        redact_hook_str=redact_hook,
    )

    typer.echo(
        f"Wrote {cases_count} eval cases across {clusters_count} clusters "
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

    # Run pytest programmatically
    exit_code = pytest.main(args)
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
