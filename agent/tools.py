"""
IRI Standards Agent — Tool Definitions
16 tools for OpenAPI 3.1 validation, style checking, DD coverage, and spec lookup.

Tools:
  Programmatic Validation (6):
    - validate_openapi_structure
    - parse_yaml_safely
    - emit_yaml
    - check_style_guide_rules
    - compute_dd_coverage
    - generate_scorecard
  Multi-Part Assembly (2):
    - manage_multipart_assembly
    - get_assembled_yaml
  Lookup (5):
    - list_available_specs
    - get_endpoint_schema
    - get_schema_definition
    - validate_payload_against_schema
    - list_schema_names
  Structural Analysis (1):
    - check_conditional_logic
  Structural Analysis (1):
    - check_conditional_logic
  Fetch (2):
    - fetch_yaml_from_url
    - fetch_data_dictionary
"""

import json
import io
import copy
import subprocess
import os
import re
from typing import Optional
from dataclasses import dataclass, field

import yaml
import jsonschema
from ruamel.yaml import YAML
from openapi_spec_validator import validate as openapi_validate
from strands import tool
import urllib.request
import urllib.error
import tempfile


# ============================================================================
# IRI BASELINE SPECS (loaded from GitHub at module import)
# ============================================================================
IRI_SPECS = {}

