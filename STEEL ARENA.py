import sys
import os
from panda3d.core import loadPrcFileData

# Если игра запущенa из .exe, корректно прописываем путь к ресурсам Panda3D
if getattr(sys, 'frozen', False):
    basedir = sys._MEIPASS
    loadPrcFileData("", f"plugin-path {basedir}")

# Явно задаем загрузку OpenGL и отключаем поиск внешних PRC файлов
loadPrcFileData("", "load-display pandagl")
loadPrcFileData("", "win-size 1280 720")
from panda3d.core import (
    loadPrcFileData, Vec3, Point3, Quat, TransformState, Shader,
    GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Geom, GeomNode, NodePath, TextNode,
    TransparencyAttrib,
)
from panda3d.bullet import (
    BulletWorld, BulletRigidBodyNode, BulletBoxShape,
    BulletCapsuleShape, BulletConeTwistConstraint, ZUp,
)
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.DirectGui import DirectFrame, DirectButton, DirectLabel

import math
import random
import json
from pathlib import Path


loadPrcFileData("", "\n".join([
    "window-title STEEL ARENA",
    "win-size 1280 720",
    "sync-video true",
    "show-frame-rate-meter false",
    "framebuffer-multisample 1",
    "multisamples 4",
    "audio-library-name null",
]))


def clamp(x, a, b):
    return max(a, min(b, x))


def cap(vector, maximum):
    if vector.length() > maximum:
        return vector.normalized() * maximum
    return vector


def rgb(r, g, b):
    return r / 255, g / 255, b / 255, 1


def heading(angle):
    q = Quat()
    q.setFromAxisAngle(angle, Vec3(0, 0, 1))
    return q


def point_up(direction):
    z = Vec3(0, 0, 1)
    d = direction.normalized()
    axis = z.cross(d)
    q = Quat()

    if axis.length() < 0.0001:
        q.setFromAxisAngle(
            180 if d.z < 0 else 0,
            Vec3(1, 0, 0),
        )
    else:
        angle = math.degrees(math.acos(clamp(z.dot(d), -1, 1)))
        q.setFromAxisAngle(angle, axis.normalized())

    return q


def smooth(x):
    x = clamp(x, 0, 1)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------
# ПРОЦЕДУРНЫЕ МОДЕЛИ
# ------------------------------------------------------------

def geometry(faces):
    data = GeomVertexData(
        "metal",
        GeomVertexFormat.getV3n3(),
        Geom.UHStatic,
    )
    vertex = GeomVertexWriter(data, "vertex")
    normal = GeomVertexWriter(data, "normal")
    triangles = GeomTriangles(Geom.UHStatic)
    index = 0

    for points, n in faces:
        points = list(points)

        if (points[1] - points[0]).cross(
            points[2] - points[0]
        ).dot(n) < 0:
            points.reverse()

        for p in points:
            vertex.addData3(p)
            normal.addData3(n)

        for j in range(1, len(points) - 1):
            triangles.addVertices(index, index + j, index + j + 1)

        index += len(points)

    mesh = Geom(data)
    mesh.addPrimitive(triangles)

    node = GeomNode("mesh")
    node.addGeom(mesh)
    return NodePath(node)


def bevel_box():
    faces = []
    b = 0.38

    for axis in range(3):
        others = [i for i in range(3) if i != axis]

        for sign in (-1, 1):
            points = []

            for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis] = sign * 0.5
                p[others[0]] = u * b
                p[others[1]] = v * b
                points.append(Vec3(*p))

            n = [0.0, 0.0, 0.0]
            n[axis] = sign
            faces.append((points, Vec3(*n)))

    for axis in range(3):
        others = [i for i in range(3) if i != axis]

        for u in (-1, 1):
            for v in (-1, 1):
                points = []

                for t, swap in (
                    (-b, False), (b, False),
                    (b, True), (-b, True),
                ):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = t
                    p[others[0]] = u * (b if swap else 0.5)
                    p[others[1]] = v * (0.5 if swap else b)
                    points.append(Vec3(*p))

                n = [0.0, 0.0, 0.0]
                n[others[0]] = u
                n[others[1]] = v
                faces.append((points, Vec3(*n).normalized()))

    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                faces.append((
                    [
                        Vec3(x * 0.5, y * b, z * b),
                        Vec3(x * b, y * 0.5, z * b),
                        Vec3(x * b, y * b, z * 0.5),
                    ],
                    Vec3(x, y, z).normalized(),
                ))

    return geometry(faces)


def cylinder():
    faces = []
    count = 16

    for i in range(count):
        a = math.tau * i / count
        b = math.tau * (i + 1) / count

        p = Vec3(math.cos(a) * 0.5, math.sin(a) * 0.5, 0)
        q = Vec3(math.cos(b) * 0.5, math.sin(b) * 0.5, 0)

        faces.append((
            [
                p + Vec3(0, 0, -0.5),
                q + Vec3(0, 0, -0.5),
                q + Vec3(0, 0, 0.5),
                p + Vec3(0, 0, 0.5),
            ],
            Vec3(math.cos((a + b) / 2), math.sin((a + b) / 2), 0),
        ))

        faces.append((
            [
                Vec3(0, 0, 0.5),
                p + Vec3(0, 0, 0.5),
                q + Vec3(0, 0, 0.5),
            ],
            Vec3(0, 0, 1),
        ))

        faces.append((
            [
                Vec3(0, 0, -0.5),
                q + Vec3(0, 0, -0.5),
                p + Vec3(0, 0, -0.5),
            ],
            Vec3(0, 0, -1),
        ))

    return geometry(faces)


SHADER = Shader.make(
    Shader.SLGLSL,
    """
#version 140
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;

in vec4 p3d_Vertex;
in vec3 p3d_Normal;

out vec3 world_position;
out vec3 world_normal;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_position = (p3d_ModelMatrix * p3d_Vertex).xyz;
    world_normal =
        mat3(transpose(inverse(p3d_ModelMatrix))) * p3d_Normal;
}
""",
    """
#version 140
uniform vec4 p3d_ColorScale;
uniform mat4 p3d_ViewMatrixInverse;
uniform float glow;
uniform float simple;

in vec3 world_position;
in vec3 world_normal;

out vec4 fragColor;

void main() {
    vec3 n = normalize(world_normal);
    vec3 v = normalize(
        p3d_ViewMatrixInverse[3].xyz - world_position
    );

    vec3 key = normalize(vec3(-0.4, -0.6, 1.0));
    vec3 fill = normalize(vec3(0.7, 0.5, 0.3));

    float light =
        0.28
        + 0.72 * max(dot(n, key), 0.0)
        + 0.16 * max(dot(n, fill), 0.0);

    float shine = pow(
        max(dot(n, normalize(key + v)), 0.0), 38.0
    );

    float rim = pow(
        1.0 - max(dot(n, v), 0.0), 3.0
    );

    vec3 c =
        p3d_ColorScale.rgb * light
        + vec3(0.68, 0.83, 1.0)
        * (shine * 0.3 + rim * 0.06);

    c = mix(c, p3d_ColorScale.rgb, max(glow, simple));
    fragColor = vec4(c, p3d_ColorScale.a);
}
""",
)

