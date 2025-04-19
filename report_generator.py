#!/usr/bin/env python3
"""
Generate an author‑level code‑review report (HTML) from an AuthorsAnalysis JSON
file.

Dependencies
------------
pip install jinja2 markdown matplotlib
"""

from __future__ import annotations
import base64
import io
import json
import os
from collections import Counter
from typing import Any, Literal, NotRequired, TypedDict

import matplotlib.pyplot as plt
import markdown  # markdown -> HTML
from jinja2 import Environment, FileSystemLoader, select_autoescape

# if your project already defines these in a shared module, import them; otherwise
# uncomment the fallback definitions below.
from developerscope._types import *  # noqa: F401  (brings in EffortEnum, IssueEnum, etc.)
# -----------------------------------------------------------------------------
# Fallback type definitions (commented out)
# -----------------------------------------------------------------------------
# MergeRequestEnum = Literal[
#     "Feature",
#     "Bug‑fix",
#     "Refactor",
#     "Performance",
#     "Security‐patch",
#     "Docs / comments",
#     "Chore / dependency bump",
# ]
# IssueEnum = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
# EffortEnum = Literal["Trivial", "Minor", "Moderate", "Large", "Major"]
# class PottentialIssue(TypedDict):
#     filePath: str
#     line: str
#     issue: str
#     proposedSolution: str
#     level: IssueEnum
# class DetailedMergeRequestAnalysis(TypedDict):
#     hiddenReasoning: str
#     type: MergeRequestEnum
#     issues: list[PottentialIssue]
#     effortEstimate: EffortEnum
#     commitHash: str
#     metrics: dict[str, Any]
# class Branch(TypedDict):
#     branch: str
#     mergeRequests: list[DetailedMergeRequestAnalysis]
# class AuthorsAnalysis(TypedDict):
#     author: str
#     branches: list[Branch]
# -----------------------------------------------------------------------------

# ────────────────────────────────────────────────────────────────
# Static data
# ────────────────────────────────────────────────────────────────
EFFORT_ORDER: list[EffortEnum] = [
    "Trivial",
    "Minor",
    "Moderate",
    "Large",
    "Major",
]
SEVERITY_ORDER: list[IssueEnum] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

TYPE_COLOURS: dict[MergeRequestEnum, str] = {
    "Feature": "#1f77b4",
    "Bug‑fix": "#d62728",
    "Refactor": "#2ca02c",
    "Performance": "#ff7f0e",
    "Security‐patch": "#9467bd",
    "Docs / comments": "#8c564b",
    "Chore / dependency bump": "#e377c2",
}

# ────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────

