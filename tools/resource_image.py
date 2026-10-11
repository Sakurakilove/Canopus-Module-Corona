#!/usr/bin/env python3
"""Convert LVGL v9 I8 / I8-RLE images and extract files from ROMFS.

Requires Pillow for PNG operations. Palette bytes are interpreted as BGRA,
following LVGL's lv_color32_t layout; device rendering is not verified here.
"""
import argparse
from pathlib import Path
import struct
import sys

HEADER = struct.Struct('<BBHHHHH')
MAX_PAYLOAD = 64 * 1024 * 1024


def image_payload(data):
    if len(data) < HEADER.size:
        raise ValueError('Truncated I8 image')
    magic, color, flags, width, height, stride, reserved = HEADER.unpack_from(data)
    if magic != 0x19 or color != 0x0A or flags not in (0, 8) or reserved:
        raise ValueError('Only LVGL v9 I8 and I8-RLE images are supported')
    if not width or not height or stride < width or width * height > 16 * 1024 * 1024:
        raise ValueError('Invalid dimensions or stride')
    expected = 1024 + stride * height
    if expected > MAX_PAYLOAD:
        raise ValueError('I8 image exceeds payload limit')
    if not flags:
        if len(data) != 12 + expected:
            raise ValueError('Image size does not match header and 256-entry palette')
        return data[12:]
    if len(data) < 24:
        raise ValueError('Truncated RLE header')
    method, packed, expanded = struct.unpack_from('<III', data, 12)
    if method != 1 or len(data) != 24 + packed or not expected <= expanded <= MAX_PAYLOAD:
        raise ValueError('Invalid RLE method, size or expanded payload')
    stream, out, cursor = data[24:], bytearray(), 0
    while cursor < len(stream):
        control = stream[cursor]
        cursor += 1
        count = control & 0x7F
        if not count or len(out) + count > expanded:
            raise ValueError('Invalid RLE run length')
        if control & 0x80:
            if cursor + count > len(stream):
                raise ValueError('Truncated RLE literal')
            out.extend(stream[cursor:cursor + count])
            cursor += count
        else:
            if cursor >= len(stream):
                raise ValueError('Truncated RLE repeated byte')
            out.extend(bytes((stream[cursor],)) * count)
            cursor += 1
    if len(out) != expanded:
        raise ValueError('RLE expanded size mismatch')
    return bytes(out)


def compress_rle(payload):
    """LVGL method 1: high bit is a literal, low seven bits are byte count."""
    out, cursor = bytearray(), 0
    while cursor < len(payload):
        end = cursor + 1
        while end < min(cursor + 127, len(payload)) and payload[end] == payload[cursor]:
            end += 1
        if end - cursor >= 3:
            out.extend((end - cursor, payload[cursor]))
            cursor = end
            continue
        start = cursor
        cursor = end
        while cursor < len(payload) and cursor - start < 127:
            if cursor + 2 < len(payload) and payload[cursor] == payload[cursor + 1] == payload[cursor + 2]:
                break
            cursor += 1
        out.append(0x80 | (cursor - start))
        out.extend(payload[start:cursor])
    return bytes(out)


def parse_image(data):
    payload = image_payload(data)
    magic, color, flags, width, height, stride, reserved = HEADER.unpack_from(data)
    palette = [(payload[i + 2], payload[i + 1], payload[i], payload[i + 3])
               for i in range(0, 1024, 4)]
    return width, height, stride, palette


def decode(data):
    from PIL import Image
    width, height, stride, palette = parse_image(data)
    image = Image.new('RGBA', (width, height))
    payload = image_payload(data)
    image.putdata([palette[index] for y in range(height)
                   for index in payload[1024 + y * stride:1024 + y * stride + width]])
    return image


def rgba_pixels(image):
    raw = image.tobytes()
    return list(zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4]))