CYAN = rgb(40, 205, 235)
ORANGE = rgb(245, 130, 65)
DARK = rgb(22, 29, 40)
METAL = rgb(95, 110, 127)


# Размеры в метрах, масса в килограммах.
SPECS = {
    "pelvis": ("box", 10, Vec3(0.54, 0.34, 0.28)),
    "torso": ("box", 15, Vec3(0.72, 0.43, 0.68)),
    "head": ("box", 4, Vec3(0.42, 0.40, 0.40)),

    "upper_l": ("capsule", 2.5, (0.13, 0.48)),
    "fore_l": ("capsule", 3.5, (0.13, 0.47)),
    "upper_r": ("capsule", 2.5, (0.13, 0.48)),
    "fore_r": ("capsule", 3.5, (0.13, 0.47)),

    "thigh_l": ("capsule", 5, (0.14, 0.47)),
    "shin_l": ("capsule", 4, (0.12, 0.47)),
    "thigh_r": ("capsule", 5, (0.14, 0.47)),
    "shin_r": ("capsule", 4, (0.12, 0.47)),

    "foot_l": ("box", 3, Vec3(0.32, 0.48, 0.22)),
    "foot_r": ("box", 3, Vec3(0.32, 0.48, 0.22)),
}

# Длительность, расход энергии, базовый урон.
MOVES = {
    "jab": (0.52, 12, 10),
    "cross": (0.68, 20, 16),
    "hook": (0.78, 24, 19),
    "uppercut": (0.82, 26, 21),
    "body": (0.64, 17, 14),
    "overhand": (0.88, 29, 23),
}

# Название, скорость ходьбы, длительность удара,
# множитель урона, восстановление равновесия.
STYLES = [
    ("BOXER", 1.0, 1.0, 1.0, 13),
    ("SWARMER", 1.12, 0.82, 0.83, 12),
    ("SLUGGER", 0.82, 1.17, 1.25, 11),
    ("COUNTER", 0.95, 0.95, 0.95, 18),
]

# Название, цвет, вариант брони.
ROBOTS = [
    ("ION", (40, 205, 235), 0),
    ("SCRAPJACK", (173, 130, 83), 1),
    ("TWINFORGE", (194, 65, 62), 2),
    ("MONARCH", (160, 110, 235), 3),
    ("GOLIATH", (220, 222, 232), 4),
    ("REDLINE", (224, 47, 66), 0),
    ("BLACK ANVIL", (75, 89, 108), 1),
    ("NEON FANG", (132, 234, 70), 3),
    ("GOLD RUSH", (233, 180, 53), 2),
    ("IRON BISON", (108, 135, 118), 4),
    ("YELLOWJACKET", (244, 195, 34), 0),
    ("ROAD CAPTAIN", (58, 110, 215), 3),
    ("GREY TYRANT", (145, 151, 165), 4),
    ("NIGHT PATROL", (73, 85, 120), 1),
    ("SKY LANCER", (182, 204, 213), 3),
    ("FIELD MEDIC", (233, 230, 187), 2),
    ("EMBER", (242, 104, 34), 4),
    ("GLACIER", (105, 200, 235), 1),
    ("VIOLET WRAITH", (151, 70, 191), 0),
    ("COPPERHEAD", (185, 110, 72), 2),
]

MAPS = [
    (
        "NEON DOCK",
        (35, 44, 57),
        (40, 205, 235),
        (0.025, 0.035, 0.055),
    ),
    (
        "FOUNDRY",
        (62, 43, 36),
        (255, 130, 42),
        (0.07, 0.035, 0.025),
    ),
    (
        "POLAR STATION",
        (62, 81, 96),
        (115, 210, 255),
        (0.085, 0.12, 0.17),
    ),
]

SAVE = Path(__file__).with_name("steel_arena_settings.json")


# ------------------------------------------------------------
# ТРАЕКТОРИИ И ФИЗИЧЕСКАЯ ПОЗА
# ------------------------------------------------------------

def punch_curve(kind, t):
    rest = Vec3(-0.40 if kind == "jab" else 0.40, 0.36, 1.78)

    if kind == "jab":
        back = Vec3(-0.48, 0.12, 1.76)
        hit = Vec3(-0.15, 1.16, 1.98)
    elif kind == "cross":
        back = Vec3(0.52, -0.18, 1.65)
        hit = Vec3(-0.06, 1.18, 1.94)
    elif kind == "hook":
        back = Vec3(0.91, 0.02, 1.85)
        hit = Vec3(-0.36, 0.79, 1.98)
    elif kind == "uppercut":
        back = Vec3(0.48, 0.03, 1.19)
        hit = Vec3(-0.10, 0.79, 2.24)
    elif kind == "body":
        back = Vec3(0.50, 0.03, 1.45)
        hit = Vec3(-0.03, 1.08, 1.42)
    else:
        back = Vec3(0.56, 0.0, 2.37)
        hit = Vec3(-0.10, 1.06, 1.94)

    # Замах.
    if t < 0.26:
        return rest + (back - rest) * smooth(t / 0.26)

    # Быстрая ударная фаза.
    if t < 0.49:
        u = smooth((t - 0.26) / 0.23)
        hand = back + (hit - back) * u

        if kind == "hook":
            hand.y += math.sin(u * math.pi) * 0.28

        return hand

    # Возврат в стойку.
    return hit + (rest - hit) * smooth((t - 0.49) / 0.51)


def elbow_between(start, end, l1, l2, pole):
    delta = end - start
    distance = clamp(delta.length(), 0.07, l1 + l2 - 0.025)

    if delta.length() > 0.001:
        axis = delta.normalized()
    else:
        axis = Vec3(0, 1, 0)

    end = start + axis * distance

    along = (
        l1 * l1 - l2 * l2 + distance * distance
    ) / (2 * distance)

    side = pole - axis * pole.dot(axis)

    if side.length() < 0.001:
        side = axis.cross(Vec3(1, 0, 0))

    middle = (
        start
        + axis * along
        + side.normalized()
        * math.sqrt(max(0, l1 * l1 - along * along))
    )

    return middle, end


