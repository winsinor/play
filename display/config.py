SCREEN_SIZE = (800, 480)
FPS = 60

SWIPE_THRESHOLD_FRACTION = 0.8  # fraction of screen width a swipe must cross
TAP_MAX_DURATION = 0.3
TAP_MAX_DISTANCE_PX = 20
LONG_PRESS_MIN_DURATION = 2.0

# Single source of truth for physical mounting orientation. Demos always
# draw onto an unrotated SCREEN_SIZE canvas; main.py rotates that canvas in
# software before it hits the real display, and the touch thread applies
# the matching inverse to raw touch coordinates -- so the screen and the
# touch input can never drift out of sync with each other the way separate
# kernel-level dtparam=rotate + touchscreen-swapped-x-y/-inverted-* flags
# could (see docs/pi-setup.md for why that approach was dropped).
#
# config.txt on the Pi should have *only* dtoverlay=vc4-kms-dpi-hyperpixel4
# -- no dtparam=rotate, no touchscreen-* params. Counterclockwise degrees,
# one of 0/90/180/270; pick whichever makes the Draw demo show upright with
# correct touch alignment for your physical mount. No reboot needed to
# change this -- just restart main.py.
DISPLAY_ROTATE_DEGREES = 270

STREAM_PORT = 8000
