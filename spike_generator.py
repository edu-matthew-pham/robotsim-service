from typing import Any, Dict, List, Set
import io
import tokenize
from typing import Tuple
from spike_translation_config import (
    MOTOR_CONFIG,
    MOTOR_MAPPING,
    SENSOR_MAPPING,
    SENSOR_TRANSLATIONS,
    SENSOR_IMPORTS,
    EDUCATIONAL_NOTES,
    GENERATION_CONFIG,
    get_motor_port,
    is_motor_reversed,
    get_sensor_port,
)

class SpikeCodeGenerator:
    """Generates Spike Prime Python code from parsed instructions."""
    
    def __init__(self, config_overrides: Dict[str, Any] = None):
        self.indent_level = 0
        self.indent_str = "    "
        self._standalone = set()
        self._inline = {}
        self._src_lines = []
        self.config = {**GENERATION_CONFIG, **(config_overrides or {})}
        
    def generate(self, instructions: List[Dict[str, Any]], src: str) -> str:
        """Generate complete Spike Prime code from instructions."""
        self._standalone, self._inline, self._src_lines = self._collect_comments(src)

        lines: List[str] = []
        
        # Add standard Spike Prime imports
        lines.append("from hub import light_matrix, port")
        lines.append("import runloop")
        lines.append("import motor")
        
        # Track which components are actually used
        used_motors = self._get_used_motors(instructions)
        uses_color = self._uses_sensor(instructions, "color_sensor")
        uses_distance = self._uses_sensor(instructions, "distance_sensor")
        uses_ir = self._uses_sensor(instructions, "ir_sensor")
        uses_gyro = self._uses_sensor(instructions, "gyro_sensor")
        
        # Add sensor-specific imports
        if uses_color and SENSOR_IMPORTS["color_sensor"]:
            lines.append(SENSOR_IMPORTS["color_sensor"])
        if uses_distance and SENSOR_IMPORTS["distance_sensor"]:
            lines.append(SENSOR_IMPORTS["distance_sensor"])
        if uses_gyro and SENSOR_IMPORTS["gyro_sensor"]:
            lines.append(SENSOR_IMPORTS["gyro_sensor"])
        if uses_ir and SENSOR_IMPORTS["ir_sensor"]:  # Add this line
            lines.append(SENSOR_IMPORTS["ir_sensor"])  # Add this line
        
        # Add IR sensor educational notes if used
        if uses_ir:
            lines.append("")
            lines.extend(EDUCATIONAL_NOTES["ir_sensor"].strip().split("\n"))
        
        # Add helper functions for motor control
        if used_motors and self.config.get("convert_percent_to_dps"):
            max_speed = MOTOR_CONFIG["max_speed_dps"]
            lines.append("")
            lines.append("# Helper function for motor control")
            lines.append("def percent_to_dps(percent, reversed=False):")
            lines.append(f"    \"\"\"Convert -100 to 100% to degrees per second, applying direction.\"\"\"")
            lines.append(f"    # Clamp to -100 to 100 range")
            lines.append(f"    speed = int(max(-100, min(100, percent)) * {max_speed} / 100)")
            lines.append("    return -speed if reversed else speed")
        
        # Add distance sensor helper if used
        if uses_distance and self.config.get("include_distance_helper", True):
            lines.append("")
            lines.extend(EDUCATIONAL_NOTES["distance_sensor_helper"].strip().split("\n"))
            lines.append("def get_distance():")
            lines.append("    \"\"\"Get distance in cm, returns 200 when nothing detected.\"\"\"")
            lines.append("    dist = distance_sensor.distance(DISTANCE_SENSOR)")
            lines.append("    if dist == -1:")
            lines.append("        return 200")
            lines.append("    return dist / 10")
        
        lines.append("")
        
        # Add port configuration note
        if self.config.get("include_port_config_note"):
            lines.extend(EDUCATIONAL_NOTES["port_configuration"].strip().split("\n"))
            lines.append("")
        
        # Generate port assignments and reversed flags for used motors
        lines.append("# Motor configuration")
        for motor_name in sorted(used_motors):
            port_val = get_motor_port(motor_name)
            reversed_flag = is_motor_reversed(motor_name)
            const_name = motor_name.upper()
            lines.append(f"{const_name} = {port_val}")
            lines.append(f"{const_name}_REVERSED = {reversed_flag}")
        
        # Generate sensor port assignments
        if uses_color or uses_distance or uses_ir:
            lines.append("")
            lines.append("# Sensor configuration")
        if uses_color:
            lines.append(f"COLOR_SENSOR = {get_sensor_port('color_sensor')}")
        if uses_distance:
            lines.append(f"DISTANCE_SENSOR = {get_sensor_port('distance_sensor')}")
        if uses_ir:
            lines.append(f"IR_SEEKER_PORT = {get_sensor_port('ir_seeker')}")
        
        lines.append("")
        lines.append("async def main():")
        
        # Emit code with comments interleaved
        self.indent_level = 1
        block_indent = self.indent_str * self.indent_level
        
        out: List[str] = []
        cursor = 1

        instrs = sorted(instructions, key=lambda d: (d.get("lineno") or 10**9, d.get("end_lineno") or 10**9))
        
        def emit_standalone_until(line_exclusive: int):
            nonlocal cursor
            while cursor < line_exclusive and cursor <= len(self._src_lines):
                if cursor in self._standalone:
                    out.append(block_indent + self._src_lines[cursor - 1].lstrip())
                cursor += 1

        for instr in instrs:
            L = instr.get("lineno") or cursor
            emit_standalone_until(L)
            
            emitted = self._generate_instruction(instr)
            if emitted:
                if L in self._inline:
                    emitted[-1] = emitted[-1] + "  " + "  ".join(self._inline[L])
                out.extend(emitted)

            cursor = max(cursor, (instr.get("end_lineno") or L) + 1)

        emit_standalone_until(len(self._src_lines) + 1)

        lines.extend(out)
        lines.append("")
        lines.append("runloop.run(main())")
        return "\n".join(lines)
    
    def _get_used_motors(self, instructions: List[Dict[str, Any]]) -> Set[str]:
        """Get set of all motor names used in instructions."""
        used = set()
        for instr in instructions:
            if instr.get("type") in ["motor_start", "motor_stop"]:
                motor_name = instr.get("motor", "")
                if motor_name:
                    used.add(motor_name)
            
            # Recursively check nested structures
            if instr.get("type") in ["for", "while", "if", "function_def"]:
                used.update(self._get_used_motors(instr.get("body", [])))
                used.update(self._get_used_motors(instr.get("orelse", [])))
        
        return used
    
    def _has_await(self, instructions: List[Dict[str, Any]]) -> bool:
        """Check if any instruction in a block uses await (wait, motor ops, etc.)"""
        for instr in instructions:
            if instr.get("type") in ["wait", "motor_start"]:
                return True
            # Check nested blocks
            if instr.get("type") in ["for", "while", "if", "function_def"]:
                if self._has_await(instr.get("body", [])):
                    return True
                if self._has_await(instr.get("orelse", [])):
                    return True
            # Check function calls - if calling a user function, assume it might be async
            if instr.get("type") == "function_call":
                return True
        return False
    
    def _generate_instruction(self, instr: Dict[str, Any]) -> List[str]:
        """Generate code for a single instruction."""
        lines = []
        indent = self.indent_str * self.indent_level
        
        instr_type = instr.get("type")
        
        if instr_type == "motor_start":
            motor_name = instr["motor"]
            const_name = motor_name.upper()
            
            if "speed" in instr:
                speed = instr["speed"]
                
                if self.config.get("convert_percent_to_dps"):
                    lines.append(f"{indent}motor.run({const_name}, percent_to_dps({speed}, {const_name}_REVERSED))")
                else:
                    lines.append(f"{indent}motor.run({const_name}, apply_direction({speed}, {const_name}_REVERSED))")
                    
            elif "speed_expr" in instr:
                expr = self._translate_expression(instr["speed_expr"])
                
                if self.config.get("convert_percent_to_dps"):
                    lines.append(f"{indent}motor.run({const_name}, percent_to_dps({expr}, {const_name}_REVERSED))")
                else:
                    lines.append(f"{indent}motor.run({const_name}, apply_direction(int({expr}), {const_name}_REVERSED))")
        
        elif instr_type == "motor_stop":
            motor_name = instr["motor"]
            const_name = motor_name.upper()
            lines.append(f"{indent}motor.stop({const_name})")
        
        elif instr_type == "wait":
            if "seconds" in instr:
                seconds = instr["seconds"]
                ms = int(seconds * 1000)
                lines.append(f"{indent}await runloop.sleep_ms({ms})")
            elif "seconds_expr" in instr:
                expr = self._translate_expression(instr["seconds_expr"])
                lines.append(f"{indent}await runloop.sleep_ms(int({expr} * 1000))")
        
        elif instr_type == "print":
            if "message" in instr:
                msg = instr["message"]
                lines.append(f"{indent}print({repr(msg)})")
            elif "expression" in instr:
                expr = self._translate_expression(instr["expression"])
                lines.append(f"{indent}print({expr})")
        
        elif instr_type == "assign":
            var = instr["variable"]
            expr = self._translate_expression(instr["expression"])
            
            # Check if expression looks like a function call (contains parentheses and not a known sensor/built-in)
            if "(" in expr and not any(sensor in expr for sensor in ["get_distance", "get_color", "get_reflected_light", "get_angle", "get_rate", "range"]):
                # It's likely a user function call - add await
                lines.append(f"{indent}{var} = await {expr}")
            else:
                lines.append(f"{indent}{var} = {expr}")
        
        elif instr_type == "for":
            target = instr["target"]
            iter_expr = self._translate_expression(instr["iter"])
            lines.extend(self._emit_block(f"for {target} in {iter_expr}:", instr))
        
        elif instr_type == "while":
            condition = self._translate_expression(instr["condition"])
            lines.extend(self._emit_block(f"while {condition}:", instr))
        
        elif instr_type == "if":
            condition = self._translate_expression(instr["condition"])
            lines.extend(self._emit_block(f"if {condition}:", instr, body_key="body"))
            
            if "orelse" in instr and instr["orelse"]:
                lines.append(f"{indent}else:")
                self.indent_level += 1
                for else_instr in instr["orelse"]:
                    lines.extend(self._generate_instruction(else_instr))
                self.indent_level -= 1
        
        elif instr_type == "break":
            lines.append(f"{indent}break")
        
        elif instr_type == "function_def":
            name = instr["name"]
            params = ", ".join(instr["params"])
            # Check if function needs to be async
            #is_async = self._has_await(instr.get("body", []))
            is_async = True
            header = f"async def {name}({params}):" if is_async else f"def {name}({params}):"
            lines.extend(self._emit_block(header, instr))
            lines.append("")
        
        elif instr_type == "return":
            if instr.get("value") is not None:
                lines.append(f"{indent}return {repr(instr['value'])}")
            elif "expression" in instr:
                expr = self._translate_expression(instr["expression"])
                lines.append(f"{indent}return {expr}")
            else:
                lines.append(f"{indent}return")
        
        elif instr_type == "function_call":
            name = instr["name"]
            args = []
            for arg in instr.get("args", []):
                if arg["type"] == "constant":
                    args.append(repr(arg["value"]))
                else:
                    args.append(self._translate_expression(arg["value"]))
            # Add await for function calls (assume user functions might be async)
            lines.append(f"{indent}await {name}({', '.join(args)})")
        
        return lines
    
    def _translate_expression(self, expr: str) -> str:
        """Translate expressions to Spike Prime equivalents."""
        result = expr
        for old, new in SENSOR_TRANSLATIONS.items():
            result = result.replace(old, new)
        return result
    
    def _collect_comments(self, src: str) -> Tuple[set, Dict[int, List[str]], List[str]]:
        """Collect standalone and inline comments from source."""
        standalone = set()
        inline: Dict[int, List[str]] = {}
        src_lines = src.splitlines()
        if not src:
            return standalone, inline, src_lines
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            ln = tok.start[0]
            text = tok.string
            if tok.line.strip().startswith('#') and tok.line.strip() == text.strip():
                standalone.add(ln)
            else:
                inline.setdefault(ln, []).append(text)
        return standalone, inline, src_lines
    
    def _uses_sensor(self, instructions: List[Dict[str, Any]], sensor_name: str) -> bool:
        """Check if any instruction uses a specific sensor."""
        for instr in instructions:
            if instr.get("type") in ["ir_direction", "ir_strength"] and sensor_name == "ir_sensor":
                return True
            
            for key in ["expression", "speed_expr", "seconds_expr", "condition", "iter"]:
                if key in instr and sensor_name in str(instr[key]):
                    return True
            
            if instr.get("type") in ["for", "while", "if", "function_def"]:
                if self._uses_sensor(instr.get("body", []), sensor_name):
                    return True
                if self._uses_sensor(instr.get("orelse", []), sensor_name):
                    return True
        
        return False
    
    def _emit_block(self, header_line: str, instr, body_key: str = "body") -> list[str]:
        """Emit a compound block with proper comment interleaving."""
        out: list[str] = []
        indent = self.indent_str * self.indent_level
        out.append(f"{indent}{header_line}")

        self.indent_level += 1
        block_indent = self.indent_str * self.indent_level

        block_cursor = (instr.get("lineno") or 0) + 1
        for child in instr.get(body_key, []):
            child_L = child.get("lineno") or block_cursor
            self._emit_standalone_between(out, block_cursor, child_L, block_indent)
            block_cursor = self._emit_child_instr(child, out, block_indent)

        block_end = (instr.get("end_lineno") or block_cursor)
        self._emit_standalone_between(out, block_cursor, block_end + 1, block_indent)

        self.indent_level -= 1
        return out
    
    def _emit_standalone_between(self, out, start_line: int, end_exclusive: int, indent: str) -> None:
        """Emit standalone comments between lines."""
        for ln in range(start_line, min(end_exclusive, len(self._src_lines) + 1)):
            if ln in self._standalone:
                out.append(indent + self._src_lines[ln - 1].lstrip())

    def _emit_child_instr(self, child, out, block_indent: str) -> int:
        """Emit child instruction with inline comments."""
        child_L = child.get("lineno") or 0
        child_lines = self._generate_instruction(child)
        if child_lines:
            if child_L in self._inline:
                child_lines[-1] = child_lines[-1] + "  " + "  ".join(self._inline[child_L])
            out.extend(child_lines)
        return (child.get("end_lineno") or child_L) + 1


def generate_spike_code(instructions: List[Dict[str, Any]], src: str, config_overrides: Dict[str, Any] = None) -> str:
    """Generate Spike Prime code from parsed instructions."""
    generator = SpikeCodeGenerator(config_overrides)
    return generator.generate(instructions, src)