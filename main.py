#!/usr/bin/env python3
"""Idle-art display: cycles between fun generative demos (boids, maze,
fractal, dvd, snake) on keyboard input or touchscreen swipe -- it never
auto-advances. See README.md and docs/pi-setup.md for hardware setup."""

import argparse
import os
import queue
import sys

import pygame

from display import config
from display.demos import ALL_DEMOS
from display.input_touch import TouchInputThread
from display.manager import DemoManager, NavEvent
from display.streaming import FrameStreamer, start_server


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="run in a normal desktop window instead of the Pi's kmsdrm framebuffer",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="quit automatically after N frames (useful for smoke tests)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="don't serve the live display preview over HTTP",
    )
    return parser.parse_args(argv)


def configure_video_driver(windowed):
    if windowed or os.environ.get("SDL_VIDEODRIVER"):
        return
    if os.path.exists("/dev/dri"):
        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def main(argv=None):
    args = parse_args(argv)
    configure_video_driver(args.windowed)

    pygame.init()

    # On the Pi, kmsdrm always renders fullscreen at the display's native
    # resolution -- no extra fullscreen flag needed.
    screen = pygame.display.set_mode(config.SCREEN_SIZE)
    pygame.display.set_caption("Idle Display")
    pygame.mouse.set_visible(False)

    manager = DemoManager([demo_cls() for demo_cls in ALL_DEMOS])
    manager.setup(screen.get_size())

    input_queue = queue.Queue()
    touch_thread = TouchInputThread(
        input_queue,
        swipe_threshold_px=config.SWIPE_THRESHOLD_PX,
        tap_max_duration=config.TAP_MAX_DURATION,
        tap_max_distance_px=config.TAP_MAX_DISTANCE_PX,
        long_press_min_duration=config.LONG_PRESS_MIN_DURATION,
    )
    touch_thread.start()

    streamer = None
    if not args.no_stream:
        streamer = FrameStreamer(config.STREAM_DEFAULT_FPS, rotate_degrees=config.STREAM_ROTATE_DEGREES)
        start_server(streamer, config.STREAM_PORT, nav_queue=input_queue)
        print(f"==> Preview stream: http://<this-device-ip>:{config.STREAM_PORT}/")

    clock = pygame.time.Clock()
    frame_count = 0
    running = True

    while running:
        dt = clock.tick(config.FPS) / 1000.0

        while not input_queue.empty():
            input_event = input_queue.get_nowait()
            if isinstance(input_event, NavEvent):
                manager.handle_nav(input_event)
            else:
                manager.current.handle_touch(input_event)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    manager.handle_nav(NavEvent.NEXT)
                elif event.key == pygame.K_LEFT:
                    manager.handle_nav(NavEvent.PREV)
            manager.current.handle_event(event)

        manager.update(dt)
        manager.draw(screen)
        pygame.display.flip()

        if streamer is not None:
            streamer.update_frame(screen)

        frame_count += 1
        if args.max_frames is not None and frame_count >= args.max_frames:
            running = False

    touch_thread.stop()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
