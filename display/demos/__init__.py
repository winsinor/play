from display.demos.boids import BoidsDemo
from display.demos.maze import MazeDemo
from display.demos.fractal import FractalDemo

# Order here is the cycle order shown on screen. To add a new demo: write a
# display/demos/<name>.py module with a class implementing display.demos.base.Demo,
# then add it to this list.
ALL_DEMOS = [BoidsDemo, MazeDemo, FractalDemo]
