from __future__ import annotations

from typing import Any, Dict, Optional, Type, List, get_args, get_origin
from pydantic import BaseModel
from enum import Enum


def _map_type_json(py_type: Any) -> Dict[str, Any]:
    origin = get_origin(py_type)
    args = get_args(py_type)
    if origin in (list, List):
        item_type = args[0] if args else Any
        return {"type": "array", "items": _map_type_json(item_type)}
    if isinstance(py_type, type) and issubclass(py_type, Enum):
        try:
            values = [m.value for m in py_type]
        except Exception:
            values = [str(m) for m in py_type]
        return {"type": "enum", "enum": values}
    if py_type is str:
        return {"type": "string"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "float"}
    if py_type is bool:
        return {"type": "boolean"}
    if py_type is dict:
        return {"type": "object"}
    return {"type": "string"}


def _json_constraints(prop: Dict[str, Any], field_info: Any) -> None:
    min_len = getattr(field_info, "min_length", None) or getattr(field_info, "min_items", None)
    max_len = getattr(field_info, "max_length", None) or getattr(field_info, "max_items", None)
    if prop.get("type") == "string":
        if min_len is not None:
            prop["minLength"] = int(min_len)
        if max_len is not None:
            prop["maxLength"] = int(max_len)
    ge = getattr(field_info, "ge", None)
    le = getattr(field_info, "le", None)
    gt = getattr(field_info, "gt", None)
    lt = getattr(field_info, "lt", None)
    if prop.get("type") in {"integer", "float", "number"}:
        if ge is not None:
            prop["minimum"] = float(ge)
        elif gt is not None:
            prop["minimum"] = float(gt)
        if le is not None:
            prop["maximum"] = float(le)
        elif lt is not None:
            prop["maximum"] = float(lt)
    if prop.get("type") == "array":
        items = prop.get("items", {})
        if items.get("type") == "string":
            if min_len is not None:
                items["minLength"] = int(min_len)
            if max_len is not None:
                items["maxLength"] = int(max_len)
        if items.get("type") in {"integer", "float", "number"}:
            if ge is not None:
                items["minimum"] = float(ge)
            elif gt is not None:
                items["minimum"] = float(gt)
            if le is not None:
                items["maximum"] = float(le)
            elif lt is not None:
                items["maximum"] = float(lt)
        prop["items"] = items


def emit_json_shape(model_cls: Optional[Type[BaseModel]]) -> Dict[str, Any]:
    if not model_cls:
        return {"properties": {}}

    # Pydantic v2 vs v1 compatibility
    if hasattr(model_cls, "model_fields"):
        fields = model_cls.model_fields  # type: ignore[attr-defined]
        def _iter_fields():
            for name, f in fields.items():
                yield name, getattr(f, "annotation", Any), f
        is_required = lambda f: getattr(f, "is_required", lambda: getattr(f, "required", False))()
        get_info = lambda f: getattr(f, "field_info", f)
    else:
        fields = getattr(model_cls, "__fields__", {})  # type: ignore[assignment]
        def _iter_fields():
            for name, f in fields.items():
                yield name, getattr(f, "type_", Any), f
        is_required = lambda f: getattr(f, "required", False)
        get_info = lambda f: getattr(f, "field_info", f)

    props: Dict[str, Any] = {}
    req: List[str] = []
    for name, ann, f in _iter_fields():
        prop = _map_type_json(ann)
        info = get_info(f)
        desc = getattr(info, "description", None)
        if desc:
            prop["description"] = desc
        _json_constraints(prop, info)
        # Alias support
        alias = getattr(info, "alias", None)
        json_name = alias or name
        props[json_name] = prop
        if is_required(f):
            req.append(json_name)
    out: Dict[str, Any] = {"properties": props}
    if req:
        out["required"] = req
    return out


def emit_flat_shape(model_cls: Optional[Type[BaseModel]]) -> Dict[str, Any]:
    if not model_cls:
        return {}

    if hasattr(model_cls, "model_fields"):
        fields = model_cls.model_fields  # type: ignore[attr-defined]
        def _iter_fields():
            for name, f in fields.items():
                yield name, getattr(f, "annotation", Any), f
        is_required = lambda f: getattr(f, "is_required", lambda: getattr(f, "required", False))()
        get_info = lambda f: getattr(f, "field_info", f)
    else:
        fields = getattr(model_cls, "__fields__", {})
        def _iter_fields():
            for name, f in fields.items():
                yield name, getattr(f, "type_", Any), f
        is_required = lambda f: getattr(f, "required", False)
        get_info = lambda f: getattr(f, "field_info", f)

    props: Dict[str, Any] = {}
    for name, ann, f in _iter_fields():
        v = _map_type_json(ann)
        direct: Dict[str, Any] = {"type": v.get("type", "string")}
        info = get_info(f)
        desc = getattr(info, "description", None)
        if desc:
            direct["description"] = desc
        # For arrays promote element type, mark isArray
        if v.get("type") == "array":
            items = v.get("items", {})
            direct["type"] = items.get("type", "string")
            direct["isArray"] = True
        # Constraints minimal set
        min_len = getattr(info, "min_length", None)
        max_len = getattr(info, "max_length", None)
        if min_len is not None:
            direct["minLength"] = int(min_len)
        if max_len is not None:
            direct["maxLength"] = int(max_len)
        ge = getattr(info, "ge", None)
        le = getattr(info, "le", None)
        if ge is not None:
            direct["minimum"] = float(ge)
        if le is not None:
            direct["maximum"] = float(le)
        if is_required(f):
            direct["required"] = True
        alias = getattr(info, "alias", None)
        json_name = alias or name
        props[json_name] = direct
    return props


def build_schemas(in_model: Optional[Type[BaseModel]], out_model: Optional[Type[BaseModel]]):
    return emit_json_shape(in_model), emit_json_shape(out_model)