def encode(image, template, quantize=False):
    from PIL import Image
    width, height, stride, palette = parse_image(template)
    image = image.convert('RGBA')
    if image.size != (width, height):
        raise ValueError(f'Expected {width}x{height}; resizing is intentionally disabled')
    pixels = rgba_pixels(image)
    # Preserve unused entries, duplicate indices, and row padding on exact round trips.
    if image.tobytes() == decode(template).tobytes():
        return template
    lookup = {color: i for i, color in reversed(list(enumerate(palette)))}
    result = bytearray(image_payload(template))
    if all(color in lookup for color in pixels):
        indices = bytes(lookup[color] for color in pixels)
    else:
        colors = list(dict.fromkeys(pixels))
        if len(colors) > 256:
            if not quantize:
                raise ValueError('PNG has more than 256 RGBA colors; pass --quantize for lossy conversion')
            image = image.quantize(colors=256, method=Image.Quantize.FASTOCTREE,
                                   dither=Image.Dither.NONE).convert('RGBA')
            pixels = rgba_pixels(image)
            colors = list(dict.fromkeys(pixels))
        lookup = {color: i for i, color in enumerate(colors)}
        result[:1024] = b''.join(bytes((b, g, r, a)) for r, g, b, a in colors).ljust(1024, b'\0')
        indices = bytes(lookup[color] for color in pixels)
    for y in range(height):
        start = 1024 + y * stride
        result[start:start + width] = indices[y * width:(y + 1) * width]
    if HEADER.unpack_from(template)[2] == 8:
        packed = compress_rle(result)
        return template[:12] + struct.pack('<III', 1, len(packed), len(result)) + packed
    return template[:12] + bytes(result)


def extract_romfs(data, path):
    if data[:8] != b'-rom1fs-' or len(data) < 32:
        raise ValueError('Not a ROMFS image')
    total = struct.unpack_from('>I', data, 8)[0]
    if total > len(data) or total < 32:
        raise ValueError('Invalid ROMFS size')
    data = data[:total]

    def name(offset):
        end = data.find(b'\0', offset)
        if end < 0:
            raise ValueError('Unterminated ROMFS name')
        return data[offset:end].decode('utf-8'), (end + 16) & ~15

    if not path.startswith('/') or any(p in ('', '.', '..') for p in path[1:].split('/')):
        raise ValueError('Use an absolute ROMFS path without empty or dot components')
    if path.startswith('/resource/'):
        path = path[len('/resource'):]
    _, root = name(16)
    pending = [(root, '')]
    seen = set()
    while pending:
        offset, parent = pending.pop()
        while offset:
            if offset in seen or offset % 16 or offset < 32 or offset + 16 > total:
                raise ValueError('Invalid or cyclic ROMFS entry')
            seen.add(offset)
            nxt, spec, size, _ = struct.unpack_from('>IIII', data, offset)
            entry, content = name(offset + 16)
            kind = nxt & 7
            current = parent if entry in ('.', '..') else parent + '/' + entry
            # The initial '.' may introduce the root chain. A nested '.' that
            # points back to itself is a directory marker, not another subtree.
            if kind == 1 and entry != '..' and (entry != '.' or spec != offset):
                pending.append((spec, current))
            elif current == path:
                if kind != 2:
                    raise ValueError('Requested entry is not a regular file')
                if content + size > total:
                    raise ValueError('Truncated ROMFS file')
                return data[content:content + size]
            offset = nxt & ~15
    raise ValueError(f'File not found in ROMFS: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    extract = commands.add_parser('extract', help='Extract one regular file, without modifying firmware')
    extract.add_argument('romfs', type=Path)
    extract.add_argument('resource_path')
    extract.add_argument('output', type=Path)
    dec = commands.add_parser('decode', help='Convert a supported I8 BIN to RGBA PNG')
    dec.add_argument('input', type=Path)
    dec.add_argument('output', type=Path)
    enc = commands.add_parser('encode', help='Convert PNG using an original BIN header/template')
    enc.add_argument('input', type=Path)
    enc.add_argument('output', type=Path)
    enc.add_argument('--template', type=Path, required=True)
    enc.add_argument('--quantize', action='store_true', help='Allow lossy RGBA quantization to 256 colors')
    args = parser.parse_args()
    try:
        if args.command == 'extract':
            result = extract_romfs(args.romfs.read_bytes(), args.resource_path)
        elif args.command == 'decode':
            import io
            buffer = io.BytesIO()
            decode(args.input.read_bytes()).save(buffer, format='PNG')
            result = buffer.getvalue()
        else:
            from PIL import Image
            with Image.open(args.input) as image:
                if image.format != 'PNG':
                    raise ValueError('Input must be PNG')
                result = encode(image, args.template.read_bytes(), args.quantize)
        # Exclusive creation protects templates, firmware, and previous edits.
        with args.output.open('xb') as output:
            output.write(result)
        print(f'Wrote {args.output} ({len(result)} bytes)')
    except (ValueError, OSError, ImportError, struct.error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
