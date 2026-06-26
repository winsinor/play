import numpy as np
import pygame
import pytest

from display.demos.stellar_collision import StellarCollisionDemo
from display.manager import TapEvent


@pytest.fixture
def demo():
    pygame.init()
    d = StellarCollisionDemo()
    d.setup((800, 480))
    return d


def test_setup_starts_with_two_systems_running(demo):
    # Two stars + PLANETS_PER_SYSTEM planets each.
    assert len(demo.masses) == 2 * (1 + demo.PLANETS_PER_SYSTEM)
    assert demo.phase == "running"


def test_physics_never_goes_non_finite_across_many_random_encounters():
    pygame.init()
    for seed in range(25):
        np.random.seed(seed)
        d = StellarCollisionDemo()
        d.setup((800, 480))
        for _ in range(2200):  # comfortably past MAX_RUN_SECONDS at 60fps
            d.update(1 / 60)
            assert len(d.masses) > 0
            assert np.isfinite(d.positions).all()
            assert np.isfinite(d.velocities).all()
            assert len(d.masses) <= d.MAX_BODIES


def test_large_dt_spike_does_not_blow_up_positions(demo):
    demo.update(5.0)
    assert np.isfinite(demo.positions).all()
    assert np.isfinite(demo.velocities).all()


def test_encounter_ends_in_pause_then_restarts(demo):
    demo.MAX_RUN_SECONDS = 0.0  # force an immediate timeout
    demo.update(1 / 60)
    assert demo.phase == "paused"

    demo.pause_timer = demo.END_PAUSE_SECONDS
    demo.update(1 / 60)
    assert demo.phase == "running"
    assert demo.elapsed == 0.0


def test_single_surviving_body_ends_the_encounter(demo):
    demo.positions = demo.positions[:1]
    demo.velocities = demo.velocities[:1]
    demo.masses = demo.masses[:1]
    demo.colors = demo.colors[:1]
    demo.trails = demo.trails[:1]
    demo.update(1 / 60)
    assert demo.phase == "paused"


def test_tap_restarts_the_encounter_immediately(demo):
    demo.elapsed = 5.0
    demo.handle_touch(TapEvent(100, 100))
    assert demo.elapsed == 0.0
    assert demo.phase == "running"


def test_star_star_collision_merges_or_shatters_with_conserved_mass(demo):
    # Force the two stars (indices 0 and 5, given PLANETS_PER_SYSTEM=5) to
    # collide head-on, fast enough to be eligible for shattering, and check
    # total mass is conserved either way.
    star_a, star_b = 0, 1 + demo.PLANETS_PER_SYSTEM
    total_mass_before = demo.masses[star_a] + demo.masses[star_b]
    demo.positions[star_a] = [100.0, 100.0]
    demo.positions[star_b] = [100.0, 100.0]
    demo.velocities[star_a] = [-500.0, 0.0]
    demo.velocities[star_b] = [500.0, 0.0]

    bodies = demo._resolve_collision(star_a, star_b)

    assert len(bodies) >= 1
    total_mass_after = sum(b[2] for b in bodies)
    assert total_mass_after == pytest.approx(total_mass_before)


def test_resolve_collision_conserves_momentum_when_it_shatters(demo):
    star_a, star_b = 0, 1 + demo.PLANETS_PER_SYSTEM
    m1, m2 = demo.masses[star_a], demo.masses[star_b]
    demo.velocities[star_a] = [-500.0, 0.0]
    demo.velocities[star_b] = [500.0, 0.0]
    momentum_before = m1 * demo.velocities[star_a] + m2 * demo.velocities[star_b]

    bodies = demo._resolve_collision(star_a, star_b)

    momentum_after = sum(np.array(vel) * mass for _, vel, mass, _ in bodies)
    assert np.allclose(momentum_after, momentum_before, atol=1e-6)
