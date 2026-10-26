"""Helpers for generic types, e.g. Option<int>, Result<int, str>.

A generic type is stored as a string: "Option<int>", "Result<int, str>",
"[Option<int>]" is rejected elsewhere (arrays of structs), but the
parser here handles nested brackets and angles correctly.
"""

SCALARS = ("int", "float", "bool", "str")


def parse_generic(t):
    """Return (base, [args]) if t is a generic type, else None."""
    if not isinstance(t, str) or "<" not in t:
        return None
    depth = 0
    base_end = None
    for i, ch in enumerate(t):
        if ch == "<":
            if depth == 0:
                base_end = i
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0 and i == len(t) - 1:
                base = t[:base_end]
                inner = t[base_end + 1:-1]
                return base, split_top_level(inner)
    return None


def split_top_level(s):
    """Split s on top-level commas (ignoring nested <>, [])."""
    out = []
    depth_a = depth_b = 0
    cur = []
    for ch in s:
        if ch == "<":
            depth_a += 1
        elif ch == ">":
            depth_a -= 1
        elif ch == "[":
            depth_b += 1
        elif ch == "]":
            depth_b -= 1
        if ch == "," and depth_a == 0 and depth_b == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return [o for o in out if o]


def mangle_type(t):
    """Map a Forge type string to a valid C identifier fragment."""
    g = parse_generic(t)
    if g is not None:
        base, args = g
        return base + "_" + "_".join(mangle_type(a) for a in args)
    if t.startswith("[") and t.endswith("]"):
        return "Array_" + mangle_type(t[1:-1])
    return t


def substitute_type(t, bindings):
    """Replace type parameters in t using bindings {param: concrete}."""
    if t in bindings:
        return bindings[t]
    g = parse_generic(t)
    if g is not None:
        base, args = g
        return base + "<" + ", ".join(substitute_type(a, bindings) for a in args) + ">"
    if t.startswith("[") and t.endswith("]"):
        return "[" + substitute_type(t[1:-1], bindings) + "]"
    return t


def unify(pattern, actual, bindings, type_params):
    """Bind type params in pattern from actual; return False on clash.

    pattern may contain type params (names in type_params); actual
    must be concrete (no type params of the caller — callers check
    that before calling unify).
    """
    if pattern in type_params:
        if pattern in bindings:
            return bindings[pattern] == actual
        bindings[pattern] = actual
        return True
    g1 = parse_generic(pattern)
    g2 = parse_generic(actual)
    if g1 is not None or g2 is not None:
        if g1 is None or g2 is None or g1[0] != g2[0] or len(g1[1]) != len(g2[1]):
            return False
        return all(unify(a, b, bindings, type_params) for a, b in zip(g1[1], g2[1]))
    if pattern.startswith("[") and actual.startswith("["):
        return unify(pattern[1:-1], actual[1:-1], bindings, type_params)
    return pattern == actual


def contains_type_param(t, type_params):
    if t in type_params:
        return True
    g = parse_generic(t)
    if g is not None:
        return any(contains_type_param(a, type_params) for a in g[1])
    if t.startswith("[") and t.endswith("]"):
        return contains_type_param(t[1:-1], type_params)
    return False
