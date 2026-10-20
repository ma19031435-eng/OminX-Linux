#!/usr/bin/env python3
"""Export a bounded preview of an actual QEMU capture; never synthesize UI pixels."""
import base64
import io
from pathlib import Path
from PIL import Image

source = Path('build/acceptance/quick-bochs-target-quick.ppm')
output = Path('build/acceptance/quick-preview.png')
with Image.open(source) as captured:
    captured = captured.convert('RGB')
    encoded = None
    for width in (800, 640):
        scaled = captured.resize((width, round(captured.height * width / captured.width)))
        for colors in (128, 64, 32, 16):
            buffer = io.BytesIO()
            scaled.quantize(colors=colors).save(buffer, format='PNG', optimize=True)
            payload = buffer.getvalue()
            candidate = base64.b64encode(payload).decode('ascii')
            if len(candidate) <= 30000:
                output.write_bytes(payload)
                encoded = candidate
                break
        if encoded is not None:
            break
    if encoded is None:
        raise SystemExit('Preview exceeds annotation budget; full screenshot remains in artifact')
chunks = [encoded[i:i+3000] for i in range(0, len(encoded), 3000)]
for index, chunk in enumerate(chunks):
    print(f'::notice title=quick-preview-{index:02d}-{len(chunks):02d}::{chunk}')