def load_iri_specs():
    """Clone IRI Digital-First-Specifications repo and load all specs.
    Gracefully handles failure (git not available, network restricted, etc.)."""
    global IRI_SPECS
    SPECS_DIR = "/tmp/Digital-First-Specifications/docs/specs"
    try:
        if not os.path.exists(SPECS_DIR):
            result = subprocess.run(
                ["git", "clone", "--depth", "1",
                 "https://github.com/Insured-Retirement-Institute/Digital-First-Specifications.git",
                 "/tmp/Digital-First-Specifications"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"[tools] git clone failed: {result.stderr[:200]}", flush=True)
    except Exception as e:
        print(f"[tools] git clone skipped (not available): {e}", flush=True)

    if os.path.exists(SPECS_DIR):
        for fname in sorted(os.listdir(SPECS_DIR)):
            if fname.endswith((".yaml", ".yml")):
                try:
                    with open(os.path.join(SPECS_DIR, fname)) as fh:
                        spec = yaml.safe_load(fh.read())
                    if isinstance(spec, dict) and "openapi" in spec:
                        key = fname.rsplit(".", 1)[0].lower().replace("-", "").replace("_", "")
                        IRI_SPECS[key] = spec
                except Exception:
                    pass
    print(f"[tools] Loaded {len(IRI_SPECS)} IRI specs", flush=True)
    return len(IRI_SPECS)

# Load specs on import (non-fatal if it fails)
try:
    _spec_count = load_iri_specs()
except Exception as e:
    print(f"[tools] IRI spec loading failed (non-fatal): {e}", flush=True)
    _spec_count = 0


# ============================================================================
# MULTI-PART ASSEMBLY STATE MANAGER
# ============================================================================
@dataclass
class MultiPartState:
    """State manager for multi-part YAML assembly."""
    yaml_document_id: str = ""
    version_intent: str = ""
    expected_parts: int = 0
    received_parts: dict = field(default_factory=dict)
    assembly_complete: bool = False
    assembled_yaml: str = ""

MULTIPART_STATE: dict[str, MultiPartState] = {}


# ============================================================================
# CORE UTILITIES
# ============================================================================
def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a $ref pointer within an OpenAPI spec."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        node = node.get(p, {})
    return node


def _resolve_all_refs(spec: dict, node) -> dict:
    """Recursively resolve all $ref pointers in a schema node."""
    if isinstance(node, dict):
        if "$ref" in node:
            resolved = _resolve_ref(spec, node["$ref"])
            return _resolve_all_refs(spec, copy.deepcopy(resolved))
        return {k: _resolve_all_refs(spec, v) for k, v in node.items()}
    elif isinstance(node, list):
        return [_resolve_all_refs(spec, item) for item in node]
    return node


def _clean_for_jsonschema(node):
    """Remove OpenAPI-specific keys not valid in JSON Schema."""
    if isinstance(node, dict):
        for key in ["example", "xml", "nullable", "discriminator", "externalDocs"]:
            node.pop(key, None)
        for v in node.values():
            _clean_for_jsonschema(v)
    elif isinstance(node, list):
        for item in node:
            _clean_for_jsonschema(item)


# ============================================================================
# PROGRAMMATIC VALIDATION TOOLS
# ============================================================================
@tool
def validate_openapi_structure(yaml_content: str) -> str:
    """Validate that a YAML string is structurally valid OpenAPI 3.1.
    Returns errors/warnings from openapi-spec-validator. This is a DETERMINISTIC check.

    Args:
        yaml_content: The OpenAPI YAML content as a string
    """
    try:
        yaml_parser = YAML()
        yaml_parser.preserve_quotes = True
        spec_dict = yaml_parser.load(io.StringIO(yaml_content))

        if not isinstance(spec_dict, dict):
            return json.dumps({"valid": False, "critical_fail": True,
                              "errors": [{"message": "YAML does not parse to a dictionary"}]})

        openapi_version = spec_dict.get("openapi", "")
        if not openapi_version.startswith("3.1"):
            return json.dumps({
                "valid": False, "critical_fail": True,
                "errors": [{"message": f"OpenAPI version '{openapi_version}' is not 3.1.x."}]
            })

        errors = []
        try:
            openapi_validate(spec_dict)
        except Exception as e:
            errors.append({"message": str(e), "type": "structural"})

        if errors:
            return json.dumps({"valid": False, "critical_fail": True, "errors": errors}, indent=2)

        return json.dumps({
            "valid": True,
            "critical_fail": False,
            "openapi_version": openapi_version,
            "title": spec_dict.get("info", {}).get("title", "Unknown"),
            "paths_count": len(spec_dict.get("paths", {})),
            "schemas_count": len(spec_dict.get("components", {}).get("schemas", {})),
            "message": "OpenAPI 3.1 structure is valid."
        })
    except Exception as e:
        return json.dumps({"valid": False, "critical_fail": True,
                          "errors": [{"message": f"YAML parse error: {str(e)}"}]})


@tool
def parse_yaml_safely(yaml_content: str) -> str:
    """Parse YAML string to JSON (dict). Preserves key order.

    Args:
        yaml_content: YAML string to parse
    """
    try:
        yaml_parser = YAML()
        yaml_parser.preserve_quotes = True
        result = yaml_parser.load(io.StringIO(yaml_content))
        def to_dict(obj):
            if hasattr(obj, "items"):
                return {k: to_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [to_dict(i) for i in obj]
            return obj
        return json.dumps({"success": True, "data": to_dict(result)}, indent=2, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def emit_yaml(spec_dict_json: str) -> str:
    """Convert a JSON/dict representation to valid YAML string.

    Args:
        spec_dict_json: JSON string representing the OpenAPI spec dict
    """
    try:
        spec_dict = json.loads(spec_dict_json)
        yaml_parser = YAML()
        yaml_parser.default_flow_style = False
        yaml_parser.preserve_quotes = True
        yaml_parser.indent(mapping=2, sequence=4, offset=2)
        stream = io.StringIO()
        yaml_parser.dump(spec_dict, stream)
        return json.dumps({"success": True, "yaml": stream.getvalue()})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def check_style_guide_rules(yaml_content: str) -> str:
    """Check YAML against IRI DFA Style Guide rules.

    Args:
        yaml_content: OpenAPI YAML content
    """
    violations = []
    warnings = []
    try:
        yaml_parser = YAML()
        spec = yaml_parser.load(io.StringIO(yaml_content))
        schemas = spec.get("components", {}).get("schemas", {})
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                prop_type = prop_def.get("type", "")
                if prop_type == "boolean":
                    if not (prop_name.startswith("is") or prop_name.startswith("has")):
                        violations.append({
                            "rule": "STYLE-001",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": f"Boolean field '{prop_name}' should start with 'is' or 'has'",
                            "severity": "warning"
                        })
                if prop_type == "array":
                    if not prop_name.endswith("s") and not prop_name.endswith("List") and not prop_name.endswith("Array"):
                        warnings.append({
                            "rule": "STYLE-002",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": f"Array field '{prop_name}' should use plural noun",
                            "severity": "warning"
                        })
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                operation = path_item.get(method, {})
                responses = operation.get("responses", {})
                for status, response in responses.items():
                    content = response.get("content", {})
                    for media_type, media_def in content.items():
                        schema = media_def.get("schema", {})
                        props = schema.get("properties", {})
                        if "correlationId" in props:
                            violations.append({
                                "rule": "STYLE-003",
                                "location": f"paths/{path}/{method}/responses/{status}",
                                "message": "correlationId should be in headers, not response body",
                                "severity": "error"
                            })
        # --- F-04: policyNumber pattern too restrictive ---
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if prop_name.lower() == "policynumber" and isinstance(prop_def, dict):
                    pat = prop_def.get("pattern", "")
                    ml = prop_def.get("maxLength")
                    if pat and pat != "":
                        violations.append({
                            "rule": "STYLE-010",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": f"policyNumber has pattern '{pat}' which is more restrictive than the cross-spec standard (minLength: 1, maxLength: 30, no character class restriction)",
                            "severity": "warning"
                        })
                    if ml and ml != 30:
                        warnings.append({
                            "rule": "STYLE-010",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": f"policyNumber maxLength is {ml}, cross-spec standard is 30",
                            "severity": "info"
                        })
        # Also check path/query parameters
        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                operation = path_item.get(method, {})
                for param in operation.get("parameters", []):
                    if isinstance(param, dict) and param.get("name", "").lower() == "policynumber":
                        ps = param.get("schema", {})
                        pat = ps.get("pattern", "")
                        if pat:
                            violations.append({
                                "rule": "STYLE-010",
                                "location": f"paths/{path}/{method}/parameters/policyNumber",
                                "message": f"policyNumber parameter has pattern '{pat}', cross-spec standard uses minLength: 1, maxLength: 30 with no pattern",
                                "severity": "warning"
                            })
            # Also check path-level parameters
            for param in path_item.get("parameters", []):
                if isinstance(param, dict) and param.get("name", "").lower() == "policynumber":
                    ps = param.get("schema", {})
                    pat = ps.get("pattern", "")
                    if pat:
                        violations.append({
                            "rule": "STYLE-010",
                            "location": f"paths/{path}/parameters/policyNumber",
                            "message": f"policyNumber parameter has pattern '{pat}', cross-spec standard uses minLength: 1, maxLength: 30 with no pattern",
                            "severity": "warning"
                        })

        # --- F-05: oneOf fields missing mutual exclusivity descriptions ---
        for schema_name, schema in schemas.items():
            one_of = schema.get("oneOf", [])
            if len(one_of) >= 2:
                # Collect all required fields across branches
                all_exclusive_fields = set()
                for branch in one_of:
                    if isinstance(branch, dict):
                        all_exclusive_fields.update(branch.get("required", []))
                # Check if the schema or its properties have descriptions about exclusivity
                props = schema.get("properties", {})
                for field_name in all_exclusive_fields:
                    if field_name in props:
                        desc = str(props[field_name].get("description", ""))
                        if not desc or ("exclusive" not in desc.lower() and "one of" not in desc.lower() and "mutually" not in desc.lower()):
                            warnings.append({
                                "rule": "STYLE-011",
                                "location": f"components/schemas/{schema_name}/properties/{field_name}",
                                "message": f"Field '{field_name}' is part of a oneOf mutual exclusivity constraint but has no description explaining when to use it vs alternatives",
                                "severity": "warning"
                            })

        # --- F-06: Conditional fields missing descriptions ---
        for schema_name, schema in schemas.items():
            all_of = schema.get("allOf", [])
            for block in all_of:
                if not isinstance(block, dict):
                    continue
                then_block = block.get("then", {})
                if not isinstance(then_block, dict):
                    continue
                then_required = then_block.get("required", [])
                props = schema.get("properties", {})
                for field_name in then_required:
                    if field_name in props:
                        desc = str(props[field_name].get("description", ""))
                        if not desc or ("required when" not in desc.lower() and "conditional" not in desc.lower()):
                            warnings.append({
                                "rule": "STYLE-012",
                                "location": f"components/schemas/{schema_name}/properties/{field_name}",
                                "message": f"Field '{field_name}' is conditionally required (via allOf/if/then) but has no description explaining the condition",
                                "severity": "warning"
                            })

        # --- F-07: Enum cross-spec inconsistency (check known field names) ---
        known_enums = {
            "assetclass": {"source": "Policy Service", "expected": ["FIXED", "VARIABLE", "INDEXED", "MODEL", "CASH", "OTHER"]},
        }
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if not isinstance(prop_def, dict):
                    continue
                key = prop_name.lower()
                if key in known_enums and "enum" in prop_def:
                    current = prop_def["enum"]
                    expected = known_enums[key]["expected"]
                    source = known_enums[key]["source"]
                    if set(current) != set(expected):
                        missing = set(expected) - set(current)
                        extra = set(current) - set(expected)
                        msg = f"'{prop_name}' enum {current} differs from {source} {expected}."
                        if missing:
                            msg += f" Missing: {list(missing)}."
                        if extra:
                            msg += f" Extra: {list(extra)}."
                        violations.append({
                            "rule": "STYLE-013",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": msg,
                            "severity": "warning"
                        })

        # --- F-08: Unconstrained string fields (known important fields) ---
        important_fields = {
            "producernumber": "Producer carrier-assigned ID",
            "npn": "National Producer Number",
            "crdnumber": "Central Registration Depository number",
            "arrangementtype": "Arrangement type — should have enum or maxLength",
            "arrangementsubtype": "Arrangement subtype — should have enum or maxLength",
        }
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if not isinstance(prop_def, dict):
                    continue
                key = prop_name.lower()
                if key in important_fields:
                    has_constraint = any(k in prop_def for k in ["maxLength", "minLength", "pattern", "enum", "format"])
                    if not has_constraint and prop_def.get("type") == "string":
                        warnings.append({
                            "rule": "STYLE-014",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": f"'{prop_name}' ({important_fields[key]}) is an unconstrained string — add maxLength, enum, or pattern",
                            "severity": "warning"
                        })

        # --- F-04: policyNumber pattern too restrictive ---
        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                operation = path_item.get(method, {})
                for param in operation.get("parameters", []):
                    p_name = param.get("name", "")
                    p_schema = param.get("schema", {})
                    if p_name.lower() == "policynumber" and "pattern" in p_schema:
                        violations.append({
                            "rule": "STYLE-010",
                            "location": f"paths/{path}/{method}/parameters/{p_name}",
                            "message": (
                                f"policyNumber pattern '{p_schema['pattern']}' is more "
                                f"restrictive than cross-spec standard (minLength: 1, maxLength: 30). "
                                f"Replace pattern with minLength/maxLength constraints."
                            ),
                            "severity": "warning"
                        })
        # Also check components/parameters
        for param_name, param_def in spec.get("components", {}).get("parameters", {}).items():
            if param_name.lower() == "policynumber" or param_def.get("name", "").lower() == "policynumber":
                p_schema = param_def.get("schema", {})
                if "pattern" in p_schema:
                    violations.append({
                        "rule": "STYLE-010",
                        "location": f"components/parameters/{param_name}",
                        "message": (
                            f"policyNumber pattern '{p_schema['pattern']}' is more "
                            f"restrictive than cross-spec standard (minLength: 1, maxLength: 30)."
                        ),
                        "severity": "warning"
                    })

        # --- F-07: assetClass enum inconsistency ---
        iri_asset_classes = {"FIXED", "VARIABLE", "INDEXED", "MODEL", "CASH", "OTHER"}
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if prop_name.lower() == "assetclass" and "enum" in prop_def:
                    spec_enums = set(prop_def["enum"])
                    missing = iri_asset_classes - spec_enums
                    extra = spec_enums - iri_asset_classes
                    if missing or extra:
                        warnings.append({
                            "rule": "STYLE-011",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": (
                                f"assetClass enum {list(spec_enums)} differs from cross-spec "
                                f"standard {list(iri_asset_classes)}."
                                + (f" Missing: {list(missing)}." if missing else "")
                                + (f" Extra: {list(extra)}." if extra else "")
                                + " Flag for working group alignment."
                            ),
                            "severity": "warning"
                        })

        # --- F-08: Unconstrained string fields (producer, arrangement) ---
        constrained_check_fields = {
            "producernumber", "npn", "crdnumber",
            "arrangementtype", "arrangementsubtype"
        }
        for schema_name, schema in schemas.items():
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if prop_name.lower() in constrained_check_fields:
                    has_constraint = any(k in prop_def for k in ["maxLength", "enum", "pattern", "minLength"])
                    if prop_def.get("type") == "string" and not has_constraint:
                        warnings.append({
                            "rule": "STYLE-012",
                            "location": f"components/schemas/{schema_name}/properties/{prop_name}",
                            "message": (
                                f"'{prop_name}' is an unconstrained string. "
                                f"Add maxLength, enum, or pattern constraint."
                            ),
                            "severity": "warning"
                        })

        return json.dumps({
            "violations": violations,
            "warnings": warnings,
            "total_issues": len(violations) + len(warnings),
            "style_score": max(0, 25 - len(violations) * 5 - len(warnings) * 2)
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "violations": [], "warnings": []})


@tool
def compute_dd_coverage(yaml_content: str, data_dictionary_json: str) -> str:
    """Compute Data Dictionary coverage for a YAML spec.

    Args:
        yaml_content: The OpenAPI YAML content
        data_dictionary_json: JSON array of DD field definitions
    """
    try:
        yaml_parser = YAML()
        spec = yaml_parser.load(io.StringIO(yaml_content))
        dd_fields = json.loads(data_dictionary_json)
        yaml_fields = set()
        schemas = spec.get("components", {}).get("schemas", {})
        for schema_name, schema in schemas.items():
            for prop in schema.get("properties", {}).keys():
                yaml_fields.add(prop.lower())
        for path, path_item in spec.get("paths", {}).items():
            for method in ["get", "post", "put", "patch", "delete"]:
                op = path_item.get(method, {})
                req_body = op.get("requestBody", {}).get("content", {})
                for media in req_body.values():
                    for prop in media.get("schema", {}).get("properties", {}).keys():
                        yaml_fields.add(prop.lower())
        mapped, unmapped = [], []
        for dd_field in dd_fields:
            field_name = dd_field.get("field_name", "")
            if field_name.lower() in yaml_fields:
                mapped.append(field_name)
            else:
                unmapped.append(field_name)
        dd_field_names = {f.get("field_name", "").lower() for f in dd_fields}
        yaml_only = [f for f in yaml_fields if f not in dd_field_names]
        coverage_pct = (len(mapped) / len(dd_fields) * 100) if dd_fields else 0
        dd_score = min(25, int(coverage_pct / 4))
        return json.dumps({
            "total_dd_fields": len(dd_fields),
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "unmapped_dd_fields": unmapped,
            "yaml_only_count": len(yaml_only),
            "yaml_fields_not_in_dd": list(yaml_only)[:50],
            "coverage_percentage": round(coverage_pct, 1),
            "dd_coverage_score": dd_score,
            "critical_fail": len(yaml_only) > 0
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "coverage_percentage": 0, "dd_coverage_score": 0})


@tool
def generate_scorecard(
    openapi_valid: bool, openapi_errors: int, style_score: int, style_violations: int,
    dd_coverage_score: int, dd_unmapped_count: int, yaml_only_count: int,
    has_evidence_map: bool, is_publish_ready: bool
) -> str:
    """Generate the 100-point governance scorecard. Determines PASS/FAIL/CONDITIONAL.

    Args:
        openapi_valid: True if OpenAPI 3.1 structure is valid
        openapi_errors: Count of structural errors
        style_score: Style guide score (0-25)
        style_violations: Count of style violations
        dd_coverage_score: DD coverage score (0-25)
        dd_unmapped_count: Count of unmapped DD fields
        yaml_only_count: Count of YAML fields not in DD
        has_evidence_map: True if sources are documented
        is_publish_ready: True if this is a publish-intent run
    """
    a_score = 30 if openapi_valid else max(0, 30 - openapi_errors * 10)
    a_critical = not openapi_valid
    b_score = style_score
    c_score = dd_coverage_score
    c_critical = yaml_only_count > 0
    d_score = 10 if has_evidence_map else 5
    e_score = 10 if (openapi_valid and dd_unmapped_count == 0) else 5
    total = a_score + b_score + c_score + d_score + e_score
    critical_fails = []
    if a_critical:
        critical_fails.append("OpenAPI 3.1 structural invalidity")
    if c_critical:
        critical_fails.append(f"Evidence-first violation: {yaml_only_count} fields not in DD")
    if is_publish_ready and dd_unmapped_count > 0:
        critical_fails.append(f"Publish-intent with {dd_unmapped_count} unmapped DD fields")
    if critical_fails:
        gate_result = "FAIL"
    elif total >= 85:
        gate_result = "PASS"
    elif total >= 70:
        gate_result = "CONDITIONAL PASS"
    else:
        gate_result = "FAIL"
    return json.dumps({
        "executive_summary": {"total_score": total, "gate_result": gate_result, "critical_fails": critical_fails},
        "category_scores": {
            "A_openapi_conformance": {"score": a_score, "max": 30, "critical": a_critical},
            "B_style_guide": {"score": b_score, "max": 25},
            "C_dd_coverage": {"score": c_score, "max": 25, "critical": c_critical},
            "D_evidence_traceability": {"score": d_score, "max": 10},
            "E_operational_readiness": {"score": e_score, "max": 10}
        },
        "gate_thresholds": {"PASS": ">= 85, no critical fails", "CONDITIONAL": "70-84, no critical fails", "FAIL": "< 70 OR any critical fail"}
    }, indent=2)


# ============================================================================
# MULTI-PART ASSEMBLY TOOLS
# ============================================================================
@tool
def manage_multipart_assembly(action: str, document_id: str = "", part_number: int = 0,
                               total_parts: int = 0, version_intent: str = "", content: str = "") -> str:
    """Manage multi-part YAML assembly state for large specs.

    Args:
        action: One of 'init', 'add_part', 'get_status', 'assemble', 'clear'
        document_id: Unique identifier for the YAML document
        part_number: Part number (1-indexed) when adding a part
        total_parts: Expected total parts (required for 'init')
        version_intent: ACTIVE | PREVIOUS | DRAFT | ARCHIVE (required for 'init')
        content: YAML content for this part (required for 'add_part')
    """
    global MULTIPART_STATE
    if action == "init":
        if not document_id or not total_parts or not version_intent:
            return json.dumps({"error": "init requires document_id, total_parts, and version_intent"})
        MULTIPART_STATE[document_id] = MultiPartState(
            yaml_document_id=document_id, version_intent=version_intent, expected_parts=total_parts)
        return json.dumps({"success": True, "message": f"Initialized assembly for '{document_id}' expecting {total_parts} parts"})
    elif action == "add_part":
        if document_id not in MULTIPART_STATE:
            return json.dumps({"error": f"No assembly in progress for '{document_id}'. Call init first."})
        state = MULTIPART_STATE[document_id]
        state.received_parts[part_number] = content
        received = sorted(state.received_parts.keys())
        missing = [i for i in range(1, state.expected_parts + 1) if i not in received]
        return json.dumps({"success": True, "received_parts": received, "missing_parts": missing,
                          "assembly_complete": len(missing) == 0})
    elif action == "assemble":
        if document_id not in MULTIPART_STATE:
            return json.dumps({"error": f"No assembly in progress for '{document_id}'"})
        state = MULTIPART_STATE[document_id]
        missing = [i for i in range(1, state.expected_parts + 1) if i not in state.received_parts]
        if missing:
            return json.dumps({"error": f"Cannot assemble: missing parts {missing}"})
        assembled = "\n".join(state.received_parts[i] for i in range(1, state.expected_parts + 1))
        state.assembled_yaml = assembled
        state.assembly_complete = True
        return json.dumps({"success": True, "assembly_complete": True, "document_id": document_id,
                          "total_lines": assembled.count("\n") + 1, "message": "ASSEMBLY COMPLETE."})
    elif action == "get_status":
        if document_id not in MULTIPART_STATE:
            return json.dumps({"active_assemblies": list(MULTIPART_STATE.keys())})
        state = MULTIPART_STATE[document_id]
        received = sorted(state.received_parts.keys())
        missing = [i for i in range(1, state.expected_parts + 1) if i not in received]
        return json.dumps({"document_id": document_id, "expected_parts": state.expected_parts,
                          "received_parts": received, "missing_parts": missing, "assembly_complete": state.assembly_complete})
    elif action == "clear":
        if document_id in MULTIPART_STATE:
            del MULTIPART_STATE[document_id]
        return json.dumps({"success": True, "message": f"Cleared assembly state for '{document_id}'"})
    return json.dumps({"error": f"Unknown action '{action}'"})


@tool
def get_assembled_yaml(document_id: str) -> str:
    """Retrieve the fully assembled YAML after multi-part assembly is complete.

    Args:
        document_id: The document ID used during assembly
    """
    if document_id not in MULTIPART_STATE:
        return json.dumps({"error": f"No assembly found for '{document_id}'"})
    state = MULTIPART_STATE[document_id]
    if not state.assembly_complete:
        return json.dumps({"error": "Assembly not complete"})
    return json.dumps({"success": True, "yaml": state.assembled_yaml, "version_intent": state.version_intent})


# ============================================================================
# LOOKUP TOOLS
# ============================================================================
@tool
def list_available_specs() -> str:
    """List all available IRI Digital-First Specifications with titles, versions, and endpoints."""
    results = []
    for key, spec in IRI_SPECS.items():
        info = spec.get("info", {})
        paths = list(spec.get("paths", {}).keys())
        results.append({"spec_key": key, "title": info.get("title", "N/A"),
                        "version": info.get("version", "N/A"),
                        "description": info.get("description", "")[:200], "endpoints": paths})
    return json.dumps(results, indent=2)


@tool
def get_endpoint_schema(spec_key: str, endpoint_path: str, method: str) -> str:
    """Get the full request/response schema for a specific API endpoint.

    Args:
        spec_key: The specification key (e.g., 'appstatusv2')
        endpoint_path: The API endpoint path (e.g., '/v2/application-statuses')
        method: HTTP method (get, post, put, patch, delete)
    """
    spec = IRI_SPECS.get(spec_key)
    if not spec:
        return json.dumps({"error": f"Spec '{spec_key}' not found. Available: {list(IRI_SPECS.keys())}"})
    path_item = spec.get("paths", {}).get(endpoint_path)
    if not path_item:
        return json.dumps({"error": f"Path '{endpoint_path}' not found."})
    operation = path_item.get(method.lower())
    if not operation:
        return json.dumps({"error": f"Method '{method}' not found for '{endpoint_path}'."})
    resolved = _resolve_all_refs(spec, operation)
    return json.dumps(resolved, indent=2, default=str)


@tool
def get_schema_definition(spec_key: str, schema_name: str) -> str:
    """Get a specific schema/model definition from a spec's components.

    Args:
        spec_key: The specification key (e.g., 'appstatusv2')
        schema_name: The schema name (e.g., 'ApplicationStatusDetail')
    """
    spec = IRI_SPECS.get(spec_key)
    if not spec:
        return json.dumps({"error": f"Spec '{spec_key}' not found."})
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name)
    if not schema:
        return json.dumps({"error": f"Schema '{schema_name}' not found. Available: {list(schemas.keys())}"})
    resolved = _resolve_all_refs(spec, copy.deepcopy(schema))
    return json.dumps(resolved, indent=2, default=str)


@tool
def validate_payload_against_schema(spec_key: str, schema_name: str, payload_json: str) -> str:
    """Validate a JSON payload against a specific schema definition.

    Args:
        spec_key: The specification key
        schema_name: The schema to validate against
        payload_json: The JSON payload string to validate
    """
    spec = IRI_SPECS.get(spec_key)
    if not spec:
        return json.dumps({"error": f"Spec '{spec_key}' not found."})
    schemas = spec.get("components", {}).get("schemas", {})
    schema = schemas.get(schema_name)
    if not schema:
        return json.dumps({"error": f"Schema '{schema_name}' not found."})
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {str(e)}"})
    resolved_schema = _resolve_all_refs(spec, copy.deepcopy(schema))
    _clean_for_jsonschema(resolved_schema)
    errors = []
    validator = jsonschema.Draft7Validator(resolved_schema)
    for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        errors.append({"path": ".".join(str(p) for p in error.absolute_path) or "(root)",
                       "message": error.message, "validator": error.validator})
    if not errors:
        return json.dumps({"valid": True, "message": "Payload passes validation."})
    return json.dumps({"valid": False, "error_count": len(errors), "errors": errors[:30]}, indent=2)


@tool
def list_schema_names(spec_key: str) -> str:
    """List all schema/model names defined in a spec's components.

    Args:
        spec_key: The specification key
    """
    spec = IRI_SPECS.get(spec_key)
    if not spec:
        return json.dumps({"error": f"Spec '{spec_key}' not found."})
    schemas = spec.get("components", {}).get("schemas", {})
    result = []
    for name, schema in schemas.items():
        result.append({"name": name, "type": schema.get("type", "object"),
                       "properties": list(schema.get("properties", {}).keys())[:20]})
    return json.dumps(result, indent=2)





# ============================================================================
# STRUCTURAL ANALYSIS TOOLS
# ============================================================================
@tool
def check_conditional_logic(yaml_content: str) -> str:
    """Deep structural analysis of oneOf, allOf, if/then/else conditional patterns.
    Catches issues that surface-level style checks miss:
    - if blocks missing required arrays (validators won't fire reliably)
    - oneOf branches that allow empty payloads (neither option required)
    - Child schemas with oneOf branches that depend on parent context
    - Malformed if conditions (properties as sibling instead of child)

    Args:
        yaml_content: The OpenAPI YAML content as a string
    """
    issues = []
    try:
        yaml_parser = YAML()
        spec = yaml_parser.load(io.StringIO(yaml_content))
        schemas = spec.get("components", {}).get("schemas", {})

        def _get_props(node):
            """Extract property names from a schema node."""
            if isinstance(node, dict):
                return set(node.get("properties", {}).keys())
            return set()

        def _check_if_block(schema_name, block, path):
            """Check an if/then/else block for common errors."""
            if_clause = block.get("if", {})
            then_clause = block.get("then", {})

            # Check 1: if block missing required array
            if_props = if_clause.get("properties", {})
            if_required = if_clause.get("required", [])
            if if_props and not if_required:
                # if checks property values but doesn't require those properties exist
                checked_fields = list(if_props.keys())
                issues.append({
                    "id": "COND-001",
                    "severity": "critical",
                    "schema": schema_name,
                    "path": path,
                    "issue": f"if block checks {checked_fields} but has no required array",
                    "detail": (
                        f"Without required: {checked_fields}, validators may not "
                        "trigger the then branch when the property is absent. "
                        "Add required to the if block."
                    ),
                    "fix": f"Add `required: {checked_fields}` inside the if block"
                })

            # Check 1b: if has nested properties (checking deep path) without required
            for prop_name, prop_def in if_props.items():
                if isinstance(prop_def, dict) and "properties" in prop_def:
                    nested_checked = list(prop_def.get("properties", {}).keys())
                    nested_required = prop_def.get("required", [])
                    if nested_checked and not nested_required:
                        issues.append({
                            "id": "COND-001a",
                            "severity": "critical",
                            "schema": schema_name,
                            "path": f"{path}.if.properties.{prop_name}",
                            "issue": (
                                f"Nested if checks {prop_name}.{nested_checked} "
                                "but parent if has no required for the outer property"
                            ),
                            "detail": (
                                f"The if block checks a value inside {prop_name} but "
                                f"does not require {prop_name} to exist. Validators "
                                "may skip the entire condition."
                            ),
                            "fix": f"Add `required: [{prop_name}]` to the if block"
                        })

            # Check 2: Malformed if — properties as sibling instead of child
            if "properties" in block and "if" in block:
                # properties at same level as if suggests indentation error
                issues.append({
                    "id": "COND-002",
                    "severity": "critical",
                    "schema": schema_name,
                    "path": path,
                    "issue": "properties appears as sibling of if instead of child",
                    "detail": (
                        "The properties block should be nested inside the if, "
                        "not at the same level. This is a common indentation error."
                    ),
                    "fix": "Move properties inside the if block"
                })

        def _check_one_of(schema_name, one_of_branches, schema_props, path):
            """Check oneOf branches for structural issues."""
            if not isinstance(one_of_branches, list) or len(one_of_branches) < 2:
                return

            # Collect all fields that oneOf branches constrain
            constrained_fields = set()
            for branch in one_of_branches:
                if isinstance(branch, dict):
                    for f in branch.get("required", []):
                        constrained_fields.add(f)

            # Check 3: oneOf branch that allows empty payload
            # (neither of the mutually exclusive fields required)
            for i, branch in enumerate(one_of_branches):
                if not isinstance(branch, dict):
                    continue
                branch_required = set(branch.get("required", []))
                branch_not_required = set()
                not_clause = branch.get("not", {})
                if isinstance(not_clause, dict):
                    branch_not_required = set(not_clause.get("required", []))

                # If this branch requires NONE of the constrained fields
                # and doesn't have a not clause, it's a permissive hole
                if not branch_required.intersection(constrained_fields):
                    # This branch doesn't require any of the fields other branches do
                    if not branch_not_required:
                        issues.append({
                            "id": "COND-003",
                            "severity": "critical",
                            "schema": schema_name,
                            "path": f"{path}.oneOf[{i}]",
                            "issue": (
                                f"oneOf branch {i+1} requires none of "
                                f"{sorted(constrained_fields)} — allows empty payload"
                            ),
                            "detail": (
                                f"Other branches constrain {sorted(constrained_fields)} but "
                                f"this branch requires none of them, creating a schema hole "
                                "that permits payloads with neither option."
                            ),
                            "fix": (
                                f"Remove this permissive branch or add required constraints. "
                                f"If this branch represents a parent-level condition "
                                f"(e.g., FULL_REBALANCE), move that logic to the parent schema."
                            )
                        })

            # Check 4: Child oneOf that depends on parent context
            # If a oneOf has 3+ branches and one is a "none required" escape hatch,
            # it likely depends on a parent-level condition
            if len(one_of_branches) >= 3:
                escape_branches = []
                for i, branch in enumerate(one_of_branches):
                    if isinstance(branch, dict):
                        req = branch.get("required", [])
                        not_req = branch.get("not", {}).get("required", []) if isinstance(branch.get("not"), dict) else []
                        if not req and not not_req:
                            escape_branches.append(i)
                        elif not req and not_req:
                            # Branch that only forbids fields — could be escape
                            all_forbidden = set(not_req)
                            if all_forbidden == constrained_fields:
                                escape_branches.append(i)

                if escape_branches:
                    issues.append({
                        "id": "COND-004",
                        "severity": "critical",
                        "schema": schema_name,
                        "path": path,
                        "issue": (
                            f"oneOf has {len(one_of_branches)} branches; "
                            f"branch(es) {[b+1 for b in escape_branches]} appear to be "
                            "context-dependent escape hatches"
                        ),
                        "detail": (
                            "A child schema's oneOf includes branches that only make "
                            "sense under specific parent conditions. The child has no "
                            "visibility into parent context, so these branches create "
                            "unintended permissiveness."
                        ),
                        "fix": (
                            "Remove context-dependent branches from the child oneOf. "
                            "Handle those conditions at the parent level using allOf "
                            "with if/then/else."
                        )
                    })

        # Walk all schemas
        for schema_name, schema_def in schemas.items():
            if not isinstance(schema_def, dict):
                continue

            schema_props = _get_props(schema_def)

            # Check direct oneOf on schema
            if "oneOf" in schema_def:
                _check_one_of(schema_name, schema_def["oneOf"],
                             schema_props, f"schemas/{schema_name}")

            # Check allOf blocks for if/then/else
            for i, block in enumerate(schema_def.get("allOf", [])):
                if isinstance(block, dict) and "if" in block:
                    _check_if_block(schema_name, block,
                                   f"schemas/{schema_name}/allOf[{i}]")

                # Also check nested oneOf inside allOf
                if isinstance(block, dict) and "oneOf" in block:
                    _check_one_of(schema_name, block["oneOf"],
                                 schema_props,
                                 f"schemas/{schema_name}/allOf[{i}]")

            # Check properties that themselves have oneOf
            for prop_name, prop_def in schema_def.get("properties", {}).items():
                if isinstance(prop_def, dict):
                    if "oneOf" in prop_def:
                        _check_one_of(schema_name, prop_def["oneOf"],
                                     _get_props(prop_def),
                                     f"schemas/{schema_name}/properties/{prop_name}")
                    if "items" in prop_def and isinstance(prop_def["items"], dict):
                        items = prop_def["items"]
                        if "oneOf" in items:
                            _check_one_of(schema_name, items["oneOf"],
                                         _get_props(items),
                                         f"schemas/{schema_name}/properties/{prop_name}/items")

        # Summarize
        critical = [i for i in issues if i["severity"] == "critical"]
        moderate = [i for i in issues if i["severity"] == "moderate"]

        return json.dumps({
            "total_issues": len(issues),
            "critical_count": len(critical),
            "moderate_count": len(moderate),
            "issues": issues,
            "summary": (
                f"Found {len(critical)} critical and {len(moderate)} moderate "
                f"conditional logic issues across {len(schemas)} schemas."
                if issues else
                f"No conditional logic issues found across {len(schemas)} schemas."
            )
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e), "issues": []})



