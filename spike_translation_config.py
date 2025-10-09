"""Configuration for translating RoboHub API to Spike Prime Python."""

# Motor speed settings
MOTOR_CONFIG = {
    "max_speed_dps": 720,
    "default_speed_dps": 360,
    "min_speed_dps": 0,
    "speed_presets": {
        "slow": 180,
        "medium": 360,
        "fast": 720,
    }
}

# Motor mapping: Abstract motor names -> Spike Prime ports + direction
MOTOR_MAPPING = {
    # Differential drive robots (2 motors)
    "motor_left": {
        "port": "port.A",
        "reversed": False,
    },
    "motor_right": {
        "port": "port.B",
        "reversed": False,
    },
    
    # Omniwheel robots (4 motors)
    "motor_fl": {
        "port": "port.A",
        "reversed": False,
    },
    "motor_fr": {
        "port": "port.B",
        "reversed": False,
    },
    "motor_bl": {
        "port": "port.C",
        "reversed": False,
    },
    "motor_br": {
        "port": "port.D",
        "reversed": False,
    },
    
    # Legacy support (backwards compatibility)
    "motor_a": {
        "port": "port.A",
        "reversed": False,
    },
    "motor_b": {
        "port": "port.B",
        "reversed": False,
    },
    "motor_c": {
        "port": "port.C",
        "reversed": False,
    },
    "motor_d": {
        "port": "port.D",
        "reversed": False,
    },
}

# Sensor mapping
SENSOR_MAPPING = {
    "color_sensor": "port.E",
    "distance_sensor": "port.F",
    "ir_seeker": "port.C",
}

def get_motor_port(motor_name: str) -> str:
    """Get Spike Prime port for abstract motor name."""
    if motor_name in MOTOR_MAPPING:
        return MOTOR_MAPPING[motor_name]["port"]
    return "port.A"

def is_motor_reversed(motor_name: str) -> bool:
    """Check if motor should run in reverse."""
    if motor_name in MOTOR_MAPPING:
        return MOTOR_MAPPING[motor_name]["reversed"]
    return False

def get_sensor_port(sensor_name: str) -> str:
    """Get Spike Prime port for abstract sensor name."""
    return SENSOR_MAPPING.get(sensor_name, "port.E")

# API translation mappings

SENSOR_IMPORTS = {
    "color_sensor": "import color_sensor",
    "distance_sensor": "import distance_sensor",
    "gyro_sensor": "from hub import motion_sensor",
    "ir_sensor": None,
}

# Update SENSOR_TRANSLATIONS
SENSOR_TRANSLATIONS = {
    "distance_sensor.get_distance()": "get_distance()",  # Returns cm (Word Blocks compatible)
    "distance_sensor.get_distance_cm()": "get_distance()",  # Explicit cm version (same)
    "color_sensor.get_reflected_light()": "color_sensor.reflection(COLOR_SENSOR)",
    "color_sensor.get_color()": "color_sensor.color(COLOR_SENSOR)",
    "ir_sensor.get_direction()": "distance_sensor.distance(IR_SEEKER_PORT)",
    "ir_sensor.get_strength()": "IR_SEEKER_PORT.device.get()[2]",
    "gyro_sensor.get_angle()": "motion_sensor.tilt_angles()[0]",
    "gyro_sensor.get_rate()": "motion_sensor.angular_velocity(motion_sensor.YAW)",
}

# Update EDUCATIONAL_NOTES
EDUCATIONAL_NOTES = {
    "ir_sensor": """
# IR Seeker Setup:
# Building Block Robotics IR Seeker appears as a distance/color sensor
# Standard Mode: Use as distance sensor for direction only
# Advanced Mode: Use hub.port.X.device for direction + strength
# See: https://irseeker.buildingblockrobotics.com/guides/spike-prime""",
    
    "port_configuration": """
# IMPORTANT: Configure ports and directions below to match your robot
# If a motor runs backwards, change its REVERSED flag to True""",
    
"distance_sensor_helper": """
# Distance sensor helper: Returns distance in cm (like Word Blocks)
# Spike Prime Python returns mm and -1 when nothing detected
# We convert to cm and return 200 when nothing detected"""
}

# Add to GENERATION_CONFIG
GENERATION_CONFIG = {
    "include_speed_explanation": False,
    "convert_percent_to_dps": True,
    "add_type_hints": False,
    "include_port_config_note": True,
    "use_single_helper": True,
    "include_distance_helper": True,  # NEW: Include distance sensor helper
}