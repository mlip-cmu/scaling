"""Document the data flow: which component produces and consumes which topic.

The diagram is generated from the declarations in components.py, so it stays correct when
the components change. It is written into README.md (between the dataflow markers).
"""

import re
from pathlib import Path

from components import COMPONENTS, TOPICS


def node(name: str) -> str:
    return name.replace("-", "_")


def mermaid() -> str:
    lines = ["flowchart LR"]
    for t, n in TOPICS.items():
        lines.append(f"  {t}[/{t}<br/>{n} partitions/]")
    for name, spec in COMPONENTS.items():
        lines.append(f"  {node(name)}({name})")
        for t in spec["consumes"]:
            label = f"|{spec['group']}|" if spec["group"] != name else ""
            lines.append(f"  {t} -->{label} {node(name)}")
        for t in spec["produces"]:
            lines.append(f"  {node(name)} --> {t}")
    return "\n".join(lines)


if __name__ == "__main__":
    diagram = mermaid()
    print(diagram)
    readme = Path("README.md")
    text = readme.read_text()
    block = f"<!-- dataflow -->\n```mermaid\n{diagram}\n```\n<!-- /dataflow -->"
    readme.write_text(re.sub(r"<!-- dataflow -->.*<!-- /dataflow -->", block, text, flags=re.S))