# ============================================================================
# STRUCTURAL ANALYSIS TOOLS
# ============================================================================
@tool
def check_conditional_logic(yaml_content: str) -> str:
    """Deep structural analysis of oneOf, allOf, if/then/else, and conditional
    patterns in an OpenAPI spec. Catches issues that surface-level style checks miss:
    - oneOf branches that allow empty/invalid payloads (missing required on all branches)
    - if blocks without required arrays (validators may not trigger then branch)
    - Child oneOf branches that depend on parent context they cannot see
    - Malformed if conditions (properties as sibling instead of child)

    Args:
        yaml_content: The OpenAPI YAML content as a string
    """
    findings = []
    try:
        yaml_parser = YAML()
        spec = yaml_parser.load(io.StringIO(yaml_content))
        schemas = spec.get("components", {}).get("schemas", {}) or {}

        for schema_name, schema_def in schemas.items():
            if not isinstance(schema_def, dict):
                continue
            props = schema_def.get("properties", {}) or {}

            # --- CHECK 1: oneOf branches ---
            one_of = schema_def.get("oneOf", [])
            if one_of and len(one_of) >= 2:
                for i, branch in enumerate(one_of):
                    if not isinstance(branch, dict):
                        continue
                    req = branch.get("required", [])
                    has_not = "not" in branch
                    has_props = "properties" in branch

                    # Branch with no required — permissive "neither" catch-all
                    # Catches: (a) empty branches, (b) "not anyOf" branches that
                    # exclude all fields other branches require (the "neither" case)
                    if not req:
                        # Determine what fields other branches require
                        other_required = set()
                        for j, other in enumerate(one_of):
                            if j != i and isinstance(other, dict):
                                other_required.update(other.get("required", []))

                        is_neither_branch = False
                        if has_not:
                            # Check if the not block excludes the same fields
                            # other branches require (= "neither" pattern)
                            not_block = branch.get("not", {})
                            not_any_of = not_block.get("anyOf", [])
                            excluded = set()
                            for item in not_any_of:
                                if isinstance(item, dict):
                                    excluded.update(item.get("required", []))
                            # Also handle simple not: { required: [...] }
                            excluded.update(not_block.get("required", []))
                            if excluded and excluded == other_required:
                                is_neither_branch = True

                        if is_neither_branch or (not req and not has_not and not has_props):
                            findings.append({
                                "severity": "critical",
                                "rule": "STRUCT-001",
                                "location": f"components/schemas/{schema_name}/oneOf[{i}]",
                                "title": f"oneOf branch {i} allows NEITHER of the fields other branches require",
                                "detail": (
                                    f"Branch {i} in {schema_name}.oneOf matches payloads with "
                                    f"none of the expected fields ({list(other_required) if other_required else 'all'}). "
                                    f"If this represents a context-dependent case (e.g., "
                                    f"FULL_REBALANCE where no amount is needed), the child "
                                    f"schema has no visibility into the parent field that "
                                    f"controls when this case applies. Any payload can match "
                                    f"this branch regardless of parent context."
                                ),
                                "recommendation": (
                                    f"Remove this branch from {schema_name}.oneOf. Handle the "
                                    f"'neither' constraint at the parent schema level (e.g., "
                                    f"in FundTransferRequest.allOf) where the controlling "
                                    f"field (like amountType) is visible."
                                )
                            })

                    # Branch with required but check if it truly enforces exclusivity
                    if req and not has_not:
                        other_reqs = []
                        for j, other in enumerate(one_of):
                            if j != i and isinstance(other, dict):
                                other_reqs.extend(other.get("required", []))
                        overlap = set(req) & set(other_reqs)
                        if overlap:
                            findings.append({
                                "severity": "moderate",
                                "rule": "STRUCT-002",
                                "location": f"components/schemas/{schema_name}/oneOf[{i}]",
                                "title": f"oneOf branches share required fields: {list(overlap)}",
                                "detail": (
                                    f"Branches in {schema_name}.oneOf require the same "
                                    f"fields {list(overlap)}, weakening mutual exclusivity."
                                ),
                                "recommendation": "Add 'not: required: [field]' to enforce exclusivity."
                            })

            # --- CHECK 2: allOf with if/then — missing required on if ---
            all_of = schema_def.get("allOf", [])
            for i, block in enumerate(all_of):
                if not isinstance(block, dict) or "if" not in block:
                    continue
                if_block = block["if"]
                if not isinstance(if_block, dict):
                    continue

                # Check if the if block has required
                if_required = if_block.get("required", [])
                if_props = if_block.get("properties", {})

                if if_props and not if_required:
                    # if checks properties but doesn't require them
                    checked_keys = list(if_props.keys())
                    findings.append({
                        "severity": "critical",
                        "rule": "STRUCT-003",
                        "location": f"components/schemas/{schema_name}/allOf[{i}]/if",
                        "title": f"if block checks properties {checked_keys} without required",
                        "detail": (
                            f"The if block inspects {checked_keys} but does not include "
                            f"'required: {checked_keys}'. If the property is absent from "
                            f"the payload, the if condition evaluates to true by default "
                            f"in JSON Schema, causing the then branch to fire unexpectedly, "
                            f"OR validators may skip the condition entirely."
                        ),
                        "recommendation": f"Add 'required: {checked_keys}' to the if block."
                    })

                # Check for nested property checks without required
                for prop_name, prop_def in if_props.items():
                    if isinstance(prop_def, dict) and "properties" in prop_def:
                        nested_props = list(prop_def["properties"].keys())
                        nested_req = prop_def.get("required", [])
                        if nested_props and not nested_req:
                            findings.append({
                                "severity": "moderate",
                                "rule": "STRUCT-004",
                                "location": f"components/schemas/{schema_name}/allOf[{i}]/if/properties/{prop_name}",
                                "title": f"Nested if condition checks {nested_props} without required",
                                "detail": (
                                    f"The if block checks nested properties {nested_props} "
                                    f"under '{prop_name}' but does not require them."
                                ),
                                "recommendation": f"Add 'required: {nested_props}' to the nested object in the if block."
                            })

                # Check for malformed if — properties as sibling of if instead of child
                if "properties" in block and "if" in block:
                    if block["properties"] != if_block.get("properties"):
                        findings.append({
                            "severity": "critical",
                            "rule": "STRUCT-005",
                            "location": f"components/schemas/{schema_name}/allOf[{i}]",
                            "title": "properties is sibling of if instead of child",
                            "detail": (
                                "The 'properties' key appears at the same level as 'if' "
                                "instead of inside the if block. This means the if condition "
                                "is not checking any property values — it is always true."
                            ),
                            "recommendation": "Move 'properties' inside the 'if' block."
                        })

            # --- CHECK 3: Child oneOf depending on parent context ---
            for prop_name, prop_def in props.items():
                if not isinstance(prop_def, dict):
                    continue
                child_one_of = prop_def.get("oneOf", [])
                if not child_one_of:
                    # Check if it's a $ref to a schema with oneOf
                    ref = prop_def.get("$ref", "")
                    if ref:
                        ref_name = ref.split("/")[-1]
                        ref_schema = schemas.get(ref_name, {})
                        if isinstance(ref_schema, dict):
                            child_one_of = ref_schema.get("oneOf", [])
                            if child_one_of and len(child_one_of) >= 2:
                                # Check if any branch has no required — potential parent dependency
                                for bi, branch in enumerate(child_one_of):
                                    if isinstance(branch, dict) and not branch.get("required") and not branch.get("not"):
                                        findings.append({
                                            "severity": "critical",
                                            "rule": "STRUCT-006",
                                            "location": f"components/schemas/{schema_name}/properties/{prop_name} -> {ref_name}/oneOf[{bi}]",
                                            "title": f"Child schema {ref_name} oneOf branch {bi} may depend on parent context",
                                            "detail": (
                                                f"{ref_name} is used as a child property of {schema_name}. "
                                                f"Its oneOf branch {bi} has no required fields, which may "
                                                f"represent a case (like FULL_REBALANCE) that only makes "
                                                f"sense in the parent's context. The child schema cannot "
                                                f"see the parent's fields to validate this correctly."
                                            ),
                                            "recommendation": (
                                                f"Remove this branch from {ref_name}.oneOf and handle the "
                                                f"constraint at the parent ({schema_name}) level where "
                                                f"the controlling field is visible."
                                            )
                                        })

        # --- CHECK 4: 202 responses with wrong descriptions ---
        paths = spec.get("paths", {}) or {}
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in ["post", "put", "patch"]:
                op = path_item.get(method, {})
                if not isinstance(op, dict):
                    continue
                responses = op.get("responses", {})
                for status_code, resp in responses.items():
                    if str(status_code) == "202" and isinstance(resp, dict):
                        desc = str(resp.get("description", ""))
                        if desc.lower().startswith("created"):
                            findings.append({
                                "severity": "moderate",
                                "rule": "STRUCT-007",
                                "location": f"paths/{path}/{method}/responses/202",
                                "title": "202 response description says 'Created' instead of 'Accepted'",
                                "detail": "202 is 'Accepted', not 'Created'. 'Created' is the canonical description for 201.",
                                "recommendation": "Change description to 'Accepted — ...'"
                            })
                    # Also check $ref responses
                    if "$ref" in (resp if isinstance(resp, dict) else {}):
                        ref_name = resp["$ref"].split("/")[-1]
                        ref_resp = spec.get("components", {}).get("responses", {}).get(ref_name, {})
                        if isinstance(ref_resp, dict):
                            desc = str(ref_resp.get("description", ""))
                            if str(status_code) == "202" and desc.lower().startswith("created"):
                                findings.append({
                                    "severity": "moderate",
                                    "rule": "STRUCT-007",
                                    "location": f"components/responses/{ref_name}",
                                    "title": f"202 response '{ref_name}' description says 'Created' instead of 'Accepted'",
                                    "detail": "202 is 'Accepted', not 'Created'.",
                                    "recommendation": "Change description to 'Accepted — ...'"
                                })

        # --- CHECK 5: oneOf fields missing mutual exclusivity descriptions ---
        for schema_name, schema_def in schemas.items():
            if not isinstance(schema_def, dict):
                continue
            one_of = schema_def.get("oneOf", [])
            if len(one_of) >= 2:
                # Collect all required fields across branches
                all_req_fields = set()
                for branch in one_of:
                    if isinstance(branch, dict):
                        all_req_fields.update(branch.get("required", []))
                # Check if those fields have descriptions in properties
                schema_props = schema_def.get("properties", {}) or {}
                for field_name in all_req_fields:
                    field_def = schema_props.get(field_name, {})
                    if isinstance(field_def, dict) and not field_def.get("description"):
                        findings.append({
                            "severity": "moderate",
                            "rule": "STRUCT-008",
                            "location": f"components/schemas/{schema_name}/properties/{field_name}",
                            "title": f"oneOf field '{field_name}' missing mutual exclusivity description",
                            "detail": (
                                f"'{field_name}' participates in a oneOf constraint in "
                                f"{schema_name} but has no description explaining when it "
                                f"should be provided vs omitted."
                            ),
                            "recommendation": (
                                f"Add a description to '{field_name}' explaining its mutual "
                                f"exclusivity with the other oneOf fields."
                            )
                        })
                # Also check for schema-level description on oneOf schemas
                if not schema_def.get("description") and all_req_fields:
                    findings.append({
                        "severity": "minor",
                        "rule": "STRUCT-009",
                        "location": f"components/schemas/{schema_name}",
                        "title": f"Schema '{schema_name}' with oneOf lacks description",
                        "detail": (
                            f"{schema_name} uses oneOf for mutual exclusivity but has no "
                            f"schema-level description explaining the constraint."
                        ),
                        "recommendation": (
                            f"Add a description like: 'Exactly one of X or Y must be "
                            f"provided — not both.'"
                        )
                    })

        # --- CHECK 6: Conditional (if/then) fields missing descriptions ---
        for schema_name, schema_def in schemas.items():
            if not isinstance(schema_def, dict):
                continue
            all_of = schema_def.get("allOf", [])
            for i, block in enumerate(all_of):
                if not isinstance(block, dict) or "if" not in block:
                    continue
                then_block = block.get("then", {})
                if not isinstance(then_block, dict):
                    continue
                # Fields made required by then
                then_required = then_block.get("required", [])
                # Also check nested then properties
                then_props = then_block.get("properties", {}) or {}
                conditional_fields = set(then_required) | set(then_props.keys())
                # Check if these fields have descriptions in the main schema
                schema_props = schema_def.get("properties", {}) or {}
                for field_name in conditional_fields:
                    field_def = schema_props.get(field_name, {})
                    if isinstance(field_def, dict) and not field_def.get("description"):
                        findings.append({
                            "severity": "minor",
                            "rule": "STRUCT-010",
                            "location": f"components/schemas/{schema_name}/properties/{field_name}",
                            "title": f"Conditional field '{field_name}' missing description",
                            "detail": (
                                f"'{field_name}' is conditionally required via allOf[{i}] "
                                f"if/then but has no description explaining when it is "
                                f"required or forbidden."
                            ),
                            "recommendation": (
                                f"Add a description to '{field_name}' explaining the "
                                f"conditions under which it is required."
                            )
                        })

        # Summary
        critical = [f for f in findings if f["severity"] == "critical"]
        moderate = [f for f in findings if f["severity"] == "moderate"]
        minor = [f for f in findings if f["severity"] == "minor"]

        return json.dumps({
            "total_findings": len(findings),
            "critical_count": len(critical),
            "moderate_count": len(moderate),
            "minor_count": len(minor),
            "findings": findings
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e), "findings": []})


