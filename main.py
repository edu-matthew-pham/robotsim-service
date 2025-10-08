# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ast

from parser import convert_ast_to_instructions
from spike_generator import generate_spike_code

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
    """Parse code and return instructions."""
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

@app.post("/generate_spike")
def generate_spike_prime_code(request: CodeRequest):
    """Parse code and generate Spike Prime equivalent."""
    try:
        print(f"Received code: {request.code[:100]}...")
        
        print("Parsing AST...")
        tree = ast.parse(request.code)
        
        print("Converting to instructions...")
        instructions = convert_ast_to_instructions(tree)
        print(f"Generated {len(instructions)} instructions")
        
        print("Generating Spike Prime code...")
        spike_code = generate_spike_code(instructions, request.code)
        print(f"Generated code length: {len(spike_code)}")
        
        result = {
            "valid": True,
            "error": None,
            "instructions": instructions,
            "spike_code": spike_code
        }
        print("Sending response:", result)
        return result
    except SyntaxError as e:
        result = {
            "valid": False,
            "error": f"Line {e.lineno}: {e.msg}",
            "instructions": None,
            "spike_code": None
        }
        print("Sending syntax error:", result)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        result = {
            "valid": False,
            "error": str(e),
            "instructions": None,
            "spike_code": None
        }
        print("Generation error:", result)
        return result

@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "endpoints": {
            "/parse": "Parse code and return instructions",
            "/generate_spike": "Parse code and generate Spike Prime equivalent"
        }
    }