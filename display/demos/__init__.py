from display.demos.boids import BoidsDemo
from display.demos.maze import MazeDemo
from display.demos.fractal import FractalDemo
from display.demos.dvd import DvdDemo
from display.demos.snake import SnakeDemo
from display.demos.life import LifeDemo
from display.demos.nbody import NBodyDemo
from display.demos.plinko import PlinkoDemo

# Order here is the cycle order shown on screen, and the first entry is what
# comes up on boot. To add a new demo: write a display/demos/<name>.py module
# with a class implementing display.demos.base.Demo, then add it to this list.
# DrawDemo (display/demos/draw.py) is the touch-alignment test screen and is
# deliberately left out of the rotation -- import it directly if you need it.
ALL_DEMOS = [BoidsDemo, MazeDemo, FractalDemo, DvdDemo, SnakeDemo, LifeDemo, NBodyDemo, PlinkoDemo]
