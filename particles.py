"""
A tiny particle system for the emotional garnish: hearts while petting,
sparkles while happy, "Zzz" bubbles while asleep, raindrops from the lonely
cloud, and little sigh puffs.

Each particle kind has its own motion rule in `update` and a pre-rendered
surface (cached by kind/size/color) so per-frame cost stays low.
"""

import math
import random

import pygame


class Particle:
    __slots__ = ("kind", "x", "y", "vx", "vy", "life", "max_life",
                 "size", "phase", "surf")

    def __init__(self, kind, x, y, vx, vy, life, size, surf):
        self.kind = kind
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.size = size
        self.phase = random.uniform(0, math.tau)
        self.surf = surf


class ParticleSystem:
    MAX_PARTICLES = 120

    def __init__(self):
        self.particles = []
        self._cache = {}
        self._font_cache = {}

    # ------------------------------------------------------------ spawning ---

    def spawn(self, kind, x, y, color, size=None, count=1):
        for _ in range(count):
            if len(self.particles) >= self.MAX_PARTICLES:
                return
            s = size or {
                "heart": random.randint(10, 18),
                "sparkle": random.randint(6, 12),
                "zzz": random.randint(14, 24),
                "drop": random.randint(4, 6),
                "puff": random.randint(8, 14),
            }.get(kind, 10)
            surf = self._surface(kind, s, color)

            if kind == "heart":
                p = Particle(kind, x + random.uniform(-30, 30), y + random.uniform(-20, 10),
                             random.uniform(-12, 12), random.uniform(-55, -35),
                             random.uniform(1.2, 1.8), s, surf)
            elif kind == "sparkle":
                p = Particle(kind, x + random.uniform(-70, 70), y + random.uniform(-70, 30),
                             random.uniform(-6, 6), random.uniform(-14, -6),
                             random.uniform(0.8, 1.4), s, surf)
            elif kind == "zzz":
                p = Particle(kind, x, y, 10.0, -28.0,
                             random.uniform(2.2, 2.8), s, surf)
            elif kind == "drop":
                p = Particle(kind, x + random.uniform(-26, 26), y,
                             0.0, random.uniform(70, 110),
                             random.uniform(0.7, 1.0), s, surf)
            elif kind == "puff":
                p = Particle(kind, x, y, random.uniform(18, 30), random.uniform(-8, -2),
                             random.uniform(0.9, 1.3), s, surf)
            else:
                continue
            self.particles.append(p)

    # ------------------------------------------------------------- update ---

    def update(self, dt):
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            t = 1.0 - p.life / p.max_life  # 0 -> 1 over the particle's life
            if p.kind == "heart":
                # Hearts float up while swaying side to side.
                p.x += (p.vx + math.sin(p.phase + t * 6.0) * 18.0) * dt
                p.y += p.vy * dt
            elif p.kind == "sparkle":
                p.x += p.vx * dt
                p.y += p.vy * dt
            elif p.kind == "zzz":
                # Zzz bubbles drift up-right with a lazy wiggle.
                p.x += (p.vx + math.sin(p.phase + t * 4.0) * 10.0) * dt
                p.y += p.vy * dt
            elif p.kind == "drop":
                p.vy += 220.0 * dt  # rain accelerates downward
                p.y += p.vy * dt
            elif p.kind == "puff":
                p.x += p.vx * dt
                p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

    # -------------------------------------------------------------- draw ---

    def draw(self, screen):
        for p in self.particles:
            t = p.life / p.max_life
            if p.kind == "sparkle":
                # Sparkles twinkle: alpha pulses as they fade.
                alpha = int(255 * t * (0.6 + 0.4 * math.sin(p.phase + t * 20)))
            else:
                alpha = int(255 * min(1.0, t * 3.0))  # quick fade at end of life
            p.surf.set_alpha(max(0, alpha))
            screen.blit(p.surf, (p.x - p.surf.get_width() / 2,
                                 p.y - p.surf.get_height() / 2))

    def clear(self):
        self.particles.clear()

    # ----------------------------------------------- pre-rendered surfaces ---

    def _surface(self, kind, size, color):
        key = (kind, size, color)
        if key in self._cache:
            return self._cache[key]

        if kind == "zzz":
            surf = self._zzz_surface(size, color)
        else:
            pad = 2
            surf = pygame.Surface((size * 2 + pad * 2, size * 2 + pad * 2), pygame.SRCALPHA)
            c = size + pad
            if kind == "heart":
                r = size // 2
                pygame.draw.circle(surf, color, (c - r + 1, c - r // 2), r)
                pygame.draw.circle(surf, color, (c + r - 1, c - r // 2), r)
                pygame.draw.polygon(surf, color, [
                    (c - size + 1, c - r // 2 + 2),
                    (c + size - 1, c - r // 2 + 2),
                    (c, c + size - 2)])
            elif kind == "sparkle":
                # A four-pointed star: two thin diamonds.
                pygame.draw.polygon(surf, color, [
                    (c, c - size), (c + size * 0.28, c), (c, c + size), (c - size * 0.28, c)])
                pygame.draw.polygon(surf, color, [
                    (c - size, c), (c, c + size * 0.28), (c + size, c), (c, c - size * 0.28)])
            elif kind == "drop":
                pygame.draw.circle(surf, color, (c, c), size)
                pygame.draw.polygon(surf, color, [
                    (c - size, c), (c + size, c), (c, c - size * 2)])
            elif kind == "puff":
                for _ in range(3):
                    ox = random.randint(-size // 2, size // 2)
                    oy = random.randint(-size // 3, size // 3)
                    pygame.draw.circle(surf, color, (c + ox, c + oy), size // 2)

        self._cache[key] = surf
        return surf

    def _zzz_surface(self, size, color):
        if size not in self._font_cache:
            self._font_cache[size] = pygame.font.Font(None, size)
        return self._font_cache[size].render("z", True, color)
