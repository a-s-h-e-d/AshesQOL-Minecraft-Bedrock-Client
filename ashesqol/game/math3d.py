"""Vectors and world->screen projection using Bedrock's camera conventions.

Bedrock yaw: 0 = south (+Z), 90 = west (-X), +/-180 = north (-Z), -90 = east (+X).
Pitch: positive = looking down.
"""
import math
from dataclasses import dataclass

NEAR_PLANE = 0.05


@dataclass(slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, o): return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)
    def __sub__(self, o): return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)
    def __mul__(self, k): return Vec3(self.x * k, self.y * k, self.z * k)
    def dot(self, o): return self.x * o.x + self.y * o.y + self.z * o.z
    def length(self): return math.sqrt(self.dot(self))
    def distance(self, o): return (self - o).length()


def facing(yaw: float) -> tuple[str, str]:
    """Cardinal direction and axis for a yaw, e.g. ('South', '+Z')."""
    index = int(((yaw % 360) + 45) // 90) % 4
    return [("South", "+Z"), ("West", "-X"), ("North", "-Z"), ("East", "+X")][index]


class Camera:
    def __init__(self, pos: Vec3, yaw: float, pitch: float, fov_y: float, width: float, height: float):
        self.pos = pos
        self.width = width
        self.height = height
        y, p = math.radians(yaw), math.radians(pitch)
        sy, cy, sp, cp = math.sin(y), math.cos(y), math.sin(p), math.cos(p)
        self.forward = Vec3(-sy * cp, -sp, cy * cp)
        self.right = Vec3(-cy, 0.0, -sy)
        self.up = Vec3(-sy * sp, cp, cy * sp)
        # pixels per unit at depth 1 (square pixels, vertical FOV)
        self.focal = (height / 2) / math.tan(math.radians(fov_y) / 2)

    def to_camera(self, p: Vec3) -> tuple[float, float, float]:
        rel = p - self.pos
        return rel.dot(self.right), rel.dot(self.up), rel.dot(self.forward)

    def project(self, p: Vec3):
        """Screen (x, y) or None if the point is behind the camera."""
        x, y, z = self.to_camera(p)
        if z < NEAR_PLANE:
            return None
        return self.width / 2 + x * self.focal / z, self.height / 2 - y * self.focal / z

    def project_edge(self, p: Vec3, margin: float = 4.0):
        """Like project(), but off-screen/behind points are pushed to the screen edge.

        Returns (x, y, on_screen).
        """
        x, y, z = self.to_camera(p)
        cx, cy = self.width / 2, self.height / 2
        if z >= NEAR_PLANE:
            sx, sy = cx + x * self.focal / z, cy - y * self.focal / z
            if margin <= sx <= self.width - margin and margin <= sy <= self.height - margin:
                return sx, sy, True
            dx, dy = sx - cx, sy - cy
        else:
            dx, dy = x, -y
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                dy = 1.0  # directly behind: point down
        half_w, half_h = cx - margin, cy - margin
        scale = min(half_w / abs(dx) if dx else math.inf, half_h / abs(dy) if dy else math.inf)
        return cx + dx * scale, cy + dy * scale, False
