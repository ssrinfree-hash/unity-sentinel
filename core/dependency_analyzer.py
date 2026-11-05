"""Assembly and (heuristic) class dependency analysis.

Scope and honesty notes:

* Assembly dependencies are read from ``.asmdef`` / ``.asmref`` files. Cycles in
  the *assembly* graph are a hard error in Unity, so they are reported as
  errors with high confidence.
* Class-level dependencies are derived from ``using`` directives and type
  references found by regular expressions. This is explicitly **heuristic**:
  it cannot see reflection, dynamic dispatch, ``partial`` classes across
  files, generic constraints or code generated at build time.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from .models import Confidence, Finding, Severity

LOGGER = logging.getLogger("unity_sentinel.dependencies")

_CLASS_RE = re.compile(
    r"\b(?:public|internal|private|protected|sealed|static|abstract|partial|\s)*"
    r"\bclass\s+([A-Za-z_]\w*)",
)
_TYPE_REF_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")


def load_assembly_definitions(root: Path) -> tuple[dict[str, dict], list[Finding]]:
    """Parse all ``.asmdef`` files.

    Returns a mapping ``name -> parsed definition`` plus findings for malformed
    files. The name falls back to the file stem when ``name`` is empty.
    """
    definitions: dict[str, dict] = {}
    findings: list[Finding] = []
    for asmdef_path in sorted(root.rglob("*.asmdef")):
        rel = asmdef_path.relative_to(root).as_posix()
        # Only paths *inside* the project are filtered: the project itself may
        # legitimately live under a folder called "Temp" (Windows temp dirs).
        if any(part in {"Library", "Temp", "Obj", "Logs", "Builds"} for part in rel.split("/")[:-1]):
            continue
        try:
            data = json.loads(asmdef_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding(
                    code="ASMDEF_INVALID",
                    message=f"Assembly definition is not valid JSON: {exc}",
                    severity=Severity.ERROR,
                    path=rel,
                    confidence=Confidence.HIGH,
                    recommendation="Fix the JSON syntax; Unity will not compile the assembly otherwise.",
                    category="dependencies",
                )
            )
            continue
        if not isinstance(data, dict):
            findings.append(
                Finding(
                    code="ASMDEF_INVALID",
                    message="Assembly definition must be a JSON object.",
                    severity=Severity.ERROR,
                    path=rel,
                    confidence=Confidence.HIGH,
                    category="dependencies",
                )
            )
            continue
        name = str(data.get("name") or asmdef_path.stem)
        if name in definitions:
            findings.append(
                Finding(
                    code="ASMDEF_DUPLICATE_NAME",
                    message=f"Two assembly definitions share the name '{name}'.",
                    severity=Severity.ERROR,
                    path=rel,
                    confidence=Confidence.HIGH,
                    recommendation="Assembly names must be unique across the project.",
                    category="dependencies",
                )
            )
        references = data.get("references") or []
        if not isinstance(references, list):
            references = []
        definitions[name] = {
            "path": rel,
            "references": [str(ref) for ref in references],
            "include_platforms": data.get("includePlatforms") or [],
            "raw": data,
        }
    return definitions, findings


def find_assembly_cycles(definitions: dict[str, dict]) -> list[Finding]:
    """Detect cycles in the assembly reference graph (iterative Tarjan SCC)."""
    # References may be GUID-based ("GUID:xxxx") or name based ("Unity.TextMeshPro")
    # or relative paths ("../Foo/Bar.asmdef"). Normalise to names where possible.
    edges: dict[str, list[str]] = {}
    for name, defn in definitions.items():
        targets: list[str] = []
        for ref in defn["references"]:
            if ref.startswith("GUID:"):
                # GUID references cannot be resolved without the .meta database;
                # skip them rather than guessing.
                continue
            candidate = Path(ref).stem
            if candidate in definitions:
                targets.append(candidate)
            elif ref in definitions:
                targets.append(ref)
        edges[name] = sorted(set(targets))

    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    for start in sorted(edges):
        if start in indices:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, child_idx = work.pop()
            if child_idx == 0:
                indices[node] = index_counter
                lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            children = edges.get(node, [])
            for idx in range(child_idx, len(children)):
                child = children[idx]
                if child not in edges:
                    continue
                if child not in indices:
                    work.append((node, idx + 1))
                    work.append((child, 0))
                    recursed = True
                    break
                if child in on_stack:
                    lowlink[node] = min(lowlink[node], indices[child])
            if recursed:
                continue
            if lowlink[node] == indices[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in edges.get(node, []):
                    sccs.append(sorted(component))
            if work:
                parent, _ = work[-1]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    findings: list[Finding] = []
    for component in sorted(sccs):
        findings.append(
            Finding(
                code="ASM_CYCLE",
                message="Assembly reference cycle: " + " -> ".join(component + [component[0]]),
                severity=Severity.ERROR,
                path=definitions[component[0]]["path"],
                confidence=Confidence.HIGH,
                recommendation="Break the cycle by moving shared code into a lower-level assembly.",
                category="dependencies",
            )
        )
    return findings


def build_class_graph(script_paths: list[Path], root: Path) -> tuple[dict[str, set[str]], list[Finding]]:
    """Approximate class -> referenced-class graph from ``using`` + identifiers.

    This is a **heuristic**; consumers must label it as such.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    findings: list[Finding] = []
    class_locations: dict[str, str] = {}

    parsed: list[tuple[str, str]] = []
    for path in script_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            LOGGER.debug("Cannot read %s: %s", path, exc)
            continue
        rel = path.relative_to(root).as_posix()
        classes = _CLASS_RE.findall(text)
        for cls in classes:
            if cls in class_locations and class_locations[cls] != rel:
                findings.append(
                    Finding(
                        code="CLASS_DUPLICATE_NAME",
                        message=f"Class '{cls}' is declared in multiple files.",
                        severity=Severity.WARNING,
                        path=rel,
                        confidence=Confidence.MEDIUM,
                        evidence=f"also declared in {class_locations[cls]}",
                        recommendation="Verify namespaces; duplicate class names cause ambiguous references.",
                        category="dependencies",
                    )
                )
            else:
                class_locations[cls] = rel
        parsed.append((rel, text))

    known = set(class_locations)
    for rel, text in parsed:
        own = set(_CLASS_RE.findall(text)) or {Path(rel).stem}
        for name in own:
            for ref in _TYPE_REF_RE.findall(text):
                if ref in known and ref not in own:
                    graph[name].add(ref)

    return graph, findings


def analyze_dependencies(root: Path, summary, config=None) -> list[Finding]:
    """Run the full dependency analysis for a scanned project."""
    findings: list[Finding] = []
    definitions, asm_findings = load_assembly_definitions(root)
    findings.extend(asm_findings)
    findings.extend(find_assembly_cycles(definitions))

    script_paths = [root / rel for rel in summary.scripts]
    _, class_findings = build_class_graph(script_paths, root)
    findings.extend(class_findings)
    return findings
