import colorsys
import math
from collections import deque

import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import PressDragEvent, PressReleaseEvent, TapEvent

BG_COLOR = (8, 8, 16)
STAR_COLOR = (255, 225, 140)
# Trails fade from this fraction of a planet's own color (near-black but not
# quite, so they stay visible against BG_COLOR) up to its full color.
TRAIL_DARK_FRACTION = 0.15
# The star's own trail only shows up while it's actually drifting noticeably
# (e.g. right after a heavy absorption kicks it), so it's drawn much lighter
# than a planet's -- short and faint rather than a constant fixture.
STAR_TRAIL_DARK_FRACTION = 0.6
STAR_TRAIL_LENGTH = 20


class NBodyDemo(Demo):
    # Tuned so an orbiter at the inner edge of the spawn ring (~0.15 of the
    # screen's shorter side) completes an orbit in a handful of seconds, and
    # one at the outer edge (~0.35) takes proportionally longer (r^1.5) --
    # visibly Keplerian without being too fast to read or too slow to notice.
    G = 300.0
    # Softens the 1/r^2 force so it stays finite as bodies pass close to each
    # other, instead of flinging them out at near-infinite speed.
    SOFTENING = 15.0
    # Heavy enough that the momentum a tapped-in body imparts barely moves it
    # even before the momentum-conserving kick in _add_body is applied.
    STAR_MASS = 8000.0
    PLANET_MASS_MIN = 20.0
    PLANET_MASS_MAX = 80.0
    NUM_INITIAL_ORBITERS = 4
    MIN_ORBIT_RADIUS = 12.0
    # Bodies more than this many screen-widths/heights from the screen center
    # stop being tracked, so a long session of tapping doesn't slowly grow an
    # ever-larger O(n^2) force computation from bodies that have long since
    # flown off past any visible area.
    TRACKING_AREA_MULTIPLIER = 10
    RADIUS_SCALE = 2.2
    MIN_DRAW_RADIUS = 3
    MAX_DRAW_RADIUS = 18
    TRAIL_LENGTH = 90  # ~1.5s at 60fps
    COLLISION_RADIUS_FRACTION = 0.5  # 50% of star's visual radius

    # Planet-vs-planet collisions (separate from star absorption above).
    # Two planets collide once their visual circles touch.
    PLANET_COLLISION_RADIUS_FRACTION = 1.0  # 100% of combined visual radii
    # Below this mass no fragment can exist, so the screen doesn't fill up
    # with specks; collisions that can't produce at least 2 such fragments
    # just merge instead of shattering.
    MIN_FRAGMENT_MASS = 10.0
    MAX_FRAGMENTS = 3  # cap shrapnel count so a hit doesn't clutter the screen
    # Hard cap on body count. Without this, tapping/launching in rapidly
    # raises n into a range where close encounters get frequent enough to
    # slingshot a body to extreme speed in one frame; the next frame's
    # position update can then overflow to inf/nan, which (once it reaches
    # the star, the body every other body's gravity and the camera are both
    # anchored to) wipes out the whole array and looks like the demo
    # "resetting". Spawns past this cap are silently dropped instead.
    MAX_BODIES = 150
    # Hard speed clamp applied every frame, for the same reason: it stops a
    # numerically chaotic close encounter from ever reaching the magnitudes
    # that would overflow into inf/nan in the first place.
    MAX_SPEED = 4000.0
    # Upper bound on the dt used for physics, independent of config.FPS --
    # a stalled frame (GC pause, a slow draw call, OS scheduling) must not
    # translate into one huge Euler integration step that flings a body
    # arbitrarily far.
    MAX_PHYSICS_DT = 1.0 / 30.0
    # A collision shatters the bodies if their impact speed exceeds their
    # mutual escape velocity (the real-world rule of thumb for whether debris
    # stays gravitationally bound or flies apart); slower grazes just merge.
    FRAGMENTATION_SPEED_FACTOR = 1.0
    # Fraction of impact speed imparted to fragments as outward ejecta speed.
    EJECTA_SPEED_FACTOR = 0.4

    # Press-and-hold-then-drag launch: speed is proportional to drag
    # distance (in screen pixels), capped so a wild drag can't fling a body
    # off at an unplayable speed.
    LAUNCH_SPEED_SCALE = 2.0
    LAUNCH_MAX_SPEED = 600.0
    # Below this drag distance, treat it as a hold that never really
    # dragged -- release does nothing rather than launching at near-zero
    # speed in a meaningless direction.
    MIN_LAUNCH_DISTANCE = 4.0
    TRAJECTORY_PREVIEW_STEPS = 90
    TRAJECTORY_PREVIEW_DT = 1.0 / 60.0
    LAUNCH_PREVIEW_COLOR = (235, 235, 245)

    # Zoom is driven by the on-screen slider on the right edge (see the SLIDER_*
    # constants and _draw_sliders), not by pinch-to-zoom. The view starts at
    # ZOOM_DEFAULT (1:1 with world space); the slider ranges from ZOOM_MIN (the
    # visible area matches the same 10x-screen tracking/culling window bodies
    # are allowed to roam in before they're culled -- see
    # TRACKING_AREA_MULTIPLIER -- so you never look at emptiness beyond where
    # anything could still be) up to ZOOM_MAX (zoomed in).
    ZOOM_DEFAULT = 1.0
    ZOOM_MAX = 4.0
    ZOOM_MIN = 1.0 / TRACKING_AREA_MULTIPLIER
    # The slider only moves a target value; self.zoom eases toward that target
    # every frame (exponential decay, per second -- higher is snappier) so a
    # flick of the slider glides to the new zoom instead of snapping.
    ZOOM_SMOOTHING_RATE = 10.0

    # Simulation-speed slider on the left edge. 1.0 is real-time; the physics
    # is sub-stepped so even SPEED_MAX stays numerically stable (no single
    # integration step ever exceeds MAX_PHYSICS_DT -- see update()).
    SPEED_DEFAULT = 1.0
    SPEED_MIN = 0.1
    SPEED_MAX = 5.0

    # Minimalist vertical sliders pinned to the screen edges (screen space, not
    # world space -- they don't move with the camera). Both map position
    # logarithmically to their value, since zoom and speed are both ratios.
    SLIDER_EDGE_MARGIN = 16     # track's distance in from the screen edge
    SLIDER_VERTICAL_INSET = 64  # track's inset from the top and bottom edges
    SLIDER_TOUCH_WIDTH = 64     # how far in from the edge a touch still grabs it
    SLIDER_KNOB_RADIUS = 9
    SLIDER_TRACK_COLOR = (70, 76, 92)
    SLIDER_FILL_COLOR = (120, 170, 230)
    SLIDER_KNOB_COLOR = (225, 232, 245)
    SLIDER_LABEL_COLOR = (150, 158, 174)

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.zoom = self.ZOOM_DEFAULT
        self._zoom_target = self.ZOOM_DEFAULT
        self.speed = self.SPEED_DEFAULT
        # Which slider, if any, the current press-drag is controlling ("zoom",
        # "speed", or None for a launch drag). Pinned for the whole gesture so a
        # finger that started on a slider keeps driving it even if it slides off.
        self._active_slider = None
        self.font = pygame.font.SysFont(None, 20)
        self._launch_origin_world = None
        self._launch_current_world = None
        self._spawn_initial_system()

    def _spawn_initial_system(self):
        cx, cy = self.width / 2, self.height / 2
        self.positions = np.array([[cx, cy]], dtype=float)
        self.velocities = np.array([[0.0, 0.0]])
        self.masses = np.array([self.STAR_MASS])
        self.colors = [STAR_COLOR]
        self.trails = [deque(maxlen=STAR_TRAIL_LENGTH)]
        self._next_color_index = 0

        rng = np.random.default_rng()
        min_dim = min(self.width, self.height)
        for _ in range(self.NUM_INITIAL_ORBITERS):
            radius = rng.uniform(0.15, 0.35) * min_dim
            angle = rng.uniform(0, 2 * np.pi)
            pos = [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
            
            # Random mass between PLANET_MASS_MIN and PLANET_MASS_MAX
            planet_mass = rng.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)
            speed = math.sqrt(self.G * self.STAR_MASS / radius)
            # Tangential direction (perpendicular to the radius vector),
            # consistently rotated the same way for every orbiter so they all
            # circle in the same direction rather than colliding head-on.
            direction = (-math.sin(angle), math.cos(angle))
            velocity = [direction[0] * speed, direction[1] * speed]
            self.positions = np.vstack([self.positions, pos])
            self.velocities = np.vstack([self.velocities, velocity])
            self.masses = np.append(self.masses, planet_mass)
            self._add_color_and_trail()

    def _add_color_and_trail(self):
        self.colors.append(_planet_color(self._next_color_index))
        self.trails.append(deque(maxlen=self.TRAIL_LENGTH))
        self._next_color_index += 1

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            slider = self._slider_at(event.x)
            if slider is not None:
                self._set_slider_from_y(slider, event.y)
                return
            world_x, world_y = self._screen_to_world(event.x, event.y)
            self._add_body(world_x, world_y)
        elif isinstance(event, PressDragEvent):
            # A drag that starts on one of the edge sliders drives that slider
            # for the rest of the gesture; anything else is a launch drag.
            if self._active_slider is None and self._launch_origin_world is None:
                self._active_slider = self._slider_at(event.start_x)
            if self._active_slider is not None:
                self._set_slider_from_y(self._active_slider, event.y)
                return
            # The origin is pinned in world space the moment the drag starts
            # (using the camera offset at that instant) so it stays put on
            # screen even as the star's drift shifts the camera over the
            # course of a slow drag; the live end point is re-converted every
            # event so it tracks the finger's current screen position.
            if self._launch_origin_world is None:
                self._launch_origin_world = np.array(self._screen_to_world(event.start_x, event.start_y))
            self._launch_current_world = np.array(self._screen_to_world(event.x, event.y))
        elif isinstance(event, PressReleaseEvent):
            if self._active_slider is not None:
                self._set_slider_from_y(self._active_slider, event.y)
                self._active_slider = None
                return
            if self._launch_origin_world is not None:
                release_world = np.array(self._screen_to_world(event.x, event.y))
                self._launch_body(self._launch_origin_world, release_world)
            self._launch_origin_world = None
            self._launch_current_world = None

    def _slider_at(self, screen_x):
        """Which slider (if any) a touch at this screen x belongs to: "speed"
        on the left edge, "zoom" on the right edge, None in the open middle."""
        if screen_x <= self.SLIDER_TOUCH_WIDTH:
            return "speed"
        if screen_x >= self.width - self.SLIDER_TOUCH_WIDTH:
            return "zoom"
        return None

    def _slider_track_y(self):
        """(top_y, bottom_y) of the slider tracks. Top is the high-value end."""
        return self.SLIDER_VERTICAL_INSET, self.height - self.SLIDER_VERTICAL_INSET

    def _set_slider_from_y(self, slider, screen_y):
        top_y, bottom_y = self._slider_track_y()
        # Fraction up the track: 0 at the bottom, 1 at the top.
        frac = float(np.clip((bottom_y - screen_y) / (bottom_y - top_y), 0.0, 1.0))
        if slider == "zoom":
            self._zoom_target = _log_lerp(self.ZOOM_MIN, self.ZOOM_MAX, frac)
        else:
            self.speed = _log_lerp(self.SPEED_MIN, self.SPEED_MAX, frac)

    def _world_to_screen(self, pos):
        """Maps a world-space position to where it lands on screen: the
        camera follows the star (left free to drift, rather than being
        snapped back, which used to cause a visible jump every few seconds)
        and zoom scales distance from the star around the screen center."""
        cx, cy = self.width / 2, self.height / 2
        star_pos = self.positions[0]
        return (np.asarray(pos, dtype=float) - star_pos) * self.zoom + np.array([cx, cy])

    def _screen_to_world(self, x, y):
        cx, cy = self.width / 2, self.height / 2
        star_pos = self.positions[0]
        return tuple((np.array([x, y], dtype=float) - np.array([cx, cy])) / self.zoom + star_pos)

    def _add_body(self, x, y):
        # New bodies are launched into a circular orbit around the current
        # heaviest body (the "star"), rather than dropped in with zero
        # velocity, so tapping anywhere near it adds a body that swings
        # around instead of just falling straight in.
        star_idx = int(np.argmax(self.masses))
        star_pos = self.positions[star_idx]
        star_mass = self.masses[star_idx]

        planet_mass = np.random.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)
        # Cleared *before* computing the orbit velocity below, so the speed
        # matches the radius the body actually ends up at, not the
        # (possibly nudged-away-from) tapped point.
        pos = self._clear_spawn_position(np.array([float(x), float(y)]), planet_mass)

        offset = pos - star_pos
        r = max(float(np.linalg.norm(offset)), self.MIN_ORBIT_RADIUS)
        direction = offset / r
        tangential = np.array([-direction[1], direction[0]])
        speed = math.sqrt(self.G * star_mass / r)
        new_velocity = tangential * speed

        self._spawn_body(pos, new_velocity, planet_mass)

    def _launch_body(self, origin, release_point):
        """Resolve a press-drag-release gesture into a new body launched
        from origin (where the hold started) with velocity pointing
        opposite the drag (like a slingshot/catapult), magnitude
        proportional to how far it was dragged."""
        drag_vector = release_point - origin
        distance = float(np.linalg.norm(drag_vector))
        if distance < self.MIN_LAUNCH_DISTANCE:
            return
        speed = min(distance * self.LAUNCH_SPEED_SCALE, self.LAUNCH_MAX_SPEED)
        velocity = -(drag_vector / distance) * speed
        planet_mass = np.random.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)
        pos = self._clear_spawn_position(origin, planet_mass)
        self._spawn_body(pos, velocity, planet_mass)

    def _clear_spawn_position(self, pos, new_mass):
        """If pos already overlaps an existing body, push it away (repeating
        against whichever body is the worst offender) until it doesn't.

        Without this, a burst of taps/launches landing near each other (very
        normal for "add a lot of planets quickly") spawns bodies already
        touching, or separated by only a sliver of a gap -- which the very
        next physics step (or the next handful of them) reads as collisions
        and merges/shatters away almost everything that was just added in a
        fast cascade. No state is actually lost or corrupted, but a
        population crashing from ~100 down to ~30 within a second or two
        looks exactly like the demo silently resetting.

        Search outward from pos along a golden-angle spiral (the standard
        even-packing pattern used for things like sunflower seed heads)
        until a clear spot is found, rather than just nudging away from
        whichever single body is most in the way -- that left bodies still
        packed almost edge-to-edge along one line, which collided again
        within a couple of seconds anyway."""
        pos = np.asarray(pos, dtype=float)
        new_radius = float(self._radius_for_mass(new_mass))
        if not self._overlaps_any_body(pos, new_radius):
            return pos

        golden_angle = math.pi * (3 - math.sqrt(5))
        # Generous spacing (not just touching-distance) so spiraled-out
        # bodies have real room to coexist for more than a couple of frames.
        step = new_radius * self.PLANET_COLLISION_RADIUS_FRACTION * 3.0
        candidate = pos
        for k in range(1, self.MAX_BODIES + 1):
            radius = step * math.sqrt(k)
            angle = k * golden_angle
            candidate = pos + radius * np.array([math.cos(angle), math.sin(angle)])
            if not self._overlaps_any_body(candidate, new_radius):
                return candidate
        return candidate  # bounded by MAX_BODIES spawns total, so this never actually exhausts

    def _overlaps_any_body(self, pos, radius):
        existing_radii = self._radius_for_mass(self.masses)
        diffs = pos - self.positions
        dists = np.sqrt(np.sum(diffs * diffs, axis=1))
        thresholds = (existing_radii + radius) * self.PLANET_COLLISION_RADIUS_FRACTION
        return bool((dists < thresholds).any())

    def _spawn_body(self, pos, velocity, mass):
        if len(self.masses) >= self.MAX_BODIES:
            return  # at the cap -- drop the spawn rather than destabilizing the sim

        # Conserve momentum: the new body's momentum must be balanced by an
        # equal-and-opposite kick to the star, otherwise every add injects
        # net momentum into the system and the star (which dominates the
        # system's center of mass) picks up speed with every add.
        star_idx = int(np.argmax(self.masses))
        star_mass = self.masses[star_idx]
        velocity = np.asarray(velocity, dtype=float)
        self.velocities[star_idx] = (
            self.velocities[star_idx] - (mass * velocity) / star_mass
        )
        self.positions = np.vstack([self.positions, pos])
        self.velocities = np.vstack([self.velocities, velocity])
        self.masses = np.append(self.masses, mass)
        self._add_color_and_trail()

    def _predict_launch_trajectory(self):
        """Forward-simulate a massless test particle launched from the
        current drag state under the live system's gravity, without
        mutating any real state -- so a drag in progress can preview where
        the body would actually go if released right now. Other bodies are
        treated as frozen at their current positions for the duration of
        the preview (cheap, and plenty for "which way will it go") rather
        than also forward-simulating the whole n-body system."""
        if self._launch_origin_world is None or self._launch_current_world is None:
            return []
        drag_vector = self._launch_current_world - self._launch_origin_world
        distance = float(np.linalg.norm(drag_vector))
        if distance < self.MIN_LAUNCH_DISTANCE:
            return []
        speed = min(distance * self.LAUNCH_SPEED_SCALE, self.LAUNCH_MAX_SPEED)
        velocity = -(drag_vector / distance) * speed

        pos = self._launch_origin_world.copy()
        vel = velocity.copy()
        points = [pos.copy()]
        star_pos = self.positions[0]
        star_radius = self._radius_for_mass(self.masses[0])
        collision_radius = star_radius * self.COLLISION_RADIUS_FRACTION
        for _ in range(self.TRAJECTORY_PREVIEW_STEPS):
            diffs = self.positions - pos
            dist_sq = np.sum(diffs * diffs, axis=1)
            inv_dist_cubed = (dist_sq + self.SOFTENING**2) ** -1.5
            accel = self.G * np.sum(self.masses[:, None] * inv_dist_cubed[:, None] * diffs, axis=0)
            vel = vel + accel * self.TRAJECTORY_PREVIEW_DT
            pos = pos + vel * self.TRAJECTORY_PREVIEW_DT
            points.append(pos.copy())
            if float(np.linalg.norm(pos - star_pos)) <= collision_radius:
                break  # would be absorbed by the star -- no point tracing further
        return points

    def update(self, dt):
        if len(self.masses) == 0:
            self._spawn_initial_system()
            return

        # The zoom easing tracks real (wall-clock) time, independent of the
        # simulation-speed slider -- the camera should glide at the same rate
        # whether the sim is in slow motion or sped up.
        real_dt = min(dt, self.MAX_PHYSICS_DT)
        self.zoom += (self._zoom_target - self.zoom) * min(1.0, real_dt * self.ZOOM_SMOOTHING_RATE)

        # Total simulated time this frame is scaled by the speed slider, then
        # split into sub-steps so no single Euler step exceeds MAX_PHYSICS_DT.
        # That keeps the integrator stable at high speed (a 5x frame is run as
        # several normal-sized steps) and simply shrinks the step at low speed.
        sim_time = real_dt * self.speed
        if sim_time <= 0:
            return
        substeps = max(1, math.ceil(sim_time / self.MAX_PHYSICS_DT))
        step_dt = sim_time / substeps
        for _ in range(substeps):
            self._step_physics(step_dt)

    def _step_physics(self, dt):
        accel = compute_gravitational_acceleration(
            self.positions, self.masses, g=self.G, softening=self.SOFTENING
        )
        self.velocities = self.velocities + accel * dt
        speed = np.sqrt(np.sum(self.velocities * self.velocities, axis=1))
        too_fast = speed > self.MAX_SPEED
        if too_fast.any():
            self.velocities[too_fast] *= (self.MAX_SPEED / speed[too_fast])[:, None]
        self.positions = self.positions + self.velocities * dt
        self._update_trails()
        self._check_collisions()
        self._check_planet_collisions()
        self._cull_escaped_bodies()

    def _radius_for_mass(self, mass):
        return np.clip(mass ** (1 / 3) * self.RADIUS_SCALE, self.MIN_DRAW_RADIUS, self.MAX_DRAW_RADIUS)

    def _check_collisions(self):
        """Check if any planets have passed too close to the star and absorb them.
        Planets within COLLISION_RADIUS_FRACTION of the star's visual radius are absorbed.
        Distances to every planet are computed in one vectorized batch rather
        than via a per-planet np.linalg.norm call -- with dozens of bodies,
        the per-call overhead of looping in Python adds up every frame."""
        if len(self.masses) < 2:
            return

        star_pos = self.positions[0]
        collision_radius = self._radius_for_mass(self.masses[0]) * self.COLLISION_RADIUS_FRACTION

        diffs = self.positions[1:] - star_pos
        dists = np.sqrt(np.sum(diffs * diffs, axis=1))
        to_absorb = np.nonzero(dists <= collision_radius)[0] + 1  # +1: shift back into full-array indices
        if len(to_absorb) == 0:
            return

        self.masses[0] += self.masses[to_absorb].sum()
        keep = np.ones(len(self.masses), dtype=bool)
        keep[to_absorb] = False
        self.positions = self.positions[keep]
        self.velocities = self.velocities[keep]
        self.masses = self.masses[keep]
        self.colors = [c for c, k in zip(self.colors, keep) if k]
        self.trails = [t for t, k in zip(self.trails, keep) if k]

    def _check_planet_collisions(self):
        """Check planets (indices > 0; the star at index 0 is handled
        separately by _check_collisions) against each other and resolve any
        that overlap, by either merging or shattering them. Operates on a
        snapshot of the current arrays so resolving one pair never disturbs
        the indices used to resolve another pair in the same frame.

        The full pairwise distance matrix is computed in one vectorized numpy
        batch (same trick as compute_gravitational_acceleration) instead of
        calling np.linalg.norm per pair in a Python double loop -- that loop
        used to cost O(n^2) *Python-level* numpy calls every frame even when
        nothing was colliding. Only candidate colliding pairs (almost always
        zero) go through the still-Python greedy claim loop below."""
        n = len(self.masses)
        if n < 3:  # need the star plus at least 2 planets
            return

        radii = self._radius_for_mass(self.masses)
        planet_pos = self.positions[1:]
        planet_radii = radii[1:]
        diffs = planet_pos[:, None, :] - planet_pos[None, :, :]
        dist = np.sqrt(np.sum(diffs * diffs, axis=2))
        threshold = (planet_radii[:, None] + planet_radii[None, :]) * self.PLANET_COLLISION_RADIUS_FRACTION
        colliding = np.triu(dist <= threshold, k=1)
        local_i, local_j = np.nonzero(colliding)

        claimed = np.zeros(n, dtype=bool)
        pairs = []
        for li, lj in zip(local_i, local_j):
            i, j = int(li) + 1, int(lj) + 1  # +1: shift back into full-array indices (star is index 0)
            if claimed[i] or claimed[j]:
                continue
            pairs.append((i, j))
            claimed[i] = True
            claimed[j] = True

        if not pairs:
            return

        new_bodies = [self._resolve_planet_collision(i, j) for i, j in pairs]

        keep = ~claimed
        self.positions = self.positions[keep]
        self.velocities = self.velocities[keep]
        self.masses = self.masses[keep]
        self.colors = [c for c, k in zip(self.colors, keep) if k]
        self.trails = [t for t, k in zip(self.trails, keep) if k]

        for bodies in new_bodies:
            for pos, vel, mass in bodies:
                if len(self.masses) >= self.MAX_BODIES:
                    break  # fragments past the cap are dropped, same as a tap/launch spawn would be
                self.positions = np.vstack([self.positions, pos])
                self.velocities = np.vstack([self.velocities, vel])
                self.masses = np.append(self.masses, mass)
                self._add_color_and_trail()

    def _resolve_planet_collision(self, i, j):
        """Resolve a collision between planets i and j, returning a list of
        (position, velocity, mass) tuples for the body/bodies it becomes.
        Slow grazes merge into one body; impacts faster than the pair's
        mutual escape velocity shatter into capped, momentum-conserving
        fragments, each at least MIN_FRAGMENT_MASS so the screen doesn't
        fill up with specks."""
        m1, m2 = self.masses[i], self.masses[j]
        total_mass = m1 + m2
        pos1, pos2 = self.positions[i], self.positions[j]
        vel1, vel2 = self.velocities[i], self.velocities[j]

        v_com = (m1 * vel1 + m2 * vel2) / total_mass
        relative_speed = float(np.linalg.norm(vel1 - vel2))
        collision_point = (m1 * pos1 + m2 * pos2) / total_mass

        contact_dist = float(self._radius_for_mass(m1) + self._radius_for_mass(m2))
        mutual_escape_speed = math.sqrt(2 * self.G * total_mass / contact_dist)

        max_fragments = int(total_mass // self.MIN_FRAGMENT_MASS)
        shatters = relative_speed > mutual_escape_speed * self.FRAGMENTATION_SPEED_FACTOR
        fragment_count = min(self.MAX_FRAGMENTS, max_fragments) if shatters and max_fragments >= 2 else 1

        if fragment_count == 1:
            return [(collision_point, v_com, total_mass)]

        rng = np.random.default_rng()
        leftover = total_mass - fragment_count * self.MIN_FRAGMENT_MASS
        frag_masses = self.MIN_FRAGMENT_MASS + leftover * rng.dirichlet(np.ones(fragment_count))

        # Spread fragments evenly around the impact point (with jitter) and
        # give each an outward kick, then remove the mass-weighted average
        # kick from all of them so total momentum still equals the
        # pre-collision total -- the spread looks like debris without
        # injecting or losing momentum.
        ejecta_speed = relative_speed * self.EJECTA_SPEED_FACTOR
        base_angle = rng.uniform(0, 2 * np.pi)
        angles = (
            base_angle
            + np.arange(fragment_count) * (2 * np.pi / fragment_count)
            + rng.uniform(-0.3, 0.3, fragment_count)
        )
        directions = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        kicks_raw = directions * ejecta_speed
        net_bias = np.sum(frag_masses[:, None] * kicks_raw, axis=0) / total_mass
        kicks = kicks_raw - net_bias

        bodies = []
        for k in range(fragment_count):
            separation = contact_dist * 0.5 + self._radius_for_mass(frag_masses[k])
            frag_pos = collision_point + directions[k] * separation
            frag_vel = v_com + kicks[k]
            bodies.append((frag_pos, frag_vel, frag_masses[k]))
        return bodies

    def _update_trails(self):
        for i, pos in enumerate(self.positions):
            self.trails[i].append((float(pos[0]), float(pos[1])))

    def _cull_escaped_bodies(self):
        # Centered on the star's current (drifting) position rather than the
        # screen center, since the star is no longer snapped back to it.
        cx, cy = self.positions[0]
        bound_x = self.width * self.TRACKING_AREA_MULTIPLIER / 2
        bound_y = self.height * self.TRACKING_AREA_MULTIPLIER / 2
        within = (np.abs(self.positions[:, 0] - cx) <= bound_x) & (
            np.abs(self.positions[:, 1] - cy) <= bound_y
        )
        if not within.all():
            self.positions = self.positions[within]
            self.velocities = self.velocities[within]
            self.masses = self.masses[within]
            self.colors = [c for c, keep in zip(self.colors, within) if keep]
            self.trails = [t for t, keep in zip(self.trails, within) if keep]

    def draw(self, surface):
        surface.fill(BG_COLOR)
        n = len(self.masses)
        if n == 0:
            return
        # Screen positions and draw radii for every body are computed once,
        # in two vectorized numpy calls, rather than recomputing the camera
        # transform and radius formula from scratch inside a per-body call --
        # with dozens of bodies redone every frame, that per-call overhead
        # was a meaningful chunk of frame time on its own.
        screen_positions = self._world_to_screen(self.positions)
        radii = np.maximum(1, (self._radius_for_mass(self.masses) * self.zoom)).astype(int)

        # The star (always index 0) is drawn last -- trail and body -- so it
        # always renders on top of every planet trail and body, never the
        # other way around.
        for i in range(1, n):
            color = self.colors[i]
            _draw_trail(surface, self.trails[i], color, self._world_to_screen)
            self._draw_body(surface, screen_positions[i], radii[i], color)

        _draw_trail(
            surface, self.trails[0], STAR_COLOR, self._world_to_screen,
            dark_fraction=STAR_TRAIL_DARK_FRACTION,
        )
        self._draw_body(surface, screen_positions[0], radii[0], STAR_COLOR)

        self._draw_launch_preview(surface)
        self._draw_sliders(surface)

    def _draw_body(self, surface, screen_pos, radius, color):
        pygame.draw.circle(surface, color, (int(screen_pos[0]), int(screen_pos[1])), int(radius))

    def _draw_sliders(self, surface):
        top_y, bottom_y = self._slider_track_y()
        zoom_frac = _inverse_log_lerp(self.ZOOM_MIN, self.ZOOM_MAX, self._zoom_target)
        speed_frac = _inverse_log_lerp(self.SPEED_MIN, self.SPEED_MAX, self.speed)
        self._draw_slider(
            surface, self.SLIDER_EDGE_MARGIN, top_y, bottom_y, speed_frac, f"{self.speed:.1f}x", "SPEED"
        )
        self._draw_slider(
            surface, self.width - self.SLIDER_EDGE_MARGIN, top_y, bottom_y, zoom_frac,
            f"{self._zoom_target:.1f}x", "ZOOM",
        )

    def _draw_slider(self, surface, x, top_y, bottom_y, frac, value_text, label):
        x = int(x)
        knob_y = int(bottom_y - frac * (bottom_y - top_y))
        # Track, then the filled portion from the bottom up to the knob, then
        # the knob itself -- a thin, unobtrusive bar with a clear handle.
        pygame.draw.line(surface, self.SLIDER_TRACK_COLOR, (x, int(top_y)), (x, int(bottom_y)), 2)
        pygame.draw.line(surface, self.SLIDER_FILL_COLOR, (x, int(bottom_y)), (x, knob_y), 2)
        pygame.draw.circle(surface, self.SLIDER_KNOB_COLOR, (x, knob_y), self.SLIDER_KNOB_RADIUS)
        self._draw_centered_text(surface, value_text, x, int(top_y) - 14)
        self._draw_centered_text(surface, label, x, int(bottom_y) + 14)

    def _draw_centered_text(self, surface, text, cx, cy):
        rendered = self.font.render(text, True, self.SLIDER_LABEL_COLOR)
        rect = rendered.get_rect(center=(cx, cy))
        rect.clamp_ip(surface.get_rect())
        surface.blit(rendered, rect)

    def _draw_launch_preview(self, surface):
        points = self._predict_launch_trajectory()
        if len(points) < 2:
            return
        screen_points = self._world_to_screen(np.array(points)).tolist()
        pygame.draw.lines(surface, self.LAUNCH_PREVIEW_COLOR, False, screen_points, 1)
        ox, oy = screen_points[0]
        pygame.draw.circle(surface, self.LAUNCH_PREVIEW_COLOR, (int(ox), int(oy)), 5, 1)


def _log_lerp(lo, hi, frac):
    """Geometric interpolation between lo and hi: frac 0 -> lo, frac 1 -> hi,
    with the midpoint at their geometric mean. Used for the zoom and speed
    sliders so each equal step of the knob is an equal *ratio* of change, which
    is what feels linear for a multiplicative quantity."""
    return float(lo * (hi / lo) ** frac)


def _inverse_log_lerp(lo, hi, value):
    """Inverse of _log_lerp: the 0..1 knob fraction that maps to value."""
    return float(math.log(value / lo) / math.log(hi / lo))


def _planet_color(seed_index):
    """Deterministic, well-separated hue per index via golden-ratio stepping
    -- stays visually distinct from its neighbors even as the number of
    simultaneously-visible planets changes from adds/culls."""
    hue = (seed_index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


# Trails are drawn as this many flat-colored polyline segments (each a
# single pygame.draw.lines call) instead of one pygame.draw.line call per
# point -- with TRAIL_LENGTH=90 and dozens of bodies on screen, one draw
# call per segment per body per frame was the single biggest cost in the
# whole demo. Bucketing trades a perfectly smooth gradient for a handful of
# visible color steps, which is not noticeable at trail scale.
TRAIL_COLOR_BUCKETS = 6


def _draw_trail(surface, trail, color, to_screen, dark_fraction=TRAIL_DARK_FRACTION):
    n = len(trail)
    if n < 2:
        return
    # One vectorized batch transform for every point in the trail, instead of
    # calling to_screen() once per point.
    screen_pts = to_screen(np.array(trail, dtype=float)).tolist()
    dark = tuple(int(c * dark_fraction) for c in color)
    buckets = min(TRAIL_COLOR_BUCKETS, n - 1)
    edges = np.linspace(0, n - 1, buckets + 1).round().astype(int)
    for b in range(buckets):
        start, end = edges[b], edges[b + 1]
        if end <= start:
            continue
        line_color = _lerp_color(dark, color, end / (n - 1))
        pygame.draw.lines(surface, line_color, False, screen_pts[start : end + 1], 2)


def _lerp_color(c0, c1, t):
    return (
        int(c0[0] + (c1[0] - c0[0]) * t),
        int(c0[1] + (c1[1] - c0[1]) * t),
        int(c0[2] + (c1[2] - c0[2]) * t),
    )


def compute_gravitational_acceleration(positions, masses, *, g, softening):
    """Pure numpy pairwise gravity, independent of pygame, so it's testable
    without a display. acc[i] = G * sum_j masses[j] * (pos[j] - pos[i]) /
    (dist_ij^2 + softening^2)^1.5 -- the softening term keeps this finite as
    dist_ij -> 0 instead of diverging. The diagonal (j == i) is zeroed
    explicitly: with softening == 0 it would otherwise be 0 * inf (nan)
    rather than the 0 it should contribute.
    """
    n = len(positions)
    if n == 0:
        return np.zeros_like(positions)

    diffs = positions[None, :, :] - positions[:, None, :]  # diffs[i, j] = pos[j] - pos[i]
    dist_sq = np.sum(diffs * diffs, axis=2)
    np.fill_diagonal(dist_sq, 1.0)  # avoid a 0**-1.5 div-by-zero warning; zeroed out below anyway
    inv_dist_cubed = (dist_sq + softening**2) ** -1.5
    np.fill_diagonal(inv_dist_cubed, 0.0)
    return g * np.sum(diffs * (masses[None, :, None] * inv_dist_cubed[:, :, None]), axis=1)