def pose(
    root, yaw, phase=0, walking=False,
    attack=None, t=0, guard=False,
):
    q = heading(yaw)
    result = {}
    anchors = {}

    def point(p):
        return root + q.xform(p)

    def box(name, p):
        result[name] = (point(p), q)

    def bone(name, a, b):
        a, b = point(a), point(b)
        result[name] = ((a + b) * 0.5, point_up(b - a))

    swing = (
        math.sin(math.pi * clamp((t - 0.23) / 0.6, 0, 1))
        if attack else 0
    )

    twist = (
        (-14 if t < 0.26 else 19) * math.sin(math.pi * t)
        if attack else 0
    )

    body_q = heading(yaw + twist)
    lean = Vec3(0, 0.12 * swing, 0)

    box("pelvis", Vec3(0, 0, 1.12))
    box("torso", Vec3(0, 0, 1.62) + lean)
    result["torso"] = (result["torso"][0], body_q)
    box("head", Vec3(0, 0, 2.18) + lean)

    anchors["waist"] = point(Vec3(0, 0, 1.28))
    anchors["neck"] = point(Vec3(0, 0, 1.98) + lean)

    for side, suffix in ((-1, "l"), (1, "r")):
        shoulder = (
            heading(twist).xform(Vec3(side * 0.46, 0, 1.83))
            + lean
        )

        hand = Vec3(side * 0.40, 0.36, 1.78)

        if guard:
            hand = Vec3(side * 0.23, 0.40, 2.07)

        if attack and side == (-1 if attack == "jab" else 1):
            hand = punch_curve(attack, t)

        elbow, hand = elbow_between(
            shoulder, hand, 0.48, 0.47,
            Vec3(side * 0.8, -0.4, -0.6),
        )

        bone("upper_" + suffix, shoulder, elbow)
        bone("fore_" + suffix, elbow, hand)

        anchors["shoulder_" + suffix] = point(shoulder)
        anchors["elbow_" + suffix] = point(elbow)

        hip = Vec3(side * 0.22, 0, 1.06)
        step = math.sin(phase) * side if walking else 0

        ankle = Vec3(
            side * 0.27,
            step * 0.18,
            0.22 + max(0, step) * 0.1,
        )

        knee, ankle = elbow_between(
            hip, ankle, 0.47, 0.47, Vec3(0, 1, 0),
        )

        bone("thigh_" + suffix, hip, knee)
        bone("shin_" + suffix, knee, ankle)
        box("foot_" + suffix, ankle + Vec3(0, 0.12, -0.1))

        anchors["hip_" + suffix] = point(hip)
        anchors["knee_" + suffix] = point(knee)
        anchors["ankle_" + suffix] = point(ankle)

    return result, anchors


# ------------------------------------------------------------
# РОБОТ: ТЕЛА, СУСТАВЫ, МОТОРЫ, ПОПАДАНИЯ
# ------------------------------------------------------------

