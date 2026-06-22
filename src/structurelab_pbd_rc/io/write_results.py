"""Result writers."""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

import yaml

from structurelab_pbd_rc.io.serialization import to_json_safe


class ReadableYamlDumper(yaml.SafeDumper):
    """YAML dumper with indented lists, matching the hand-written configs."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


class FlowList(list):
    """List rendered in YAML flow style."""


def _represent_flow_list(dumper: yaml.Dumper, data: FlowList) -> yaml.SequenceNode:
    """Represent selected lists horizontally."""

    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


ReadableYamlDumper.add_representer(FlowList, _represent_flow_list)


def _format_selected_lists(value: Any, parent_key: str | None = None) -> Any:
    """Use horizontal YAML lists for compact repeated engineering inputs."""

    flow_list_keys = {"clear_spacing_wi", "w_i"}
    if isinstance(value, dict):
        return {key: _format_selected_lists(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        items = [_format_selected_lists(item) for item in value]
        if parent_key in flow_list_keys:
            return FlowList(items)
        return items
    return value


def write_json_result(data: dict[str, Any], path: str | Path) -> Path:
    """Write a JSON result file and return its path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(to_json_safe(data), file, indent=2, ensure_ascii=True)
    return output_path


def write_csv_rows(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """Write dictionaries to CSV and return the output path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: to_json_safe(row.get(key, "")) for key in fieldnames})
    return output_path


def write_yaml_result(data: dict[str, Any], path: str | Path) -> Path:
    """Write a YAML result file and return its path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    readable_data = _format_selected_lists(to_json_safe(data))
    with output_path.open("w", encoding="utf-8") as file:
        yaml.dump(
            readable_data,
            file,
            Dumper=ReadableYamlDumper,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
            width=100,
        )
    return output_path
