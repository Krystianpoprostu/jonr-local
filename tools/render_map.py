"""Re-render a saved map dump fully offline (no network): map_raw.json -> map.png + json views.

    python tools/render_map.py [dump_dir]     # default: local_data/map_dumps/latest
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump_map import ROOT, render_dump  # noqa: E402

dump = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "local_data" / "map_dumps" / "latest"
attrs = render_dump(dump.resolve())
print(f"OK: {dump.resolve() / 'map.png'}  ({attrs['image_width']}x{attrs['image_height']}, "
      f"{len(attrs['rooms'])} pokoi, map_id={attrs['map_id']})")
