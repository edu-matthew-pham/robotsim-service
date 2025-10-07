# validator.py
import ast

# Attribute calls you allow as numeric expressions (match your executor)
ALLOWED_ATTR_CALLS = {
    "distance_sensor.get_distance",
    "distance_sensor.get_distance_cm",
    "color_sensor.get_reflected_light",
    "ir_sensor.get_direction",
    "ir_sensor.get_strength",
    "gyro_sensor.get_angle",
    "gyro_sensor.get_rate",
}

def _is_allowed_attr_call(func: ast.AST) -> bool:
    # Accept chained attributes like distance_sensor.get_distance(...)
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        dotted = ".".join(reversed(parts))
        return dotted in ALLOWED_ATTR_CALLS
    return False

def is_numeric_expr(node: ast.AST) -> bool:
    """
    True if `node` is a numeric expression we can evaluate at runtime:
    - numeric literals
    - names (variables)
    - unary +/- on numeric expr
    - binary + - * / between numeric exprs
    - subscripts (speeds[0], speeds[i]) where both base and index are numeric exprs
    - allowed sensor attribute calls (no free functions)
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float))

    if isinstance(node, ast.Name):
        return True

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return is_numeric_expr(node.operand)

    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        return is_numeric_expr(node.left) and is_numeric_expr(node.right)

    if isinstance(node, ast.Subscript):
        base_ok = is_numeric_expr(node.value)
        # Py3.9+ uses node.slice as an expr; older uses ast.Index
        sl = node.slice
        if hasattr(ast, "Index") and isinstance(sl, ast.Index):  # py<3.9 safety
            sl = sl.value
        return base_ok and is_numeric_expr(sl)

    if isinstance(node, ast.Call):
        # Only allow known sensor attribute calls (usually 0 args)
        if isinstance(node.func, ast.Attribute) and _is_allowed_attr_call(node.func):
            return all(is_numeric_expr(a) for a in node.args)
        return False

    # Parenthesized expressions fold to the inner value in Python AST, so no special case needed
    return False
