# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ast

from parser import convert_ast_to_instructions  # <- our new module

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
