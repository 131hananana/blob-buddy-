"""
Animation primitives: easing curves and damped springs.

Why springs instead of fixed-duration tweens?
    The blob's emotional parameters (smile, droopiness, squash...) change
    *targets* whenever its state changes.  A spring continuously chases its
    target, so every transition is automatically smooth no matter when or
    how often the target moves — there are never sudden jumps.

    - zeta = 1.0  -> critically damped: glides to the target, no overshoot.
      Used for emotions (smile, eye openness, droop...).
    - zeta < 1.0  -> under-damped: overshoots and wobbles before settling.
      Used for the body squash so the blob physically jiggles like jelly
      when you "nudge" it (see Spring.nudge).
"""

import math

TAU = math.tau


# ------------------------------------------------------------------ easing ---

def ease_in_out(t):
    """Smoothstep — gentle acceleration and deceleration."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_out_back(t, overshoot=1.4):
    """Overshoots slightly past 1 then settles — nice for pop-in effects."""
    t = max(0.0, min(1.0, t)) - 1.0
    return 1.0 + t * t * ((overshoot + 1.0) * t + overshoot)


def bounce_arc(t):
    """0 -> 1 -> 0 arc (sin half-wave), used for hops."""
    t = max(0.0, min(1.0, t))
    return math.sin(t * math.pi)


# ------------------------------------------------------------------ spring ---

class Spring:
    """A damped harmonic spring integrated with semi-implicit Euler.

    omega : natural frequency in rad/s (higher = snappier)
    zeta  : damping ratio (1 = critical, <1 = wobbly)
    """

    def __init__(self, value=0.0, omega=10.0, zeta=1.0):
        self.value = float(value)
        self.velocity = 0.0
        self.omega = omega
        self.zeta = zeta

    def update(self, target, dt):
        # Clamp dt so a long frame hitch can't make the integration explode.
        dt = min(dt, 1.0 / 30.0)
        accel = (self.omega * self.omega) * (target - self.value) \
            - 2.0 * self.zeta * self.omega * self.velocity
        self.velocity += accel * dt
        self.value += self.velocity * dt
        return self.value

    def nudge(self, impulse):
        """Kick the spring's velocity — an under-damped spring will visibly
        wobble afterwards.  This is how petting makes the blob jiggle."""
        self.velocity += impulse

    def snap(self, value):
        self.value = float(value)
        self.velocity = 0.0