class Fighter:
    def __init__(self, game, pos, robot, yaw, style=0):
        self.game = game
        self.robot = robot
        self.style = STYLES[style]

        self.anchor = Vec3(*pos)
        self.yaw = yaw

        self.hp = 100.0
        self.energy = 100.0
        self.balance = 100.0

        self.attack = None
        self.elapsed = 0.0
        self.cooldown = 0.0
        self.down = 0.0
        self.flash = 0.0
        self.stun = 0.0
        self.phase = 0.0
        self.recover = 1.0
        self.duration = 1.0

        self.guard = False
        self.connected = False
        self.pre_velocity = Vec3(0)

        self.nodes = {}
        self.paths = {}
        self.joints = []

        self.shadow = game.part(
            game.render,
            (pos[0], pos[1], 0.006),
            (1.25, 0.85, 0.002),
            (0, 0, 0, 0.23),
            "cylinder",
            glow=True,
        )
        self.shadow.setTransparency(TransparencyAttrib.MAlpha)

        initial, anchors = pose(self.anchor, self.yaw)

        for name, (kind, mass, size) in SPECS.items():
            body = BulletRigidBodyNode(name)
            body.setMass(mass)
            body.setFriction(0.95)
            body.setRestitution(0.03)
            body.setLinearDamping(0.1)
            body.setAngularDamping(0.45)
            body.setDeactivationEnabled(False)

            if kind == "box":
                shape = BulletBoxShape(size * 0.5)
            else:
                shape = BulletCapsuleShape(
                    size[0],
                    max(0.01, size[1] - size[0] * 2),
                    ZUp,
                )

            body.addShape(shape)

            if name.startswith("fore"):
                body.addShape(
                    BulletBoxShape(Vec3(0.16, 0.16, 0.17)),
                    TransformState.makePos(
                        Vec3(0, 0, size[1] / 2)
                    ),
                )

            body.setCcdMotionThreshold(0.03)
            body.setCcdSweptSphereRadius(0.09)

            path = game.render.attachNewNode(body)
            path.setPos(initial[name][0])
            path.setQuat(initial[name][1])

            game.world.attachRigidBody(body)
            self.nodes[name] = body
            self.paths[name] = path

        self.chest_plate = game.dress(self.paths, robot)

        connections = [
            ("pelvis", "torso", "waist", 35),
            ("torso", "head", "neck", 40),
        ]

        for suffix in ("l", "r"):
            connections.extend([
                (
                    "torso", "upper_" + suffix,
                    "shoulder_" + suffix, 110,
                ),
                (
                    "upper_" + suffix, "fore_" + suffix,
                    "elbow_" + suffix, 90,
                ),
                (
                    "pelvis", "thigh_" + suffix,
                    "hip_" + suffix, 65,
                ),
                (
                    "thigh_" + suffix, "shin_" + suffix,
                    "knee_" + suffix, 65,
                ),
                (
                    "shin_" + suffix, "foot_" + suffix,
                    "ankle_" + suffix, 35,
                ),
            ])

        for a, b, anchor, limit in connections:
            pa = self.paths[a]
            pb = self.paths[b]

            qa = pa.getQuat(game.render)
            qb = pb.getQuat(game.render)
            qa.conjugateInPlace()
            qb.conjugateInPlace()

            fa = TransformState.makePosQuatScale(
                pa.getRelativePoint(
                    game.render, Point3(anchors[anchor])
                ),
                qa,
                Vec3(1),
            )

            fb = TransformState.makePosQuatScale(
                pb.getRelativePoint(
                    game.render, Point3(anchors[anchor])
                ),
                qb,
                Vec3(1),
            )

            joint = BulletConeTwistConstraint(
                self.nodes[a], self.nodes[b], fa, fb,
            )
            joint.setLimit(limit, limit, min(limit, 55))

            game.world.attachConstraint(joint, True)
            self.joints.append(joint)

    def position(self):
        return self.paths["pelvis"].getPos(self.game.render)

    def hand(self, name):
        return self.game.render.getRelativePoint(
            self.paths[name], Point3(0, 0, 0.235),
        )

    def remove(self):
        self.shadow.removeNode()

        for joint in self.joints:
            self.game.world.removeConstraint(joint)

        for name, node in self.nodes.items():
            self.game.world.removeRigidBody(node)
            self.paths[name].removeNode()

    def punch(self, kind):
        if (
            self.hp <= 0
            or self.down > 0
            or self.attack
            or self.cooldown > 0
            or self.energy < MOVES[kind][1]
        ):
            return

        self.attack = kind
        self.elapsed = 0.0
        self.connected = False
        self.duration = MOVES[kind][0] * self.style[2]
        self.cooldown = self.duration + 0.08
        self.energy -= MOVES[kind][1]

    def drive(self, dt, move, guard, other):
        self.cooldown = max(0, self.cooldown - dt)
        self.down = max(0, self.down - dt)
        self.flash = max(0, self.flash - dt)
        self.stun = max(0, self.stun - dt)

        if self.hp <= 0 or self.down > 0:
            self.attack = None
            self.recover = 0.0
            self.guard = False

            p = self.position()
            self.anchor = Vec3(p.x, p.y, 0)
            return

        self.recover = min(1, self.recover + dt * 1.8)
        self.energy = min(100, self.energy + dt * 19)
        self.balance = min(
            100, self.balance + dt * self.style[4],
        )

        delta = other.position() - self.position()

        if not self.attack:
            self.yaw = math.degrees(
                math.atan2(-delta.x, delta.y)
            )

        self.guard = (
            bool(guard)
            and not self.attack
            and self.energy > 10
        )

        move = cap(move, 1)
        speed = (1.2 if self.guard else 2.5) * self.style[1]
        self.anchor += move * dt * speed

        p = self.position()
        diff = self.anchor - Vec3(p.x, p.y, 0)

        if diff.length() > 0.42:
            self.anchor = (
                Vec3(p.x, p.y, 0) + diff.normalized() * 0.42
            )

        self.anchor.x = clamp(self.anchor.x, -4.5, 4.5)
        self.anchor.y = clamp(self.anchor.y, -4.5, 4.5)
        self.phase += dt * 8

        t = 0.0

        if self.attack:
            self.elapsed += dt
            t = min(1, self.elapsed / self.duration)

            if t >= 1:
                self.attack = None

        target, _ = pose(
            self.anchor,
            self.yaw,
            self.phase,
            move.length() > 0.1,
            self.attack,
            t,
            self.guard,
        )

        # Моторы тела и суставов.
        # После попадания сила удержания временно ослабевает.
        for name, node in self.nodes.items():
            path = self.paths[name]
            mass = SPECS[name][1]
            goal, q = target[name]

            arm = name.startswith(("upper", "fore"))
            strength = self.recover * (0.22 if self.stun else 1.0)
            stiffness = 45 if arm else 100
            damping = 6 if arm else 15

            acceleration = (
                (goal - path.getPos()) * stiffness
                - node.getLinearVelocity() * damping
                + Vec3(0, 0, 9.81)
            )

            node.applyCentralForce(
                cap(acceleration, 95) * mass * strength
            )

            current = path.getQuat()
            torque = Vec3(0)

            for axis in (Vec3(0, 0, 1), Vec3(0, 1, 0)):
                torque += (
                    current.xform(axis).cross(q.xform(axis))
                    * mass
                    * (65 if arm else 22)
                )

            torque -= (
                node.getAngularVelocity()
                * mass
                * (2.5 if arm else 3.0)
            )

            node.applyTorque(
                cap(torque, mass * 100) * strength
            )

        # Усилие прикладывается к физическому кулаку.
        # Поэтому удар может быть остановлен столкновением.
        for suffix in ("l", "r"):
            name = "fore_" + suffix
            node = self.nodes[name]
            path = self.paths[name]

            goal, q = target[name]
            target_hand = goal + q.xform(Vec3(0, 0, 0.235))
            offset = path.getQuat().xform(Vec3(0, 0, 0.235))

            velocity = (
                node.getLinearVelocity()
                + node.getAngularVelocity().cross(offset)
            )

            active = (
                self.attack
                and suffix == (
                    "l" if self.attack == "jab" else "r"
                )
            )

            if active:
                self.pre_velocity = Vec3(velocity)

            force = (
                (target_hand - self.hand(name))
                * (2200 if active else 650)
                - velocity * (55 if active else 35)
            )

            node.applyForce(
                cap(force, 1400 if active else 400)
                * self.recover,
                offset,
            )

    def check_hit(self, other):
        if (
            not self.attack
            or self.connected
            or other.hp <= 0
            or other.down > 0
        ):
            return

        if not 0.26 < self.elapsed / self.duration < 0.78:
            return

        name = "fore_l" if self.attack == "jab" else "fore_r"

        if other.guard:
            targets = (
                "fore_l", "fore_r", "head", "torso", "pelvis",
            )
        else:
            targets = ("head", "torso", "pelvis")

        for target in targets:
            hit = self.game.world.contactTestPair(
                self.nodes[name], other.nodes[target],
            )

            if not hit.getNumContacts():
                continue

            # Объекты контактов должны оставаться живыми,
            # пока читаются данные Bullet.
            contacts = hit.getContacts()
            manifold = contacts[0].getManifoldPoint()

            if manifold.getDistance() > 0.008:
                continue

            relative = (
                self.pre_velocity
                - other.nodes[target].getLinearVelocity()
            )
            speed = relative.length()

            if speed < 1.0:
                continue

            self.connected = True
            blocked = target.startswith("fore")

            damage = (
                MOVES[self.attack][2]
                * self.style[3]
                * clamp(speed / 4, 0.25, 1.6)
            )

            if target == "head":
                damage *= 1.2

            if blocked:
                other.energy = max(
                    0, other.energy - damage * 0.8,
                )
                other.balance -= damage * 0.45
                self.game.hit_text = "BLOCK"
            else:
                other.hp = max(0, other.hp - damage)
                other.balance -= damage * 2.2
                other.stun = 0.18
                other.flash = 0.14
                self.game.hit_text = (
                    f"{self.attack.upper()}  {damage:.0f}"
                )

            if other.balance <= 0 and other.hp > 0:
                other.down = 1.7
                other.balance = 65.0

            self.game.hit_time = 0.55
            self.game.spark(
                Vec3(manifold.getPositionWorldOnB())
            )
            self.game.shake = 0.015 if blocked else 0.055
            break


