from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ast

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str

@app.post("/parse")
def parse_code(request: CodeRequest):
    try:
        tree = ast.parse(request.code)
        instructions = convert_ast_to_instructions(tree)
        result = {"valid": True, "error": None, "instructions": instructions}
        print("Sending response:", result)
        return result
    except SyntaxError as e:
        result = {"valid": False, "error": f"Line {e.lineno}: {e.msg}", "instructions": None}
        print("Sending error:", result)
        return result

def convert_ast_to_instructions(tree):
    """Convert Python AST to simple instruction objects"""
    instructions = []
    
    for node in tree.body:
        instr = parse_stmt(node)
        if instr:
            instructions.append(instr)
    
    return instructions

def parse_stmt(stmt):
    """Parse individual statements"""
    if isinstance(stmt, ast.Expr):
        if isinstance(stmt.value, ast.Call):
            return parse_call(stmt.value)
        elif isinstance(stmt.value, ast.Await):
            # Handle await expressions
            if isinstance(stmt.value.value, ast.Call):
                instr = parse_call(stmt.value.value)
                if instr:
                    instr["await"] = True
                return instr
    elif isinstance(stmt, ast.While):
        return parse_while(stmt)
    elif isinstance(stmt, ast.If):
        return parse_if(stmt)
    elif isinstance(stmt, ast.Break):
        return {"type": "break"}
    
    return None

def parse_call(call_node):
    """Parse function calls like motor_a.start(50)"""
    if isinstance(call_node.func, ast.Attribute):
        obj = call_node.func.value.id if isinstance(call_node.func.value, ast.Name) else None
        method = call_node.func.attr
        
        if obj in ["motor_a", "motor_b"]:
            if method == "start" and call_node.args:
                # Handle negative numbers (UnaryOp) and positive (Constant)
                arg = call_node.args[0]
                if isinstance(arg, ast.Constant):
                    speed = arg.value
                elif isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                    speed = -arg.operand.value
                else:
                    speed = 0
                
                return {"type": "motor_start", "motor": obj[-1].lower(), "speed": speed}
            elif method == "stop":
                return {"type": "motor_stop", "motor": obj[-1].lower()}
    
    elif isinstance(call_node.func, ast.Name):
        func_name = call_node.func.id
        
        if func_name == "wait" and call_node.args:
            seconds = call_node.args[0].value if isinstance(call_node.args[0], ast.Constant) else 0
            return {"type": "wait", "seconds": seconds}
        
        elif func_name == "print" and call_node.args:
            # Handle print statements
            arg = call_node.args[0]
            if isinstance(arg, ast.Constant):
                return {"type": "print", "message": arg.value}
            else:
                # For expressions, store the unparsed expression
                return {"type": "print", "expression": ast.unparse(arg)}
    
    return None

def parse_while(while_node):
    """Parse while loops"""
    body_instructions = []
    for stmt in while_node.body:
        instr = parse_stmt(stmt)
        if instr:
            body_instructions.append(instr)
    
    return {
        "type": "while",
        "condition": ast.unparse(while_node.test),
        "body": body_instructions
    }

def parse_if(if_node):
    """Parse if/elif/else statements"""
    body_instructions = []
    for stmt in if_node.body:
        instr = parse_stmt(stmt)
        if instr:
            body_instructions.append(instr)
    
    orelse_instructions = []
    if if_node.orelse:
        for stmt in if_node.orelse:
            instr = parse_stmt(stmt)
            if instr:
                orelse_instructions.append(instr)
    
    result = {
        "type": "if",
        "condition": ast.unparse(if_node.test),
        "body": body_instructions
    }
    
    # Only add orelse if it exists and has content
    if orelse_instructions:
        result["orelse"] = orelse_instructions
    
    return result