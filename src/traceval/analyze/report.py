# ruff: noqa: E501
from pathlib import Path
from typing import Any

import jinja2

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>traceval — Traffic & Eval Coverage Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: #151b2c;
            --card-border: #242f4c;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 2rem 1.5rem;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 1.5rem;
        }

        .logo-area h1 {
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            background: linear-gradient(to right, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .logo-area p {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }

        .stat-card {
            background-color: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s, border-color 0.2s;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            border-color: #3b82f640;
        }

        .stat-label {
            font-size: 0.875rem;
            color: var(--text-secondary);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            margin-top: 0.5rem;
            color: var(--text-primary);
        }

        .stat-desc {
            font-size: 0.775rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }

        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 2rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }

        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th {
            padding: 1rem;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            border-bottom: 2px solid var(--card-border);
            font-weight: 600;
        }

        td {
            padding: 1.25rem 1rem;
            border-bottom: 1px solid var(--card-border);
            font-size: 0.9rem;
            vertical-align: middle;
        }

        tr:hover td {
            background-color: rgba(255, 255, 255, 0.02);
        }

        .cluster-info {
            max-width: 400px;
        }

        .cluster-name {
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.25rem;
        }

        .cluster-sig {
            font-family: monospace;
            font-size: 0.75rem;
            color: var(--text-secondary);
            background-color: rgba(0, 0, 0, 0.2);
            padding: 0.125rem 0.375rem;
            border-radius: 0.25rem;
            display: inline-block;
        }

        .bar-container {
            width: 150px;
            background-color: rgba(255, 255, 255, 0.1);
            height: 0.5rem;
            border-radius: 0.25rem;
            overflow: hidden;
            display: inline-block;
            margin-right: 0.5rem;
            vertical-align: middle;
        }

        .bar-fill {
            height: 100%;
            border-radius: 0.25rem;
        }

        .bar-success { background-color: var(--success); }
        .bar-warning { background-color: var(--warning); }
        .bar-danger { background-color: var(--danger); }
        .bar-info { background-color: var(--info); }

        .traffic-td {
            white-space: nowrap;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.625rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .badge-success { background-color: rgba(16, 185, 129, 0.15); color: #34d399; }
        .badge-warning { background-color: rgba(245, 158, 11, 0.15); color: #fbbf24; }
        .badge-danger { background-color: rgba(239, 68, 68, 0.15); color: #f87171; }
        .badge-info { background-color: rgba(59, 130, 246, 0.15); color: #60a5fa; }

        details {
            margin-top: 1rem;
            background-color: rgba(0, 0, 0, 0.15);
            border-radius: 0.5rem;
            border: 1px solid var(--card-border);
        }

        summary {
            padding: 0.75rem 1rem;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
            cursor: pointer;
            outline: none;
            user-select: none;
        }

        summary:hover {
            color: var(--text-primary);
        }

        .details-content {
            padding: 0 1rem 1rem 1rem;
            max-height: 250px;
            overflow-y: auto;
        }

        .trace-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .trace-item:last-child {
            border-bottom: none;
        }

        .trace-item-id {
            font-family: monospace;
            color: var(--text-secondary);
        }

        .alert-banner {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(245, 158, 11, 0.15) 100%);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 0.75rem;
            padding: 1.25rem 1.5rem;
            margin-bottom: 2rem;
            display: flex;
            align-items: flex-start;
            gap: 1rem;
        }

        .alert-title {
            font-weight: 600;
            color: #f87171;
            margin-bottom: 0.25rem;
        }

        .alert-desc {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        .alert-icon {
            font-size: 1.5rem;
            line-height: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-area">
                <h1>traceval</h1>
                <p>Traffic Analysis & Evaluation Suite Coverage Report</p>
            </div>
            <div>
                <span class="badge badge-info">v{{ version }}</span>
            </div>
        </header>

        {% if alerts %}
        <div class="alert-banner">
            <span class="alert-icon">⚠️</span>
            <div>
                <h3 class="alert-title">Coverage Gaps Detected</h3>
                <p class="alert-desc">
                    We found {{ alerts|length }} cluster(s) with high traffic volumes or failure rates that do not have enough test cases generated.
                </p>
            </div>
        </div>
        {% endif %}

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Traces</div>
                <div class="stat-value">{{ total_traces }}</div>
                <div class="stat-desc">Ingested logs analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Clusters</div>
                <div class="stat-value">{{ clusters|length }}</div>
                <div class="stat-desc">Distinct task groups found</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value">{{ success_rate }}%</div>
                <div class="stat-desc">Of all analyzed traces</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Evals Coverage</div>
                <div class="stat-value">{{ covered_clusters_pct }}%</div>
                <div class="stat-desc">Clusters with &ge;1 eval case</div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">
                <span>Task Clusters & Eval Coverage Diff</span>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Cluster Details</th>
                        <th>Traffic Share</th>
                        <th>Dominant Outcome</th>
                        <th>Eval Cases</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in clusters %}
                    <tr>
                        <td class="cluster-info">
                            <div class="cluster-name">{{ c.name | e }}</div>
                            {% if c.tool_signature %}
                            <div class="cluster-sig">{{ c.tool_signature | e }}</div>
                            {% endif %}

                            <details>
                                <summary>Show Traces ({{ c.trace_ids|length }})</summary>
                                <div class="details-content">
                                    {% for tid in c.trace_ids %}
                                    <div class="trace-item">
                                        <span class="trace-item-id">{{ tid | e }}</span>
                                    </div>
                                    {% endfor %}
                                </div>
                            </details>
                        </td>
                        <td class="traffic-td">
                            <div class="bar-container">
                                <div class="bar-fill bar-info" style="width: {{ c.pct }}%"></div>
                            </div>
                            <span>{{ c.trace_count }} ({{ c.pct }}%)</span>
                        </td>
                        <td>
                            {% if "tool_error" in c.name or "bad_output" in c.name or "loop" in c.name or "timeout" in c.name or "validation_error" in c.name %}
                            <span class="badge badge-danger">Failure</span>
                            {% else %}
                            <span class="badge badge-success">Success</span>
                            {% endif %}
                        </td>
                        <td>
                            <strong>{{ c.cases_count }}</strong> case(s)
                        </td>
                        <td>
                            {% if c.cases_count == 0 %}
                                {% if "tool_error" in c.name or "bad_output" in c.name or "loop" in c.name or "timeout" in c.name or "validation_error" in c.name %}
                                <span class="badge badge-danger">Uncovered Failure</span>
                                {% else %}
                                <span class="badge badge-warning">Uncovered</span>
                                {% endif %}
                            {% else %}
                            <span class="badge badge-success">Active</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


def render_report(
    summary: dict[str, Any],
    coverage: dict[str, int],
    output_path: Path,
) -> None:
    total_traces = summary.get("total_traces", 0)
    clusters_data = summary.get("clusters", [])

    # Calculate success rate
    outcomes = summary.get("outcomes", {})
    success_count = outcomes.get("success", 0)
    success_rate = (
        round((success_count / total_traces) * 100) if total_traces > 0 else 0
    )

    # Decorate clusters with percentage and coverage count
    clusters = []
    covered_count = 0
    alerts = []

    for c in clusters_data:
        t_count = c.get("trace_count", 0)
        pct = round((t_count / total_traces) * 100) if total_traces > 0 else 0
        cid = c.get("id")
        cases_count = coverage.get(cid, 0)

        if cases_count > 0:
            covered_count += 1

        is_failure = any(
            x in c.get("name", "")
            for x in ["tool_error", "bad_output", "loop", "timeout", "validation_error"]
        )
        if cases_count == 0 and (pct >= 15 or is_failure):
            alerts.append(c)

        clusters.append(
            {
                "id": cid,
                "name": c.get("name", ""),
                "tool_signature": c.get("tool_signature", ""),
                "trace_ids": c.get("trace_ids", []),
                "trace_count": t_count,
                "pct": pct,
                "cases_count": cases_count,
            }
        )

    # Sort clusters: largest traffic share first
    clusters.sort(key=lambda x: x["trace_count"], reverse=True)

    covered_clusters_pct = (
        round((covered_count / len(clusters)) * 100) if clusters else 0
    )

    # Create HTML
    from traceval import __version__

    env = jinja2.Environment(autoescape=True)
    template = env.from_string(REPORT_TEMPLATE)
    html_content = template.render(
        total_traces=total_traces,
        success_rate=success_rate,
        covered_clusters_pct=covered_clusters_pct,
        clusters=clusters,
        alerts=alerts,
        version=__version__,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
