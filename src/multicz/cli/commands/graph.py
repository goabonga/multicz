# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz graph`` - render the cascade DAG between components.

Two kinds of edges contribute:

* **mirrors** - file-based: ``A``'s mirror writes a path owned by
  ``B`` (a Helm chart's ``appVersion`` mirroring an API version).
* **depends_on** - name-based: ``B`` declares
  ``depends_on = ["A"]``.

Both are *cascade* edges directed upstream → downstream: bumping the
upstream may bump the downstream. Three output formats:

* ``tree`` (default) - ASCII tree, one root per component with no
  incoming cascade edge. Components with multiple upstreams appear
  under each parent (DAG flattened to a tree by duplication).
* ``mermaid`` - ``graph LR`` block ready to drop into Markdown
  (GitHub, MkDocs, …) for a rendered diagram.
* ``dot`` - Graphviz DOT for offline / static rendering.
"""

from __future__ import annotations

import typer
from rich.tree import Tree

from ...config import ComponentMatcher
from .. import app, console, err
from .._shared import _load


def _build_edges(config) -> list[tuple[str, str, str]]:
    """Cascade edges as ``(upstream, downstream, label)`` triples.

    Mirror edges fire when an upstream's mirror writes into a path
    owned by a different component; self-mirrors are skipped (they
    don't propagate). depends_on edges fire when a component lists a
    known component in its ``depends_on``.
    """
    edges: list[tuple[str, str, str]] = []
    matcher = ComponentMatcher(config.components)

    for name, comp in config.components.items():
        for mirror in comp.mirrors:
            target = matcher.match(str(mirror.file))
            if target is not None and target != name:
                key = f":{mirror.key}" if mirror.key else ""
                edges.append((name, target, f"mirror {mirror.file}{key}"))

    for name, comp in config.components.items():
        for upstream in comp.depends_on:
            if upstream in config.components:
                edges.append((upstream, name, "depends_on"))

    return edges


def _walk_tree(
    parent: Tree,
    node: str,
    children: dict[str, list[tuple[str, str]]],
    path: frozenset[str],
) -> None:
    """Recursively attach children of ``node`` to ``parent``.

    ``path`` is the set of nodes on the current branch; if we'd revisit
    one we annotate a cycle marker and stop. The set is scoped to the
    current branch so a DAG with shared descendants renders correctly
    (the same node may appear under multiple parents)."""
    if node in path:
        parent.add(f"[red]↻ cycle back to {node}[/]")
        return
    branch_path = path | {node}
    for child, label in children.get(node, []):
        sub = parent.add(f"[bold cyan]{child}[/] [dim]({label})[/]")
        _walk_tree(sub, child, children, branch_path)


def _render_tree(config, edges, *, root: str | None) -> None:
    children: dict[str, list[tuple[str, str]]] = {}
    parents: dict[str, list[str]] = {}
    for u, d, label in edges:
        children.setdefault(u, []).append((d, label))
        parents.setdefault(d, []).append(u)

    if root is not None:
        roots = [root]
    else:
        all_names = list(config.components)
        # A component is a "root" if nothing upstream cascades into it.
        roots = [n for n in all_names if n not in parents]
        if not roots:
            # Pure cycle case (shouldn't happen post-validate, but guard).
            roots = all_names
        # Also include components that ARE roots in the DAG sense but
        # have no children either - they'd otherwise be invisible.
        # Already covered: roots includes them, just no descendants.

    for i, name in enumerate(roots):
        if i > 0:
            console.print()
        tree = Tree(f"[bold green]{name}[/]")
        _walk_tree(tree, name, children, frozenset())
        console.print(tree)


def _render_mermaid(config, edges, *, root: str | None) -> None:
    if root is not None:
        keep = _reachable(root, edges)
        edges = [(u, d, lbl) for u, d, lbl in edges if u in keep and d in keep]

    print("graph LR")
    for name in config.components:
        if root is None or name in _reachable(root, edges) or name == root:
            print(f"  {name}")
    for u, d, label in edges:
        # Mermaid edge labels can't contain `|`; escape just in case.
        clean = label.replace("|", "\\|")
        print(f"  {u} -->|{clean}| {d}")


def _render_dot(config, edges, *, root: str | None) -> None:
    if root is not None:
        keep = _reachable(root, edges)
        edges = [(u, d, lbl) for u, d, lbl in edges if u in keep and d in keep]
    else:
        keep = set(config.components)

    print("digraph multicz {")
    print("  rankdir=LR;")
    print('  node [shape=box, style="rounded"];')
    for name in config.components:
        if name in keep or root is None:
            print(f'  "{name}";')
    for u, d, label in edges:
        clean = label.replace('"', '\\"')
        print(f'  "{u}" -> "{d}" [label="{clean}"];')
    print("}")


def _reachable(root: str, edges: list[tuple[str, str, str]]) -> set[str]:
    """Set of component names reachable downstream from ``root`` (inclusive)."""
    children: dict[str, list[str]] = {}
    for u, d, _ in edges:
        children.setdefault(u, []).append(d)
    seen: set[str] = set()
    stack = [root]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(children.get(n, []))
    return seen


@app.command(name="graph")
def graph_cmd(
    output: str = typer.Option(
        "tree", "--output", "-o",
        help="tree | mermaid | dot [default: tree]",
    ),
    component: str = typer.Option(
        None, "--component", "-c",
        help="Show only the cascade rooted at this component (downstream).",
    ),
) -> None:
    """Render the cascade DAG between components.

    Edges are directed upstream → downstream and come from two sources:
    ``mirrors`` (file-based) and ``depends_on`` (name-based). Both are
    propagation edges - bumping the upstream may bump the downstream.

    Examples:

    \b
    multicz graph                          # ASCII tree, all roots
    multicz graph -c api                   # downstream cascade from api
    multicz graph --output mermaid         # paste into a Markdown doc
    multicz graph --output dot | dot -Tsvg # render via Graphviz
    """
    if output not in {"tree", "mermaid", "dot"}:
        err.print(
            f"[red]unknown --output:[/] {output} "
            "(use 'tree', 'mermaid', or 'dot')"
        )
        raise typer.Exit(code=1)

    _, config = _load()
    if component is not None and component not in config.components:
        err.print(f"[red]unknown component:[/] {component}")
        raise typer.Exit(code=1)

    edges = _build_edges(config)

    if output == "tree":
        _render_tree(config, edges, root=component)
    elif output == "mermaid":
        _render_mermaid(config, edges, root=component)
    elif output == "dot":
        _render_dot(config, edges, root=component)
