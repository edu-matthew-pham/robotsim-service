# parser.py
import ast
from typing import Any, Dict, List, Optional
from validator import is_numeric_expr, is_boolean_expr

def convert_ast_to_instructions(tree: ast.AST) -> List[Dict[str, Any]]:
    instructions: List[Dict[str, Any]] = []
    for node in tree.body:
        instr = parse_stmt(node)
        if instr:
            instructions.append(instr)
    return instructions

def _with_loc(d, node):
    d["lineno"] = getattr(node, "lineno", None)
    d["end_lineno"] = getattr(node, "end_lineno", d["lineno"])
    return d

def parse_stmt(stmt: ast.stmt) -> Optional[Dict[str, Any]]:
    # Keep docstrings / triple-quoted blocks as comments
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        return _with_loc({"type": "comment_block", "text": stmt.value.value}, stmt)

    if isinstance(stmt, ast.Expr):
        if isinstance(stmt.value, ast.Call):
            d = parse_call(stmt.value)
            return _with_loc(d, stmt) if d else None
        elif isinstance(stmt.value, ast.Await) and isinstance(stmt.value.value, ast.Call):
            d = parse_call(stmt.value.value)
            if d:
                d["await"] = True
                return _with_loc(d, stmt)
            return None

    elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return _with_loc({
            "type": "assign",
            "variable": stmt.targets[0].id,
            "expression": ast.unparse(stmt.value),
        }, stmt)

    elif isinstance(stmt, ast.For):
        out = parse_for(stmt);  return _with_loc(out, stmt)
    elif isinstance(stmt, ast.While):
        out = parse_while(stmt);  return _with_loc(out, stmt)
    elif isinstance(stmt, ast.If):
        out = parse_if(stmt);  return _with_loc(out, stmt)
    elif isinstance(stmt, ast.Break):
        return _with_loc({"type": "break"}, stmt)
    elif isinstance(stmt, ast.FunctionDef):
        out = parse_function(stmt);  return _with_loc(out, stmt)
    elif isinstance(stmt, ast.Return):
        out = parse_return(stmt);  return _with_loc(out, stmt)
    return None


def parse_call(call_node: ast.Call) -> Optional[Dict[str, Any]]:
    # Attribute calls: obj.method(...)
    if isinstance(call_node.func, ast.Attribute):
        obj = call_node.func.value.id if isinstance(call_node.func.value, ast.Name) else None
        method = call_node.func.attr

        # Motors
        if obj in ["motor_a", "motor_b", "motor_c", "motor_d"]:
            if method == "start" and call_node.args:
                arg = call_node.args[0]

                # Literal numbers (incl. negative literal)
                if isinstance(arg, ast.Constant):
                    return {"type": "motor_start", "motor": obj[-1].lower(), "speed": arg.value}
                if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub) and isinstance(arg.operand, ast.Constant):
                    return {"type": "motor_start", "motor": obj[-1].lower(), "speed": -arg.operand.value}

                # Validated numeric expression → evaluate at runtime in Godot
                if is_numeric_expr(arg):
                    return {"type": "motor_start", "motor": obj[-1].lower(), "speed_expr": ast.unparse(arg)}

                # Otherwise reject clearly
                raise SyntaxError("motor.start() expects a numeric expression (e.g., 50, speeds[i], x+5).")

            elif method == "stop":
                return {"type": "motor_stop", "motor": obj[-1].lower()}

        # IR sensor (kept as before—simple commands you already mapped)
        elif obj == "ir_sensor":
            if method == "get_direction":
                return {"type": "ir_direction"}
            elif method == "get_strength":
                return {"type": "ir_strength"}

    # Name calls: wait(...), print(...), user-defined functions
    elif isinstance(call_node.func, ast.Name):
        func_name = call_node.func.id

        # wait(...)
        if func_name == "wait" and call_node.args:
            arg = call_node.args[0]
            if isinstance(arg, ast.Constant):
                return {"type": "wait", "seconds": arg.value}
            if is_numeric_expr(arg):
                return {"type": "wait", "seconds_expr": ast.unparse(arg)}
            raise SyntaxError("wait() expects a numeric expression in seconds.")

        # print(...)
        elif func_name == "print":
            if len(call_node.args) == 0:
                return {"type": "print", "message": ""}
            elif len(call_node.args) == 1:
                arg = call_node.args[0]
                if isinstance(arg, ast.Constant):
                    return {"type": "print", "message": arg.value}
                else:
                    return {"type": "print", "expression": ast.unparse(arg)}
            else:
                parts = [ast.unparse(arg) for arg in call_node.args]
                return {"type": "print", "expression": " + ' ' + ".join(parts)}

        # user-defined function call
        else:
            args = []
            for arg in call_node.args:
                if isinstance(arg, ast.Constant):
                    args.append({"type": "constant", "value": arg.value})
                else:
                    args.append({"type": "expression", "value": ast.unparse(arg)})
            return {"type": "function_call", "name": func_name, "args": args}

    return None

def parse_for(for_node: ast.For) -> Dict[str, Any]:
    body = []
    for s in for_node.body:
        instr = parse_stmt(s)
        if instr:
            body.append(instr)
    return {
        "type": "for",
        "target": ast.unparse(for_node.target),
        "iter": ast.unparse(for_node.iter),
        "body": body,
    }

def parse_while(while_node: ast.While) -> Dict[str, Any]:
    # Validate the condition is a boolean expression
    if not is_boolean_expr(while_node.test):
        raise SyntaxError(f"while condition must be a boolean expression, got: {ast.unparse(while_node.test)}")
    
    body = []
    for s in while_node.body:
        instr = parse_stmt(s)
        if instr:
            body.append(instr)
    return {"type": "while", "condition": ast.unparse(while_node.test), "body": body}

def parse_if(if_node: ast.If) -> Dict[str, Any]:
    # Validate the condition is a boolean expression
    if not is_boolean_expr(if_node.test):
        raise SyntaxError(f"if condition must be a boolean expression, got: {ast.unparse(if_node.test)}")
    
    body = []
    for s in if_node.body:
        instr = parse_stmt(s)
        if instr:
            body.append(instr)

    orelse = []
    for s in if_node.orelse or []:
        instr = parse_stmt(s)
        if instr:
            orelse.append(instr)

    out = {"type": "if", "condition": ast.unparse(if_node.test), "body": body}
    if orelse:
        out["orelse"] = orelse
    return out

def parse_function(func_node: ast.FunctionDef) -> Dict[str, Any]:
    params = [a.arg for a in func_node.args.args]
    body = []
    for s in func_node.body:
        instr = parse_stmt(s)
        if instr:
            body.append(instr)
    return {"type": "function_def", "name": func_node.name, "params": params, "body": body}

def parse_return(return_node: ast.Return) -> Dict[str, Any]:
    if return_node.value is None:
        return {"type": "return", "value": None}
    if isinstance(return_node.value, ast.Constant):
        return {"type": "return", "value": return_node.value.value}
    return {"type": "return", "expression": ast.unparse(return_node.value)}