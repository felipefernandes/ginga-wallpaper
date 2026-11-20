"""Run the renderer on its own (no desktop attach, no tray) and report its cost.

The window covers the whole desktop on top of other windows until task 7
attaches it behind the icons. Esc (when focused) or Ctrl+C stops it.

Usage:
    python scripts/run_renderer.py --seconds 10 [--fps 30] [--pause-after 5]
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

from ginga.config import load_config
from ginga.renderer import Renderer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0, help="stop after N seconds")
    parser.add_argument("--fps", type=int, help="override config fps")
    parser.add_argument("--pause-after", type=float, help="manually pause after N seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = load_config()
    if args.fps:
        config.render.fps = args.fps
    renderer = Renderer(config)

    timers = [threading.Timer(args.seconds, renderer.stop)]
    if args.pause_after is not None:
        timers.append(threading.Timer(args.pause_after, renderer.set_paused, (True,)))
    for t in timers:
        t.daemon = True
        t.start()

    wall, cpu = time.perf_counter(), time.process_time()
    try:
        renderer.run()
    except KeyboardInterrupt:
        pass
    wall, cpu = time.perf_counter() - wall, time.process_time() - cpu
    print(
        f"{renderer.frames} frames in {wall:.1f}s = {renderer.frames / wall:.1f} fps "
        f"(target {config.render.fps}); CPU {100 * cpu / wall:.1f}% of one core"
    )


if __name__ == "__main__":
    main()