def fig_to_base64(fig: plt.Figure) -> str:
    """Return the figure as a base‑64‑encoded PNG (no newlines)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def build_scatter(points: list[tuple[EffortEnum, int, MergeRequestEnum]]) -> str:
    """Create the effort‑vs‑issues scatter plot and return it as base‑64 PNG."""
    x = [EFFORT_ORDER.index(p[0]) for p in points]
    y = [p[1] for p in points]
    colours = [TYPE_COLOURS[p[2]] for p in points]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(x, y, c=colours, s=60, edgecolors="k")

    # Build legend (unique labels)
    seen: dict[MergeRequestEnum, bool] = {}
    for p_type, colour in zip((p[2] for p in points), colours):
        if p_type not in seen:
            ax.scatter([], [], c=colour, label=p_type)
            seen[p_type] = True
    ax.legend(title="Merge‑request type", bbox_to_anchor=(1.04, 1), loc="upper left")

    ax.set_xticks(range(len(EFFORT_ORDER)), EFFORT_ORDER, rotation=45, ha="right")
    ax.set_xlabel("Effort estimate")
    ax.set_ylabel("Number of issues")
    ax.set_title("Issues vs. Effort")

    return fig_to_base64(fig)


def build_type_pie(type_counts: Counter[MergeRequestEnum]) -> str:
    """Build a pie chart of commit types and return as base‑64 PNG."""
    if not type_counts:
        # Empty chart placeholder
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_axis_off()
        return fig_to_base64(fig)

    labels, sizes, colors = zip(
        *[(t, c, TYPE_COLOURS[t]) for t, c in type_counts.items()]
    )
    fig, ax = plt.subplots(figsize=(5, 5))
    wedges = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"linewidth": 0.5, "edgecolor": "#fff"},
        autopct=lambda p: f"{p:.0f}%",
    )
    ax.set_title("Commits by type")
    return fig_to_base64(fig)


# ────────────────────────────────────────────────────────────────
# Main entry point
# ────────────────────────────────────────────────────────────────

def generate_report(
    analysis: AuthorsAnalysis,
    repo_url: str,
    summary: str,
    output_dir: str = "out",
) -> str:
    """Build the HTML report and write it to *output_dir/{author}.html*."""
    author = analysis["author"]
    out_html = os.path.join(output_dir, f"{author}.html")
    os.makedirs(output_dir, exist_ok=True)

    # ── Data collection ────────────────────────────────────────
    scatter_pts: list[tuple[EffortEnum, int, MergeRequestEnum]] = []
    issues: list[dict[str, Any]] = []
    type_counter: Counter[MergeRequestEnum] = Counter()

    for br in analysis["branches"]:
        for mr in br["mergeRequests"]:
            # Scatter point
            scatter_pts.append((mr["effortEstimate"], len(mr["issues"]), mr["type"]))
            # Type pie
            type_counter[mr["type"]] += 1
            # Issues table
            for iss in mr["issues"]:
                issues.append(
                    {
                        "level": iss["level"],
                        "filePath": iss["filePath"],
                        "line": iss["line"],
                        "issue": iss["issue"],
                        "proposedSolution": iss["proposedSolution"],
                        "commit": mr["commitHash"],
                    }
                )

    # Sort issues by severity
    issues.sort(key=lambda i: SEVERITY_ORDER.index(i["level"]))

    # ── Generate charts ────────────────────────────────────────
    scatter_b64 = build_scatter(scatter_pts)
    pie_b64 = build_type_pie(type_counter)

    # ── Jinja2 template env ────────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(searchpath=os.path.dirname(__file__) or "."),
        autoescape=select_autoescape(["html"]),
    )
    template_file = "_report_template.html"

    # create default template if missing (developer can edit afterwards)
    if not os.path.exists(template_file):
        with open(template_file, "w", encoding="utf-8") as tf:
            tf.write(DEFAULT_TEMPLATE)

    template = env.get_template(template_file)

    # ── Render HTML ────────────────────────────────────────────
    html = template.render(
        author=author,
        summary=summary,
        scatter_b64=scatter_b64,
        pie_b64=pie_b64,
        repo_url=repo_url.rstrip("/"),
        issues=[
            {
                **i,
                "markdownSolution": markdown.markdown(i["proposedSolution"]),
            }
            for i in issues
        ],
    )

    # ── Write file ─────────────────────────────────────────────
    with open(out_html, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"✅  Report written to {out_html}")
    return out_html


# ────────────────────────────────────────────────────────────────
# Default Jinja2 template – only created once if not present
# ────────────────────────────────────────────────────────────────
DEFAULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ author }} – Code‑Review Report</title>
<style>
  :root {
    --clr-critical: #ff4d4f;
    --clr-high:     #ffa940;
    --clr-medium:   #ffe58f;
    --clr-low:      #bae7ff;
  }

  /* ------- base ------- */
  html { box-sizing: border-box; }
  *, *::before, *::after { box-sizing: inherit; }

  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    margin: 2rem;
    line-height: 1.5;
    color: #222;
    background: #fff;
  }

  h1, h2 {
    color: #212529;
    margin: 1.6em 0 .6em;
    line-height: 1.25;
  }

  /* ------- layout ------- */
  .report-container {
    display: grid;
    grid-template-columns: 55% 45%;
    gap: 2.5rem;
    align-items: start;
  }
  .left img { width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 1.4rem; }
  .right { overflow-x: auto; }

  /* ------- table ------- */
  table {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
    font-size: .92rem;
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 6px;
    overflow: hidden;
  }
  th, td {
    border: 1px solid #e1e4e8;
    padding: .55rem .6rem;
    vertical-align: top;
    word-break: break-word;
  }
  th {
    background: #f6f8fa;
    font-weight: 600;
    text-align: left;
  }
  th:nth-child(1), td:nth-child(1) { width: 85px; text-align: center; }
  th:nth-child(2), td:nth-child(2) { width: 210px; }
  tbody tr:hover { background: #f5faff; }

  /* ------- severity colours ------- */
  .sev-CRITICAL td { background: var(--clr-critical, #ff4d4f20); }
  .sev-HIGH     td { background: var(--clr-high,    #ffa94033); }
  .sev-MEDIUM   td { background: var(--clr-medium,  #ffe58f44); }
  .sev-LOW      td { background: var(--clr-low,     #bae7ff55); }

  .sev-CRITICAL td:first-child { border-left: 6px solid var(--clr-critical); }
  .sev-HIGH     td:first-child { border-left: 6px solid var(--clr-high); }
  .sev-MEDIUM   td:first-child { border-left: 6px solid var(--clr-medium); }
  .sev-LOW      td:first-child { border-left: 6px solid var(--clr-low); }

  /* markdown inside table */
  table p { margin: 0 0 .3rem; }
  table ul, table ol { margin: .3rem 0 .3rem 1.2rem; }
  code, pre {
    background: #f0f0f0;
    padding: .15rem .25rem;
    border-radius: 4px;
    font-family: Consolas, Monaco, 'Courier New', monospace;
    font-size: .85em;
  }
</style>
</head>
<body>
<h1>Repository Report for {{ author }}</h1>

<h2>Summary</h2>
<p>{{ summary }}</p>

<div class="report-container">
  <div class="left">
    <h2>Issues vs. Effort</h2>
    <img src="data:image/png;base64,{{ scatter_b64 }}" alt="Scatter: issues vs. effort" />

    <h2>Commits by type</h2>
    <img src="data:image/png;base64,{{ pie_b64 }}" alt="Pie chart: commits by type" />
  </div>

  <div class="right">
    <h2>Issues</h2>
    <table>
      <thead>
        <tr><th>Severity</th><th>File</th><th>Description</th><th>Proposed solution</th></tr>
      </thead>
      <tbody>
      {% for i in issues %}
        <tr class="sev-{{ i.level }}">
          <td>{{ i.level }}</td>
          <td><a href="{{ repo_url }}/commit/{{ i.commit }}" target="_blank">{{ i.filePath }}:{{ i.line }}</a></td>
          <td>{{ i.issue }}</td>
          <td>{{ i.markdownSolution | safe }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>

</body>
</html>

"""


# ────────────────────────────────────────────────────────────────
# Demo runner
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    AUTHOR = "iliyas.dzabbarov"
    IN_JSON = f"out/codeutils/{AUTHOR}.json"
    REPO_URL = "https://github.com/developerscope/codeutils"
    with open(IN_JSON, "r", encoding="utf-8") as jf:
        analysis_obj: AuthorsAnalysis = json.load(jf)

    generate_report(analysis_obj, REPO_URL, analysis_obj["summary"])
