#!/usr/bin/env python3
"""
ANI 커서 리사이저
알파 채널을 올바르게 처리하는 고품질 리사이즈.
업스케일링(예: 32→48)과 다운스케일링(예: 128→48) 모두 지원.

Premultiplied alpha + Lanczos 리샘플링으로 부드러운 가장자리를 유지하고,
32bpp ARGB 커서 프레임으로 출력하여 안티앨리어싱된 투명도를 보존.

Usage:
    python ani-scale.py input.ani -o output.ani                    # 소스 크기 자동 감지, 대상=48
    python ani-scale.py input.ani -o output.ani -s 128 -t 48      # 크기 직접 지정
    python ani-scale.py *.ani -o output_dir/ -s 32 -t 48          # 배치 처리
"""

import struct
import sys
import os
import argparse
import numpy as np
from PIL import Image


# ─── ANI 파싱 ────────────────────────────────────────────────────────────────

def read_u16(data, off):
    return struct.unpack_from('<H', data, off)[0]

def read_u32(data, off):
    return struct.unpack_from('<I', data, off)[0]

def read_i32(data, off):
    return struct.unpack_from('<i', data, off)[0]


def parse_ani(data):
    """ANI 파일을 파싱하여 헤더 정보와 아이콘 프레임을 반환."""
    assert data[0:4] == b'RIFF', 'Not a RIFF file'
    assert data[8:12] == b'ACON', 'Not an ANI file'

    result = {
        'anih': None,
        'rate': None,
        'seq': None,
        'frames': [],
        'extra_chunks': [],  # 기타 청크 보존 (예: 'INAM', 'IART')
    }

    offset = 12
    file_end = 8 + read_u32(data, 4)

    while offset < file_end:
        if offset + 8 > len(data):
            break
        chunk_id = data[offset:offset+4]
        chunk_size = read_u32(data, offset + 4)

        if chunk_id == b'anih':
            result['anih'] = data[offset+8:offset+8+chunk_size]
        elif chunk_id == b'rate':
            n = chunk_size // 4
            result['rate'] = [read_u32(data, offset + 8 + i*4) for i in range(n)]
        elif chunk_id == b'seq ':
            n = chunk_size // 4
            result['seq'] = [read_u32(data, offset + 8 + i*4) for i in range(n)]
        elif chunk_id == b'LIST':
            list_type = data[offset+8:offset+12]
            if list_type == b'fram':
                # 아이콘 프레임 파싱
                foff = offset + 12
                fend = offset + 8 + chunk_size
                while foff < fend:
                    fid = data[foff:foff+4]
                    fsize = read_u32(data, foff + 4)
                    if fid == b'icon':
                        result['frames'].append(data[foff+8:foff+8+fsize])
                    foff += 8 + fsize
                    if fsize % 2:
                        foff += 1
            else:
                # 기타 LIST 청크 보존 (예: LIST/INFO)
                result['extra_chunks'].append(data[offset:offset+8+chunk_size])
        else:
            result['extra_chunks'].append(data[offset:offset+8+chunk_size])

        offset += 8 + chunk_size
        if chunk_size % 2:
            offset += 1

    return result


def parse_anih(anih_data):
    """anih 청크 데이터 파싱."""
    fields = struct.unpack_from('<9I', anih_data, 0)
    return {
        'cbSize': fields[0],
        'nFrames': fields[1],
        'nSteps': fields[2],
        'cx': fields[3],
        'cy': fields[4],
        'cBitCount': fields[5],
        'cPlanes': fields[6],
        'jifRate': fields[7],
        'flags': fields[8],
    }


# ─── ICO 프레임 → RGBA ───────────────────────────────────────────────────────

