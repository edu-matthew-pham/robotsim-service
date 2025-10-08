# spike_generator.py
from typing import Any, Dict, List
import io
import tokenize
from typing import Tuple

class SpikeCodeGenerator:
    """Generates Spike Prime Python code from parsed instructions."""
    
    def __init__(self):
        self.indent_level = 0
        self.indent_str = "    "
        self._standalone = set()
        self._inline = {}
        self._src_lines = []
        
    def generate(self, instructions: List[Dict[str, Any]], src: str) -> str:
        """Generate complete Spike Prime code from instructions."""
        # Pre-scan comments
        standalone, inline, src_lines = self._collect_comments(src)
        self._standalone, self._inline, self._src_lines = self._collect_comments(src)

        lines: List[str] = []
        
        # Add standard Spike Prime imports
        lines.append("from hub import light_matrix, port")
        lines.append("import runloop")
        lines.append("import motor")
        lines.append("import motor_pair")
        
        # Track which components are actually used
        uses_motors = self._uses_motors(instructions)
        uses_color = self._uses_sensor(instructions, "color_sensor")
        uses_distance = self._uses_sensor(instructions, "distance_sensor")
        uses_ir = self._uses_sensor(instructions, "ir_sensor")
        uses_gyro = self._uses_sensor(instructions, "gyro_sensor")
        
        if uses_color:
            lines.append("import color_sensor")
        if uses_distance:
            lines.append("import distance_sensor")
        if uses_gyro:
            lines.append("from hub import motion_sensor")
        
        # Check if IR sensor is used and add note
        if uses_ir:
            lines.append("")
            lines.append("# IR Seeker Setup:")
            lines.append("# Building Block Robotics IR Seeker appears as a distance/color sensor")
            lines.append("# Standard Mode: Use as distance sensor for direction only")
            lines.append("# Advanced Mode: Use hub.port.X.device for direction + strength")
            lines.append("# See: https://irseeker.buildingblockrobotics.com/guides/spike-prime")
        
        lines.append("")
        lines.append("# Port assignments (adjust as needed)")
        if uses_motors:
            lines.append("MOTOR_A = port.A")
            lines.append("MOTOR_B = port.B")
        if uses_color:
            lines.append("COLOR_SENSOR = port.C")
        if uses_distance:
            lines.append("DISTANCE_SENSOR = port.D")
        if uses_ir:
            lines.append("IR_SEEKER_PORT = port.E  # Appears as distance sensor in standard mode")
        
        lines.append("")
        lines.append("async def main():")
        
        
        
        # Indent and generate code for each instruction
        # Emit code with comments interleaved
        self.indent_level = 1
        block_indent = self.indent_str * self.indent_level
        
        out: List[str] = []
        cursor = 1  # 1-based source line pointer

        # sort by source order if lineno present
        instrs = sorted(instructions, key=lambda d: (d.get("lineno") or 10**9, d.get("end_lineno") or 10**9))
        
        def emit_standalone_until(line_exclusive: int):
            nonlocal cursor
            while cursor < line_exclusive and cursor <= len(src_lines):
                if cursor in standalone:
                    out.append(block_indent + src_lines[cursor - 1].lstrip())
                cursor += 1

        for instr in instrs:
            L = instr.get("lineno") or cursor

            # 1) standalone comments before this instruction
            emit_standalone_until(L)

            # 2) generate code for the instruction
            emitted = self._generate_instruction(instr)
            if emitted:
                # attach inline comments for that source line to the last emitted line
                if L in inline:
                    emitted[-1] = emitted[-1] + "  " + "  ".join(inline[L])
                out.extend(emitted)

            cursor = max(cursor, (instr.get("end_lineno") or L) + 1)

        # 3) trailing standalone comments
        emit_standalone_until(len(src_lines) + 1)

        lines.extend(out)
        lines.append("")
        lines.append("runloop.run(main())")
        return "\n".join(lines)

    
    # NEW: collect comments
    def _collect_comments(self, src: str) -> Tuple[set, Dict[int, List[str]], List[str]]:
        standalone = set()
        inline: Dict[int, List[str]] = {}
        src_lines = src.splitlines()
        if not src:
            return standalone, inline, src_lines
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            ln = tok.start[0]
            text = tok.string  # includes leading '#'
            # Entire line is a comment?
            if tok.line.strip().startswith('#') and tok.line.strip() == text.strip():
                standalone.add(ln)
            else:
                inline.setdefault(ln, []).append(text)
        return standalone, inline, src_lines
    
    def _uses_motors(self, instructions: List[Dict[str, Any]]) -> bool:
        """Check if any instruction uses motors."""
        for instr in instructions:
            if instr.get("type") in ["motor_start", "motor_stop"]:
                return True
            if instr.get("type") in ["for", "while", "if", "function_def"]:
                if self._uses_motors(instr.get("body", [])):
                    return True
                if self._uses_motors(instr.get("orelse", [])):
                    return True
        return False
    
    def _uses_sensor(self, instructions: List[Dict[str, Any]], sensor_name: str) -> bool:
        """Check if any instruction uses a specific sensor."""
        for instr in instructions:
            # Check if this instruction type directly indicates sensor usage
            if instr.get("type") in ["ir_direction", "ir_strength"] and sensor_name == "ir_sensor":
                return True
            
            # Check in expression fields
            for key in ["expression", "speed_expr", "seconds_expr", "condition", "iter"]:
                if key in instr and sensor_name in str(instr[key]):
                    return True
            
            # Recursively check nested body and orelse
            if instr.get("type") in ["for", "while", "if", "function_def"]:
                if self._uses_sensor(instr.get("body", []), sensor_name):
                    return True
                if self._uses_sensor(instr.get("orelse", []), sensor_name):
                    return True
        
        return False
    
    def _generate_instruction(self, instr: Dict[str, Any]) -> List[str]:
        """Generate code for a single instruction."""
        lines = []
        indent = self.indent_str * self.indent_level
        
        instr_type = instr.get("type")
        
        if instr_type == "motor_start":
            motor = instr["motor"]
            if "speed" in instr:
                speed = instr["speed"]
                lines.append(f"{indent}motor.run(MOTOR_{motor.upper()}, int({speed}))")
            elif "speed_expr" in instr:
                expr = self._translate_expression(instr["speed_expr"])
                lines.append(f"{indent}motor.run(MOTOR_{motor.upper()}, int({expr}))")
        
        elif instr_type == "motor_stop":
            motor = instr["motor"]
            lines.append(f"{indent}motor.stop(MOTOR_{motor.upper()})")
        
        elif instr_type == "wait":
            if "seconds" in instr:
                seconds = instr["seconds"]
                # Convert to milliseconds for runloop.sleep_ms
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
            lines.extend(self._emit_block(f"def {name}({params}):", instr))
            lines.append("")  # Blank line after function
        
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
            lines.append(f"{indent}{name}({', '.join(args)})")
        
        return lines
    
    def _translate_expression(self, expr: str) -> str:
        """Translate expressions to Spike Prime equivalents."""
        # Map sensor methods to Spike Prime API
        translations = {
            "distance_sensor.get_distance()": "distance_sensor.distance(DISTANCE_SENSOR)",
            "distance_sensor.get_distance_cm()": "distance_sensor.distance(DISTANCE_SENSOR) / 10",
            "color_sensor.get_reflected_light()": "color_sensor.reflection(COLOR_SENSOR)",
            "color_sensor.get_color()": "color_sensor.color(COLOR_SENSOR)",
            # IR sensor - Building Block Robotics IR Seeker (works out of box)
            # Standard mode: appears as distance sensor, returns direction 0-12
            "ir_sensor.get_direction()": "distance_sensor.distance(IR_SEEKER_PORT)",
            # Advanced mode for strength - requires raw device access
            "ir_sensor.get_strength()": "IR_SEEKER_PORT.device.get()[2]",
            "gyro_sensor.get_angle()": "motion_sensor.tilt_angles()[0]",
            "gyro_sensor.get_rate()": "motion_sensor.angular_velocity(motion_sensor.YAW)",
        }
        
        result = expr
        for old, new in translations.items():
            result = result.replace(old, new)
        
        return result
    
    def _emit_block(self, header_line: str, instr, body_key: str = "body") -> list[str]:
        """
        Emit a compound block:
        1) header line (e.g., 'while cond:' / 'if cond:' / 'def f():')
        2) interleave standalone comments between children
        3) emit children with inline comments
        Uses instr.lineno/end_lineno when available.
        """
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
        """Emit standalone '#…' lines in [start_line, end_exclusive), indented for this block."""
        for ln in range(start_line, min(end_exclusive, len(self._src_lines) + 1)):
            if ln in self._standalone:
                out.append(indent + self._src_lines[ln - 1].lstrip())

    def _emit_child_instr(self, child, out, block_indent: str) -> int:
        """Emit one child instruction + attach inline comments. Returns child end line + 1."""
        child_L = child.get("lineno") or 0
        child_lines = self._generate_instruction(child)
        if child_lines:
            # attach inline comments to the last emitted line for child_L
            if child_L in self._inline:
                child_lines[-1] = child_lines[-1] + "  " + "  ".join(self._inline[child_L])
            out.extend(child_lines)
        return (child.get("end_lineno") or child_L) + 1


# Helper function for the endpoint
def generate_spike_code(instructions: List[Dict[str, Any]], src: str) -> str:
    """Generate Spike Prime code from parsed instructions."""
    generator = SpikeCodeGenerator()
    return generator.generate(instructions, src)




