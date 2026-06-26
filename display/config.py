SCREEN_SIZE = (800, 480)
FPS = 60

SWIPE_THRESHOLD_PX = 60
TAP_MAX_DURATION = 0.3
TAP_MAX_DISTANCE_PX = 20
LONG_PRESS_MIN_DURATION = 0.6

# Software fallback for touch axis alignment, for panels where no combination
# of the kernel's touchscreen-swapped-x-y/-inverted-x/-inverted-y dtparam
# flags (see docs/pi-setup.md) fixes it -- e.g. because too many touchscreen
# params stacked on one dtparam line get silently truncated by the overlay
# parser. Leave all False if the dtparam combo already works; otherwise set
# whichever combination here makes a tap land where you actually touched.
TOUCH_SWAP_XY = False
TOUCH_INVERT_X = False
TOUCH_INVERT_Y = False

STREAM_PORT = 8000
# The physical HyperPixel rotation is handled entirely by the KMS
# dtparam=rotate boot config (see docs/pi-setup.md) and never touches the
# pygame surface -- so the raw frame grabbed for the web preview is in the
# *unrotated* logical orientation. Rotate it here purely for the preview
# image (pygame.transform.rotate, counterclockwise); if it comes out the
# wrong way, try -90 instead.
STREAM_ROTATE_DEGREES = 90
