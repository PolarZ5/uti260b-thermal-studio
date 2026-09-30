"""Screen geometry of the UTi260B live view (portrait 240 x 320).

Measured from screen captures stored in the camera's BMP files. The USB
"PC Camera" stream mirrors this screen, so the same geometry is used to find
the colour bar and the max/min labels in live frames.
"""

SCREEN_W = 240
SCREEN_H = 320

# Colour bar: rows BAR_TOP..BAR_BOTTOM (inclusive), top = hottest (index 255)
BAR_X0, BAR_X1 = 225, 235          # columns [x0, x1)
BAR_TOP, BAR_BOTTOM = 58, 252

# Right-aligned max/min labels above/below the colour bar
LABEL_MAX_Y = (39, 52)             # rows [y0, y1)
LABEL_MIN_Y = (258, 271)
# Fixed character cells, right to left: last digit, '.', then digits/minus
LABEL_CELLS = [(226, 234), (220, 225), (210, 219), (200, 210), (190, 200), (180, 190)]
DOT_CELL = 1

# Regions covered by the on-screen display that must not be measured
OSD_MASK_RECTS = [
    (0, 0, SCREEN_W, 34),          # top bar: centre reading, date/time, battery
    (180, 34, SCREEN_W, 56),       # max label
    (220, 54, SCREEN_W, 256),      # colour bar
    (180, 254, SCREEN_W, 276),     # min label
]

# Camera main menu (SET button): dark bar along the bottom, tooltip above the selected icon
MENU_X0, MENU_X1 = 12, 228
MENU_TOP_EDGE = (272, 284)         # rows searched for the bar's dark top border
MENU_BOTTOM_EDGE = (308, 320)      # rows searched for its dark bottom border
MENU_MASK_Y0 = 250                 # mask everything below this row while the menu is open

CENTER = (SCREEN_W // 2, SCREEN_H // 2)