def ico_frame_to_rgba(ico_data):
    """
    단일 ICO/CUR 프레임(바이트)을 RGBA numpy 배열 + 핫스팟으로 변환.
    1/4/8/24/32bpp BMP 및 PNG 페이로드 처리.
    """
    # ICO 헤더: reserved(2), type(2), count(2)
    img_type = read_u16(ico_data, 2)
    img_count = read_u16(ico_data, 4)

    # 디렉토리 엔트리 (16바이트)
    entry_off = 6
    width = ico_data[entry_off]
    height = ico_data[entry_off + 1]
    if width == 0:
        width = 256
    if height == 0:
        height = 256

    # CUR(type==2): 핫스팟 x, y / ICO(type==1): 색상 평면, 비트 수
    hotx = read_u16(ico_data, entry_off + 4)
    hoty = read_u16(ico_data, entry_off + 6)
    img_size = read_u32(ico_data, entry_off + 8)
    img_offset = read_u32(ico_data, entry_off + 12)

    img_start = img_offset

    # PNG 여부 확인
    if ico_data[img_start:img_start+4] == b'\x89PNG':
        from io import BytesIO
        png_img = Image.open(BytesIO(ico_data[img_start:img_start+img_size]))
        rgba = np.array(png_img.convert('RGBA'))
        return rgba, hotx, hoty, img_type

    # BMP BITMAPINFOHEADER
    bih_size = read_u32(ico_data, img_start)
    bmp_w = read_i32(ico_data, img_start + 4)
    bmp_h = read_i32(ico_data, img_start + 8)
    bpp = read_u16(ico_data, img_start + 14)
    compression = read_u32(ico_data, img_start + 16)
    colors_used = read_u32(ico_data, img_start + 32)

    real_h = abs(bmp_h) // 2  # 높이는 XOR + AND 비트맵 포함

    # 팔레트
    if bpp <= 8:
        num_colors = colors_used if colors_used > 0 else (1 << bpp)
        palette_off = img_start + bih_size
        palette = np.zeros((num_colors, 3), dtype=np.uint8)
        for i in range(num_colors):
            base = palette_off + i * 4
            palette[i] = [ico_data[base+2], ico_data[base+1], ico_data[base]]  # BGR→RGB
    else:
        num_colors = 0
        palette_off = img_start + bih_size
        palette = None

    # 픽셀 데이터
    pixel_off = palette_off + num_colors * 4

    if bpp == 32:
        # 32bpp BGRA — AND 마스크 불필요 (알파 채널이 인라인)
        stride = bmp_w * 4
        rgba = np.zeros((real_h, bmp_w, 4), dtype=np.uint8)
        for y in range(real_h):
            src_y = real_h - 1 - y  # 하→상 순서
            row_off = pixel_off + src_y * stride
            for x in range(bmp_w):
                px = row_off + x * 4
                b, g, r, a = ico_data[px], ico_data[px+1], ico_data[px+2], ico_data[px+3]
                rgba[y, x] = [r, g, b, a]
        return rgba, hotx, hoty, img_type

    elif bpp == 24:
        stride = ((bmp_w * 24 + 31) // 32) * 4
        xor_size = stride * real_h
        and_off = pixel_off + xor_size
        and_stride = ((bmp_w + 31) // 32) * 4

        rgba = np.zeros((real_h, bmp_w, 4), dtype=np.uint8)
        for y in range(real_h):
            src_y = real_h - 1 - y
            for x in range(bmp_w):
                px = pixel_off + src_y * stride + x * 3
                b, g, r = ico_data[px], ico_data[px+1], ico_data[px+2]
                and_byte = ico_data[and_off + src_y * and_stride + x // 8]
                and_bit = (and_byte >> (7 - (x % 8))) & 1
                alpha = 0 if and_bit else 255
                rgba[y, x] = [r, g, b, alpha]
        return rgba, hotx, hoty, img_type

    else:
        # 1, 4, 8 bpp — 팔레트 기반
        stride = ((bmp_w * bpp + 31) // 32) * 4
        xor_size = stride * real_h
        and_off = pixel_off + xor_size
        and_stride = ((bmp_w + 31) // 32) * 4

        rgba = np.zeros((real_h, bmp_w, 4), dtype=np.uint8)
        for y in range(real_h):
            src_y = real_h - 1 - y
            for x in range(bmp_w):
                # 팔레트 인덱스 추출
                if bpp == 8:
                    idx = ico_data[pixel_off + src_y * stride + x]
                elif bpp == 4:
                    byte_val = ico_data[pixel_off + src_y * stride + x // 2]
                    idx = (byte_val >> 4) & 0x0F if (x % 2 == 0) else byte_val & 0x0F
                elif bpp == 1:
                    byte_val = ico_data[pixel_off + src_y * stride + x // 8]
                    idx = (byte_val >> (7 - (x % 8))) & 1
                else:
                    idx = 0

                r, g, b = palette[min(idx, num_colors - 1)]

                and_byte = ico_data[and_off + src_y * and_stride + x // 8]
                and_bit = (and_byte >> (7 - (x % 8))) & 1
                alpha = 0 if and_bit else 255

                rgba[y, x] = [r, g, b, alpha]

        return rgba, hotx, hoty, img_type


# ─── 고품질 리사이즈 ─────────────────────────────────────────────────────────

def resize_rgba(rgba, dst):
    """
    RGBA 이미지를 dst×dst 크기로 고품질 리사이즈.
    업스케일링과 다운스케일링 모두 지원.

    전략:
    1. Premultiplied alpha로 변환 (가장자리 어두운 프린징 방지)
    2. Premultiplied RGB를 Lanczos로 리사이즈
    3. 알파 채널을 Lanczos로 리사이즈 (부드러운 안티앨리어싱 가장자리)
    4. Un-premultiply하여 최종 RGBA 생성
    """
    h, w = rgba.shape[:2]

    rgb = rgba[:, :, :3].astype(np.float64)
    alpha = rgba[:, :, 3].astype(np.float64) / 255.0

    # 프리멀티플라이
    premul = np.zeros_like(rgb)
    for c in range(3):
        premul[:, :, c] = rgb[:, :, c] * alpha

    # Premultiplied RGB를 Lanczos로 리사이즈
    premul_img = Image.fromarray(premul.astype(np.uint8), 'RGB')
    premul_up = np.array(premul_img.resize((dst, dst), Image.LANCZOS)).astype(np.float64)

    # 알파 채널을 Lanczos로 리사이즈
    alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), 'L')
    alpha_up = np.array(alpha_img.resize((dst, dst), Image.LANCZOS)).astype(np.float64) / 255.0

    # 언프리멀티플라이
    result = np.zeros((dst, dst, 4), dtype=np.uint8)
    safe_alpha = np.where(alpha_up > 1.0 / 255.0, alpha_up, 1.0)  # 0 나누기 방지
    for c in range(3):
        unpremul = premul_up[:, :, c] / safe_alpha
        # 알파가 사실상 0이면 색상은 무의미
        unpremul = np.where(alpha_up > 1.0 / 255.0, unpremul, 0)
        result[:, :, c] = np.clip(unpremul, 0, 255).astype(np.uint8)

    result[:, :, 3] = np.clip(alpha_up * 255, 0, 255).astype(np.uint8)

    return result


# ─── RGBA → 32bpp ICO/CUR 프레임 ─────────────────────────────────────────────

def rgba_to_cur_frame(rgba, hotx, hoty):
    """
    RGBA numpy 배열로부터 CUR 형식 프레임(ICO type=2) 생성.
    32bpp BGRA 형식 사용 (팔레트, AND 마스크 불필요 — 알파가 인라인).
    """
    h, w = rgba.shape[:2]

    # BITMAPINFOHEADER (40 bytes)
    bih = struct.pack('<IiiHHIIiiII',
        40,         # biSize
        w,          # biWidth
        h * 2,      # biHeight (doubled for ICO convention, even with 32bpp)
        1,          # biPlanes
        32,         # biBitCount
        0,          # biCompression (BI_RGB)
        0,          # biSizeImage (can be 0 for BI_RGB)
        0,          # biXPelsPerMeter
        0,          # biYPelsPerMeter
        0,          # biClrUsed
        0,          # biClrImportant
    )

    # 픽셀 데이터: BGRA, 하→상 순서
    pixel_data = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = rgba[y, x]
            pixel_data.extend([b, g, r, a])

    # AND 마스크: 32bpp에서는 전부 0 (알파 채널이 투명도 처리)
    # 형식상 필수 — 픽셀당 1비트, DWORD 패딩
    and_stride = ((w + 31) // 32) * 4
    and_mask = bytes(and_stride * h)

    img_data = bih + bytes(pixel_data) + and_mask

    # ICO 디렉토리 엔트리
    w_byte = 0 if w == 256 else w
    h_byte = 0 if h == 256 else h
    img_offset = 6 + 16  # ICO header (6) + 1 directory entry (16)

    ico_header = struct.pack('<HHH', 0, 2, 1)  # reserved, type=CUR, count=1
    ico_entry = struct.pack('<BBBBHHII',
        w_byte,         # width
        h_byte,         # height
        0,              # color count (0 for 32bpp)
        0,              # reserved
        hotx,           # hotspot X
        hoty,           # hotspot Y
        len(img_data),  # image data size
        img_offset,     # offset to image data
    )

    return ico_header + ico_entry + img_data


# ─── ANI 조립 ────────────────────────────────────────────────────────────────

def build_ani(anih_info, frames_data, rate=None, seq=None, extra_chunks=None):
    """구성 요소로부터 완성된 ANI 파일 생성."""
    # anih 청크
    anih_bytes = struct.pack('<9I',
        36,                     # cbSize
        anih_info['nFrames'],
        anih_info['nSteps'],
        0,                      # cx (0 = 프레임 크기 사용)
        0,                      # cy
        0,                      # cBitCount
        0,                      # cPlanes
        anih_info['jifRate'],
        anih_info['flags'],
    )
    anih_chunk = b'anih' + struct.pack('<I', len(anih_bytes)) + anih_bytes

    # LIST/fram 청크
    frame_chunks = bytearray()
    for frame in frames_data:
        frame_chunks += b'icon' + struct.pack('<I', len(frame)) + frame
        if len(frame) % 2:
            frame_chunks += b'\x00'  # RIFF 패딩

    list_data = b'fram' + bytes(frame_chunks)
    list_chunk = b'LIST' + struct.pack('<I', len(list_data)) + list_data

    # rate 청크 (선택)
    rate_chunk = b''
    if rate is not None:
        rate_data = b''.join(struct.pack('<I', r) for r in rate)
        rate_chunk = b'rate' + struct.pack('<I', len(rate_data)) + rate_data

    # seq 청크 (선택)
    seq_chunk = b''
    if seq is not None:
        seq_data = b''.join(struct.pack('<I', s) for s in seq)
        seq_chunk = b'seq ' + struct.pack('<I', len(seq_data)) + seq_data

    # 기타 청크
    extra = b''
    if extra_chunks:
        extra = b''.join(extra_chunks)

    # RIFF 조립
    acon_data = anih_chunk + rate_chunk + seq_chunk + extra + list_chunk
    riff = b'RIFF' + struct.pack('<I', 4 + len(acon_data)) + b'ACON' + acon_data

    return riff


# ─── 메인 ────────────────────────────────────────────────────────────────────

def resize_ani(input_path, output_path, src_size, dst_size):
    """단일 ANI 파일을 src_size에서 dst_size로 리사이즈."""
    with open(input_path, 'rb') as f:
        data = f.read()

    ani = parse_ani(data)
    anih = parse_anih(ani['anih'])

    print(f'  Frames: {anih["nFrames"]}, Steps: {anih["nSteps"]}, '
          f'JifRate: {anih["jifRate"]}, Flags: {anih["flags"]}')

    resized_frames = []

    for i, frame_data in enumerate(ani['frames']):
        rgba, hotx, hoty, img_type = ico_frame_to_rgba(frame_data)
        h, w = rgba.shape[:2]

        # 자동 감지: src_size가 None이면 프레임의 실제 크기 사용
        effective_src = src_size if src_size else w

        if w != effective_src or h != effective_src:
            if src_size is not None:
                print(f'  WARNING: Frame {i} is {w}x{h}, expected {effective_src}x{effective_src}. Skipping.')
                resized_frames.append(frame_data)
                continue
            else:
                effective_src = w  # 실제 크기 사용

        if effective_src == dst_size:
            resized_frames.append(frame_data)
            continue

        # 핫스팟 비례 조정
        scale = dst_size / effective_src
        new_hotx = round(hotx * scale)
        new_hoty = round(hoty * scale)

        # 리사이즈
        resized = resize_rgba(rgba, dst_size)

        # 새 CUR 프레임 생성
        cur_frame = rgba_to_cur_frame(resized, new_hotx, new_hoty)
        resized_frames.append(cur_frame)

        if i == 0 or i == len(ani['frames']) - 1:
            print(f'  Frame {i}: {effective_src}x{effective_src} → {dst_size}x{dst_size}, '
                  f'hotspot ({hotx},{hoty}) → ({new_hotx},{new_hoty})')
        elif i == 1 and len(ani['frames']) > 3:
            print(f'  ... ({len(ani["frames"]) - 2} more frames) ...')

    # 출력 ANI 생성
    output_data = build_ani(anih, resized_frames, ani['rate'], ani['seq'], ani['extra_chunks'])

    with open(output_path, 'wb') as f:
        f.write(output_data)

    print(f'  Output: {output_path} ({len(output_data)} bytes)')


def main():
    parser = argparse.ArgumentParser(
        description='Resize ANI cursor files (e.g. 32→48 or 128→48)'
    )
    parser.add_argument('input', nargs='+', help='Input .ani file(s)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output file or directory')
    parser.add_argument('-s', '--src-size', type=int, default=None,
                        help='Source size (auto-detect if omitted)')
    parser.add_argument('-t', '--target-size', type=int, default=48,
                        help='Target size (default: 48)')
    args = parser.parse_args()

    inputs = args.input
    src = args.src_size
    dst = args.target_size

    src_label = str(src) if src else 'auto'
    print(f'Resize: {src_label}×{src_label} → {dst}×{dst}')

    if len(inputs) == 1 and args.output and not os.path.isdir(args.output):
        # 단일 파일 → 단일 출력
        print(f'Processing: {inputs[0]}')
        resize_ani(inputs[0], args.output, src, dst)
    else:
        # 다중 파일 또는 출력 디렉토리
        out_dir = args.output or '.'
        os.makedirs(out_dir, exist_ok=True)
        for inp in inputs:
            basename = os.path.basename(inp)
            out_path = os.path.join(out_dir, basename)
            print(f'Processing: {inp}')
            resize_ani(inp, out_path, src, dst)

    print('Done!')


if __name__ == '__main__':
    main()