# ============================================================================
# URL FETCH TOOL
# ============================================================================
@tool
def fetch_yaml_from_url(url: str) -> str:
    """Fetch YAML/OpenAPI content from a URL (GitHub, raw links, or any public URL).
    Automatically converts GitHub blob URLs to raw content URLs.
    Use this when the user provides a link to a YAML file instead of pasting content.

    Args:
        url: URL to the YAML file. Supports:
             - GitHub blob URLs (github.com/org/repo/blob/branch/path/file.yaml)
             - Raw GitHub URLs (raw.githubusercontent.com/...)
             - Any public URL returning YAML content
    """
    try:
        original_url = url.strip()

        # Convert GitHub blob URLs to raw content URLs
        # e.g. https://github.com/org/repo/blob/main/path/file.yaml
        #   -> https://raw.githubusercontent.com/org/repo/main/path/file.yaml
        raw_url = original_url
        github_blob_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", original_url
        )
        if github_blob_match:
            org, repo, rest = github_blob_match.groups()
            raw_url = f"https://raw.githubusercontent.com/{org}/{repo}/{rest}"

        # Also handle GitHub tree URLs (less common but possible)
        github_tree_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/tree/(.+)", original_url
        )
        if github_tree_match:
            return json.dumps({
                "success": False,
                "error": "This appears to be a directory URL, not a file. Please provide a direct link to a .yaml or .yml file."
            })

        req = urllib.request.Request(raw_url, headers={"User-Agent": "IRI-Standards-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            yaml_content = resp.read().decode(charset)

        # Validate it's actually YAML/parseable
        try:
            parsed = yaml.safe_load(yaml_content)
            if not isinstance(parsed, dict):
                return json.dumps({
                    "success": False,
                    "error": "URL content parsed but is not a YAML dictionary/mapping. It may be a list or scalar."
                })
            is_openapi = "openapi" in parsed
        except yaml.YAMLError as ye:
            return json.dumps({
                "success": False,
                "error": f"URL content is not valid YAML: {str(ye)[:300]}"
            })

        # Extract metadata
        info = parsed.get("info", {}) if is_openapi else {}
        return json.dumps({
            "success": True,
            "source_url": original_url,
            "resolved_url": raw_url,
            "is_openapi": is_openapi,
            "openapi_version": parsed.get("openapi", "N/A") if is_openapi else "N/A",
            "title": info.get("title", "N/A"),
            "version": info.get("version", "N/A"),
            "line_count": yaml_content.count("\n") + 1,
            "char_count": len(yaml_content),
            "yaml_content": yaml_content
        })

    except urllib.error.HTTPError as e:
        return json.dumps({
            "success": False,
            "error": f"HTTP {e.code}: {e.reason}. Check that the URL is correct and the file is publicly accessible."
        })
    except urllib.error.URLError as e:
        return json.dumps({
            "success": False,
            "error": f"URL error: {str(e.reason)}. Check network connectivity and URL format."
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Failed to fetch URL: {str(e)[:300]}"
        })

@tool
def fetch_data_dictionary(url: str, sheet_name: str = "", field_name_column: str = "") -> str:
    """Fetch a Data Dictionary Excel (.xlsx/.xls) or CSV file from a URL (GitHub, etc.)
    and return its contents as a JSON array of field definitions.
    Each row becomes a dict. The tool auto-detects the header row and normalizes column names.

    Args:
        url: URL to the Data Dictionary file (GitHub blob, raw, or any public URL)
        sheet_name: Optional Excel sheet name. If empty, uses the first sheet.
        field_name_column: Optional column name containing field names. If empty, auto-detects
                          columns containing 'field', 'name', 'property', or 'element'.
    """
    try:
        original_url = url.strip()

        # Convert GitHub blob URLs to raw
        raw_url = original_url
        github_blob_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", original_url
        )
        if github_blob_match:
            org, repo, rest = github_blob_match.groups()
            raw_url = f"https://raw.githubusercontent.com/{org}/{repo}/{rest}"

        # Download the file
        req = urllib.request.Request(raw_url, headers={"User-Agent": "IRI-Standards-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            file_bytes = resp.read()

        # Detect format from URL extension
        lower_url = raw_url.lower()
        is_csv = lower_url.endswith(".csv")
        is_excel = any(lower_url.endswith(ext) for ext in (".xlsx", ".xls", ".xlsm"))

        if not is_csv and not is_excel:
            # Try to guess from content
            try:
                file_bytes.decode("utf-8")
                is_csv = True
            except UnicodeDecodeError:
                is_excel = True

        rows = []

        if is_excel:
            try:
                import openpyxl
            except ImportError:
                return json.dumps({"success": False, "error": "openpyxl not installed. Run: pip install openpyxl"})

            # Write to temp file and parse
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
                if sheet_name:
                    if sheet_name not in wb.sheetnames:
                        return json.dumps({
                            "success": False,
                            "error": f"Sheet '{sheet_name}' not found. Available: {wb.sheetnames}"
                        })
                    ws = wb[sheet_name]
                else:
                    ws = wb.active

                # Read all rows
                all_rows = []
                for row in ws.iter_rows(values_only=True):
                    all_rows.append([str(c).strip() if c is not None else "" for c in row])
                wb.close()
            finally:
                os.unlink(tmp_path)

            if not all_rows:
                return json.dumps({"success": False, "error": "Sheet is empty"})

            # Use first non-empty row as headers
            headers = all_rows[0]
            for i, row in enumerate(all_rows):
                if any(cell for cell in row):
                    headers = row
                    all_rows = all_rows[i+1:]
                    break

            # Normalize header names
            headers = [h.strip().lower().replace(" ", "_").replace("-", "_") for h in headers]

            for row in all_rows:
                if not any(cell for cell in row):
                    continue
                record = {}
                for j, val in enumerate(row):
                    if j < len(headers) and headers[j]:
                        record[headers[j]] = val
                rows.append(record)

        elif is_csv:
            import csv
            import io as _io
            text = file_bytes.decode("utf-8-sig")
            reader = csv.reader(_io.StringIO(text))
            all_rows = list(reader)

            if not all_rows:
                return json.dumps({"success": False, "error": "CSV is empty"})

            headers = [h.strip().lower().replace(" ", "_").replace("-", "_") for h in all_rows[0]]
            for row in all_rows[1:]:
                if not any(cell.strip() for cell in row):
                    continue
                record = {}
                for j, val in enumerate(row):
                    if j < len(headers) and headers[j]:
                        record[headers[j]] = val.strip()
                rows.append(record)

        # Auto-detect field_name column
        fn_col = field_name_column.strip().lower().replace(" ", "_").replace("-", "_") if field_name_column else ""
        if not fn_col and rows:
            candidates = [k for k in rows[0].keys()
                         if any(term in k for term in ["field", "name", "property", "element", "attribute", "column"])]
            if candidates:
                fn_col = candidates[0]

        # Add normalized field_name key if we found one
        if fn_col and rows and fn_col in rows[0]:
            for row in rows:
                row["field_name"] = row.get(fn_col, "")

        return json.dumps({
            "success": True,
            "source_url": original_url,
            "format": "excel" if is_excel else "csv",
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "field_name_column": fn_col or "(not detected — set field_name_column explicitly)",
            "sample_rows": rows[:3],
            "data": rows
        })

    except urllib.error.HTTPError as e:
        return json.dumps({"success": False, "error": f"HTTP {e.code}: {e.reason}"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Failed: {str(e)[:300]}"})


# ============================================================================
# TOOL REGISTRY — Import this from agent.py
# ============================================================================
AGENT_TOOLS = [
    validate_openapi_structure,
    parse_yaml_safely,
    emit_yaml,
    check_style_guide_rules,
    compute_dd_coverage,
    generate_scorecard,
    manage_multipart_assembly,
    get_assembled_yaml,
    list_available_specs,
    get_endpoint_schema,
    get_schema_definition,
    validate_payload_against_schema,
    list_schema_names,
    check_conditional_logic,
    check_conditional_logic,
    fetch_yaml_from_url,
    fetch_data_dictionary,
]