# ------------------------------------------------------------
# ИГРА
# ------------------------------------------------------------

class Game(ShowBase):
    def __init__(self):
        super().__init__()

        self.disableMouse()
        self.setBackgroundColor(0.025, 0.035, 0.055)
        self.camLens.setFov(55)
        self.camLens.setNearFar(0.1, 120)

        self.camera.setPos(5.8, -8.4, 4.8)
        self.camera.lookAt(0, 0, 1.1)

        self.render.setShader(SHADER)
        self.render.setShaderInput("glow", 0.0)
        self.render.setShaderInput("simple", 0.0)

        self.box = bevel_box()
        self.round = cylinder()

        self.world = BulletWorld()
        self.world.setGravity(Vec3(0, 0, -9.81))

        self.keys = {
            k: False for k in ("w", "a", "s", "d", "space")
        }

        self.simple = False
        self.ai = True
        self.accumulator = 0.0
        self.shake = 0.0
        self.particles = []
        self.fighters = []
        self.ai_timer = 0.5
        self.finished = False
        self.elapsed = 0.0

        self.selected = 0
        self.style_id = 0
        self.map_id = 0
        self.last_enemy = -1

        self.screen = "menu"
        self.widgets = []
        self.preview = None
        self.arena = None
        self.static = []

        self.hit_text = ""
        self.hit_time = 0.0
        self.training = False
        self.camera_shake = True
        self.round_limit = 120

        for key in self.keys:
            self.accept(key, self.key, [key, True])
            self.accept(key + "-up", self.key, [key, False])

        for key, move in (
            ("j", "jab"),
            ("k", "cross"),
            ("l", "hook"),
            ("i", "uppercut"),
            ("u", "body"),
            ("o", "overhand"),
        ):
            self.accept(key, self.attack, [move])

        self.accept("escape", self.pause)
        self.accept("r", self.rematch)
        self.accept("n", self.next_match)
        self.accept("f1", self.toggle_ai)
        self.accept("f2", self.toggle_light)
        self.accept("window-event", self.focus)

        try:
            saved = json.loads(SAVE.read_text())

            if isinstance(saved, dict):
                self.selected = int(
                    saved.get("robot", 0)
                ) % len(ROBOTS)

                self.style_id = int(
                    saved.get("style", 0)
                ) % len(STYLES)

                self.map_id = int(
                    saved.get("map", 0)
                ) % len(MAPS)

        except (OSError, ValueError, TypeError):
            pass

        self.make_arena()

        self.hud = OnscreenText(
            text="",
            pos=(-1.7, 0.89),
            align=TextNode.ALeft,
            scale=0.048,
            fg=(0.85, 0.93, 1, 1),
            mayChange=True,
        )

        self.notice = OnscreenText(
            text="",
            pos=(0, 0.68),
            scale=0.055,
            fg=(1, 0.7, 0.3, 1),
            mayChange=True,
        )

        OnscreenText(
            text=(
                "WASD move | J / K / L / I / U / O punches"
                " | SPACE guard | ESC pause"
            ),
            pos=(0, -0.89),
            scale=0.036,
            fg=(0.72, 0.82, 0.9, 1),
        )

        OnscreenText(
            text="R restart | F1 opponent on/off | F2 simple lighting",
            pos=(0, -0.95),
            scale=0.032,
            fg=(0.55, 0.68, 0.78, 1),
        )

        self.reset()
        self.show_menu()
        self.taskMgr.add(self.update, "game")

    def part(
        self, parent, pos, size, col,
        model="box", glow=False,
    ):
        source = self.box if model == "box" else self.round
        node = source.copyTo(parent)

        node.setPos(*pos)
        node.setScale(*size)
        node.setColorScale(*col)
        node.setShaderInput("glow", 1.0 if glow else 0.0)

        return node

    def wall(self, pos, size):
        body = BulletRigidBodyNode("wall")
        body.addShape(BulletBoxShape(Vec3(*size) * 0.5))
        body.setFriction(1.0)

        path = self.arena.attachNewNode(body)
        path.setPos(*pos)

        self.world.attachRigidBody(body)
        self.static.append(body)

    def make_arena(self):
        for body in self.static:
            self.world.removeRigidBody(body)

        self.static.clear()

        if self.arena:
            self.arena.removeNode()

        self.arena = self.render.attachNewNode("arena")

        _, floor, accent, background = MAPS[self.map_id]
        self.setBackgroundColor(*background)

        neon = rgb(*accent)
        base = rgb(*floor)

        self.wall((0, 0, -0.2), (30, 30, 0.4))
        self.part(
            self.arena, (0, 0, -0.24),
            (30, 30, 0.4), DARK,
        )

        for x in range(-5, 6):
            for y in range(-5, 6):
                factor = 0.88 if (x + y) % 2 else 1
                tint = tuple(c * factor for c in base[:3]) + (1,)

                self.part(
                    self.arena,
                    (x, y, -0.03),
                    (0.98, 0.98, 0.06),
                    tint,
                )

        for axis in (0, 1):
            for sign in (-1, 1):
                pos = [0, 0, 0.65]
                pos[axis] = sign * 5.1

                size = [10.4, 10.4, 1.3]
                size[axis] = 0.18

                self.wall(pos, size)

                for z in (0.1, 0.65, 1.2):
                    rail_pos = list(pos)
                    rail_size = list(size)

                    rail_pos[2] = z
                    rail_size[2] = 0.055

                    self.part(
                        self.arena, rail_pos, rail_size,
                        neon, glow=True,
                    )

        for x in (-5.1, 5.1):
            for y in (-5.1, 5.1):
                self.part(
                    self.arena,
                    (x, y, 0.85),
                    (0.28, 0.28, 1.7),
                    METAL,
                )

        for x in range(-10, 11, 4):
            if self.map_id == 0:
                self.part(
                    self.arena,
                    (x, 8, 2.7),
                    (2.8, 1.1, 5.4),
                    rgb(29, 40, 57),
                )
                self.part(
                    self.arena,
                    (x, 7.42, 3.5),
                    (1.6, 0.03, 0.1),
                    neon,
                    glow=True,
                )

            elif self.map_id == 1:
                self.part(
                    self.arena,
                    (x, 8, 2),
                    (2, 2, 4),
                    METAL,
                    "cylinder",
                )

                for z in (1, 2, 3):
                    self.part(
                        self.arena,
                        (x, 6.97, z),
                        (1.5, 0.04, 0.3),
                        neon,
                        glow=True,
                    )

            else:
                self.part(
                    self.arena,
                    (x, 8, 1.4),
                    (3, 2.4, 2.8),
                    rgb(157, 178, 196),
                )
                self.part(
                    self.arena,
                    (x, 6.76, 1.8),
                    (2, 0.03, 0.75),
                    neon,
                    glow=True,
                )

    def key(self, key, value):
        self.keys[key] = value

    def focus(self, window):
        if window and not window.getProperties().getForeground():
            for key in self.keys:
                self.keys[key] = False

            if self.screen == "fight":
                self.show_pause()

    def attack(self, kind):
        if self.screen == "fight" and not self.finished:
            self.fighters[0].punch(kind)

    def pause(self):
        if self.screen == "fight":
            self.show_pause()
        elif self.screen == "pause":
            self.resume()
        elif self.screen != "menu":
            self.show_menu()

    def toggle_ai(self):
        self.ai = not self.ai

    def toggle_light(self):
        self.simple = not self.simple
        self.render.setShaderInput("simple", float(self.simple))

    def reset(self):
        for fighter in self.fighters:
            fighter.remove()

        for particle in self.particles:
            particle[0].removeNode()

        self.particles.clear()

        choices = [
            i for i in range(len(ROBOTS))
            if i not in (self.selected, self.last_enemy)
        ]

        enemy = random.choice(choices)
        self.last_enemy = enemy

        self.fighters = [
            Fighter(
                self, (-1.4, 0, 0),
                self.selected, -90, self.style_id,
            ),
            Fighter(
                self, (1.4, 0, 0),
                enemy, 90, random.randrange(len(STYLES)),
            ),
        ]

        self.hit_time = 0.0
        self.hit_text = ""

        for key in self.keys:
            self.keys[key] = False

        self.finished = False
        self.accumulator = 0.0
        self.elapsed = 0.0
        self.ai_timer = 0.6

    def movement(self):
        q = self.camera.getQuat(self.render)

        right = q.xform(Vec3(1, 0, 0))
        right.z = 0
        right.normalize()

        forward = q.xform(Vec3(0, 0, 1))
        forward.z = 0

        if forward.length() < 0.01:
            forward = Vec3(0, 1, 0)

        forward.normalize()

        return cap(
            right * (self.keys["d"] - self.keys["a"])
            + forward * (self.keys["w"] - self.keys["s"]),
            1,
        )

    def spark(self, pos):
        if len(self.particles) > 100:
            return

        for _ in range(9):
            node = self.part(
                self.render,
                pos,
                (0.035, 0.035, 0.035),
                ORANGE,
                glow=True,
            )

            velocity = Vec3(
                random.uniform(-2, 2),
                random.uniform(-2, 2),
                random.uniform(1, 3),
            )

            self.particles.append([node, velocity, 0.3])

    def step(self, dt, move, guard):
        a, b = self.fighters

        if self.finished:
            for fighter, other in ((a, b), (b, a)):
                if fighter.hp > 0:
                    fighter.attack = None
                    fighter.drive(dt, Vec3(0), False, other)

            self.world.doPhysics(dt, 1, dt)
            return

        self.elapsed += dt

        direction = a.position() - b.position()
        direction.z = 0
        distance = direction.length()

        ai_move = (
            direction.normalized()
            if distance > 1.05 and self.ai
            else Vec3(0)
        )

        if b.energy < 25 and distance < 2.2 and self.ai:
            ai_move = (
                -direction.normalized() * 0.6
                if distance > 0.01 else Vec3(0)
            )

        ai_guard = (
            self.ai
            and a.attack
            and math.sin(self.elapsed * 5) > 0.1
        )

        self.ai_timer -= dt

        if self.ai and self.ai_timer <= 0:
            if distance < 1.8:
                b.punch(random.choice(tuple(MOVES)))

            self.ai_timer = random.uniform(0.25, 0.65)

        a.drive(dt, move, guard, b)
        b.drive(dt, ai_move, ai_guard, a)

        self.world.doPhysics(dt, 1, dt)

        a.check_hit(b)
        b.check_hit(a)

        if (
            a.hp <= 0
            or b.hp <= 0
            or (
                not self.training
                and self.elapsed >= self.round_limit
            )
        ):
            self.finished = True

    def draw(self, dt):
        a, b = self.fighters

        for fighter in self.fighters:
            p = fighter.position()
            fighter.shadow.setPos(p.x, p.y, 0.006)

            color = (
                rgb(240, 245, 250)
                if fighter.flash else DARK
            )
            fighter.chest_plate.setColorScale(*color)

        for particle in self.particles[:]:
            particle[2] -= dt
            particle[1].z -= 9 * dt
            particle[0].setPos(
                particle[0].getPos() + particle[1] * dt
            )

            if particle[2] <= 0:
                particle[0].removeNode()
                self.particles.remove(particle)

        mid = (a.position() + b.position()) * 0.5
        distance = (a.position() - b.position()).length()

        line = b.position() - a.position()
        line.z = 0

        side = Vec3(line.y, -line.x, 0)

        if side.length() < 0.01:
            side = Vec3(0, -1, 0)

        side.normalize()

        view = self.camera.getPos() - mid
        view.z = 0

        if side.dot(view) < 0:
            side = -side

        desired = (
            Vec3(mid.x, mid.y, 0)
            + side * (7.4 + distance * 0.3)
            + Vec3(0, 0, 3.8 + distance * 0.15)
        )

        self.camera.setPos(
            self.camera.getPos()
            + (desired - self.camera.getPos())
            * min(1, dt * 3)
        )

        self.shake *= math.exp(-dt * 13)

        shake = (
            random.uniform(-self.shake, self.shake)
            if self.camera_shake else 0
        )

        self.camera.lookAt(
            mid.x * 0.65 + shake,
            mid.y * 0.65,
            1.1,
        )

        self.hud.setText(
            f"{ROBOTS[a.robot][0]}  HP {math.ceil(a.hp):3}"
            f"  ENERGY {int(a.energy):3}"
            f"  BALANCE {int(a.balance):3}\n"
            f"{ROBOTS[b.robot][0]}  HP {math.ceil(b.hp):3}"
            f"  ENERGY {int(b.energy):3}"
            f"  BALANCE {int(b.balance):3}"
        )

        self.hit_time = max(0, self.hit_time - dt)
        clock = max(0, self.round_limit - int(self.elapsed))

        if self.hit_time:
            status = self.hit_text
        elif self.training:
            status = "TRAINING | F1: AI ON/OFF"
        else:
            status = (
                f"{clock // 60:02}:{clock % 60:02}"
                f"  |  {STYLES[self.style_id][0]}"
            )

        self.notice.setText(status)

    def update(self, task):
        dt = min(globalClock.getDt(), 0.1)
        fixed_dt = 1 / 120

        if self.screen == "fight":
            self.accumulator += dt

            while self.accumulator >= fixed_dt:
                self.step(
                    fixed_dt,
                    self.movement(),
                    self.keys["space"],
                )
                self.accumulator -= fixed_dt

            self.draw(dt)

            if self.finished:
                self.show_result()

        elif self.screen == "result":
            self.accumulator += dt

            while self.accumulator >= fixed_dt:
                self.step(fixed_dt, Vec3(0), False)
                self.accumulator -= fixed_dt

            self.draw(dt)

        elif self.preview:
            self.preview.setH(
                self.preview.getH() + dt * 22
            )

        return task.cont

    # --------------------------------------------------------
    # ВНЕШНИЙ ВИД РОБОТОВ
    # --------------------------------------------------------

    def dress(self, paths, robot):
        _, color, variant = ROBOTS[robot]
        paint = rgb(*color)

        for name, (kind, mass, size) in SPECS.items():
            path = paths[name]

            if kind == "box":
                self.part(path, (0, 0, 0), size, paint)
            else:
                radius, length = size

                self.part(
                    path,
                    (0, 0, 0),
                    (radius * 1.35, radius * 1.35, length),
                    METAL,
                    "cylinder",
                )

                self.part(
                    path,
                    (0, 0, 0),
                    (
                        radius * 2.2,
                        radius * 2.2,
                        length * 0.66,
                    ),
                    paint,
                )

                for z in (-length / 2, length / 2):
                    self.part(
                        path,
                        (0, 0, z),
                        (radius * 1.8, radius * 1.8, 0.07),
                        DARK,
                        "cylinder",
                    )

            if name.startswith("fore"):
                self.part(
                    path,
                    (0, 0, size[1] / 2),
                    (0.35, 0.35, 0.34),
                    paint,
                )

        chest = paths["torso"]
        head = paths["head"]

        plate = self.part(
            chest,
            (0, 0.225, 0.03),
            (0.52, 0.06, 0.4),
            DARK,
        )

        self.part(
            chest,
            (0, 0.27, 0.06),
            (0.17, 0.025, 0.15),
            paint,
            glow=True,
        )

        self.part(
            head,
            (0, 0.21, 0.04),
            (0.34, 0.045, 0.095),
            DARK,
        )

        self.part(
            head,
            (0, 0.24, 0.04),
            (0.27, 0.02, 0.04),
            paint,
            glow=True,
        )

        for x in (-0.35, 0.35):
            self.part(
                chest,
                (x, 0, 0.3),
                (0.2, 0.48, 0.14),
                METAL,
            )

        if variant == 0:
            for x in (-0.17, 0.17):
                self.part(
                    chest,
                    (x, 0.27, -0.08),
                    (0.07, 0.035, 0.3),
                    METAL,
                )

            self.part(
                head, (0, 0, 0.22),
                (0.08, 0.35, 0.1), METAL,
            )

        elif variant == 1:
            for x in (-0.20, 0.20):
                self.part(
                    head,
                    (x, 0, 0),
                    (0.10, 0.35, 0.32),
                    METAL,
                )

            for z in (-0.15, -0.07, 0.01):
                self.part(
                    chest,
                    (0, 0.275, z),
                    (0.46, 0.04, 0.025),
                    METAL,
                )

        elif variant == 2:
            for x in (-0.19, 0.19):
                self.part(
                    chest,
                    (x, 0.27, 0.05),
                    (0.18, 0.05, 0.28),
                    paint,
                )

            for x in (-0.12, 0.12):
                self.part(
                    head,
                    (x, 0.242, 0.05),
                    (0.075, 0.03, 0.085),
                    ORANGE,
                    glow=True,
                )

        elif variant == 3:
            for x in (-0.22, 0.22):
                self.part(
                    head,
                    (x, -0.06, 0.22),
                    (0.065, 0.12, 0.28),
                    METAL,
                )

            for x in (-0.2, 0.2):
                self.part(
                    chest,
                    (x, 0.26, 0.17),
                    (0.22, 0.06, 0.16),
                    paint,
                )

        else:
            for x in (-0.43, 0.43):
                self.part(
                    chest,
                    (x, 0, 0.26),
                    (0.22, 0.45, 0.23),
                    paint,
                )

            self.part(
                head,
                (0, 0.22, -0.12),
                (0.34, 0.08, 0.12),
                METAL,
            )

        return plate

    # --------------------------------------------------------
    # МЕНЮ
    # --------------------------------------------------------

    def clear_ui(self):
        for widget in self.widgets:
            widget.destroy()

        self.widgets = []

        if self.preview:
            self.preview.removeNode()
            self.preview = None

        self.hud.hide()
        self.notice.hide()

    def label(self, text, z, scale=0.055, x=0):
        widget = DirectLabel(
            parent=self.aspect2d,
            text=text,
            text_scale=scale,
            text_fg=(0.85, 0.94, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(x, 0, z),
        )

        self.widgets.append(widget)
        return widget

    def button(self, text, z, command, x=0, width=0.75):
        widget = DirectButton(
            parent=self.aspect2d,
            text=text,
            text_scale=0.045,
            text_fg=(0.9, 0.97, 1, 1),
            frameColor=(0.06, 0.13, 0.19, 0.97),
            frameSize=(-width, width, -0.055, 0.075),
            pos=(x, 0, z),
            command=command,
            relief=1,
            pressEffect=True,
        )

        self.widgets.append(widget)
        return widget

    def panel(self, title, screen):
        self.clear_ui()
        self.screen = screen
        self.accumulator = 0.0

        for key in self.keys:
            self.keys[key] = False

        panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.012, 0.022, 0.035, 0.90),
            frameSize=(-1.65, 1.65, -0.83, 0.86),
        )

        self.widgets.append(panel)
        self.label(title, 0.72, 0.085)

    def save_settings(self):
        try:
            SAVE.write_text(json.dumps({
                "robot": self.selected,
                "style": self.style_id,
                "map": self.map_id,
            }))
        except OSError:
            pass

    def show_menu(self):
        self.panel("STEEL ARENA", "menu")
        self.label("ROBOT COMBAT", 0.57, 0.035)

        self.button(
            "FIGHT", 0.37,
            lambda: self.start_match(False),
        )
        self.button(
            "TRAINING", 0.20,
            lambda: self.start_match(True),
        )
        self.button("FREE GARAGE", 0.03, self.show_garage)
        self.button("FIGHTING STYLE", -0.14, self.show_styles)
        self.button("ARENA", -0.31, self.show_maps)
        self.button(
            "SETTINGS / CONTROLS", -0.48,
            self.show_settings,
        )
        self.button("QUIT", -0.65, self.userExit)

    def show_preview(self):
        self.preview = self.render.attachNewNode(
            "garage-preview"
        )

        target, _ = pose(Vec3(0), 180)
        paths = {}

        for name, (pos, q) in target.items():
            paths[name] = self.preview.attachNewNode(name)
            paths[name].setPos(pos)
            paths[name].setQuat(q)

        self.dress(paths, self.selected)

        self.camera.setPos(3, -7.8, 3.4)
        self.camera.lookAt(0, 0, 1.05)
        self.preview.setPos(0, 0, 0.03)

    def show_garage(self):
        self.panel("FREE GARAGE", "garage")
        self.widgets[0]["frameColor"] = (
            0.012, 0.022, 0.035, 0.25,
        )

        for fighter in self.fighters:
            for path in fighter.paths.values():
                path.hide()
            fighter.shadow.hide()

        self.show_preview()

        self.label(ROBOTS[self.selected][0], 0.55, 0.06)
        self.label(
            f"{self.selected + 1} / {len(ROBOTS)}"
            "   |   ALL ROBOTS FREE",
            0.43,
            0.035,
        )

        self.button(
            "<", 0.02,
            lambda: self.choose_robot(-1),
            x=-1.2, width=0.2,
        )
        self.button(
            ">", 0.02,
            lambda: self.choose_robot(1),
            x=1.2, width=0.2,
        )
        self.button(
            "USE ROBOT / BACK", -0.66,
            self.leave_garage,
        )

    def choose_robot(self, delta):
        self.selected = (
            self.selected + delta
        ) % len(ROBOTS)
        self.show_garage()

    def leave_garage(self):
        self.save_settings()

        for fighter in self.fighters:
            for path in fighter.paths.values():
                path.show()
            fighter.shadow.show()

        self.show_menu()

    def show_styles(self):
        self.panel("FIGHTING STYLE", "styles")

        descriptions = [
            "Balanced punches and footwork",
            "Fast hands, lighter hits",
            "Slow, powerful punches",
            "Quick recovery of balance",
        ]

        for i, style in enumerate(STYLES):
            z = 0.40 - i * 0.24
            prefix = "> " if i == self.style_id else ""

            self.button(
                prefix + style[0],
                z,
                lambda i=i: self.choose_style(i),
                x=-0.65,
                width=0.65,
            )
            self.label(
                descriptions[i], z, 0.031, x=0.70,
            )

        self.button("BACK", -0.67, self.show_menu)

    def choose_style(self, index):
        self.style_id = index
        self.save_settings()
        self.show_styles()

    def show_maps(self):
        self.panel("SELECT ARENA", "maps")

        for i, arena in enumerate(MAPS):
            prefix = "> " if i == self.map_id else ""

            self.button(
                prefix + arena[0],
                0.35 - i * 0.23,
                lambda i=i: self.choose_map(i),
            )

        self.label(
            "Dock / industrial furnaces / polar base",
            -0.41,
            0.034,
        )
        self.button("BACK", -0.66, self.show_menu)

    def choose_map(self, index):
        self.map_id = index
        self.make_arena()
        self.save_settings()
        self.show_maps()

    def show_settings(self):
        self.panel("SETTINGS / CONTROLS", "settings")

        self.button(
            "LIGHTING: "
            + ("SIMPLE" if self.simple else "METALLIC"),
            0.40,
            self.setting_light,
        )

        self.button(
            "CAMERA SHAKE: "
            + ("ON" if self.camera_shake else "OFF"),
            0.20,
            self.setting_shake,
        )

        self.label(
            "WASD: move    SPACE: guard",
            -0.02, 0.042,
        )
        self.label(
            "J: jab   K: cross   L: hook   I: uppercut"
            "   U: body   O: overhand",
            -0.16, 0.037,
        )
        self.label(
            "ESC: pause    R: restart    N: next opponent",
            -0.30, 0.037,
        )
        self.label(
            "F1: opponent AI    F2: lighting",
            -0.44, 0.037,
        )

        self.button("BACK", -0.66, self.show_menu)

    def setting_light(self):
        self.toggle_light()
        self.show_settings()

    def setting_shake(self):
        self.camera_shake = not self.camera_shake
        self.show_settings()

    def start_match(self, training=False):
        self.clear_ui()
        self.training = training
        self.ai = not training
        self.reset()

        self.screen = "fight"
        self.hud.show()
        self.notice.show()

        self.camera.setPos(0, -8, 4)
        self.camera.lookAt(0, 0, 1.1)

    def resume(self):
        self.clear_ui()
        self.screen = "fight"
        self.accumulator = 0.0
        self.hud.show()
        self.notice.show()

    def show_pause(self):
        self.panel("PAUSED", "pause")

        self.button("RESUME", 0.30, self.resume)
        self.button(
            "NEW OPPONENT", 0.08,
            lambda: self.start_match(self.training),
        )
        self.button("MAIN MENU", -0.14, self.show_menu)

    def rematch(self):
        if self.screen in ("fight", "pause", "result"):
            self.start_match(self.training)

    def next_match(self):
        if self.screen == "result":
            self.start_match(self.training)

    def show_result(self):
        a, b = self.fighters

        if abs(a.hp - b.hp) < 0.01:
            title = "DRAW"
        elif a.hp > b.hp:
            title = "VICTORY"
        else:
            title = "DEFEAT"

        self.panel(title, "result")

        self.label(
            "KNOCKOUT" if min(a.hp, b.hp) <= 0 else "TIME LIMIT",
            0.48,
            0.04,
        )

        self.button(
            "NEXT OPPONENT",
            0.12,
            lambda: self.start_match(self.training),
        )
        self.button("MAIN MENU", -0.12, self.show_menu)


if __name__ == "__main__":
    Game().run()