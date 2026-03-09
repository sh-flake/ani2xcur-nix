#!/usr/bin/env python3
"""
inf-convert: 커서 install.inf 파일을 표준 형식으로 변환

Usage:
    inf-convert <input.inf> [output.inf]

    output을 생략하면 standard.inf로 생성됩니다.

변환 규칙:
    1. [Wreg] 섹션 제거
    2. AddReg에서 ,Wreg 참조 제거
    3. rundll32 호출: main.cpl @0,1 → main.cpl,,1
    4. [Scheme.Cur] 파일명 따옴표 제거
    5. [Strings] 정렬을 공백 기반으로 통일 (= 기준 14칸)
    6. [Scheme.Reg]에 HKLM 줄이 없으면 추가
"""

import sys
import re
import os


def parse_sections(lines):
    """INF 파일을 섹션별로 파싱"""
    sections = {}
    current = None
    for line in lines:
        stripped = line.strip()
        m = re.match(r'^\[(.+)\]$', stripped)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def get_strings(sections):
    """[Strings] 섹션에서 key=value 파싱"""
    strings = {}
    if 'Strings' not in sections:
        return strings
    for line in sections['Strings']:
        # key = "value" 또는 key\t\t= "value"
        m = re.match(r'^(\w+)\s*=\s*"?([^"]*)"?\s*$', line.strip())
        if m:
            strings[m.group(1)] = m.group(2)
    return strings


def build_standard(sections, strings):
    """표준 형식의 INF 내용 생성"""
    out = []

    # [Version]
    out.append('[Version]')
    out.append('signature="$CHICAGO$"')
    out.append('')

    # [DefaultInstall] — Wreg 제거
    out.append('[DefaultInstall]')
    out.append('CopyFiles = Scheme.Cur, Scheme.Txt')
    out.append('AddReg    = Scheme.Reg')
    out.append('')

    # [DestinationDirs]
    out.append('[DestinationDirs]')
    out.append('Scheme.Cur = 10,"%CUR_DIR%"')
    out.append('Scheme.Txt = 10,"%CUR_DIR%"')
    out.append('')

    # [Scheme.Reg] — 원본의 HKCU Schemes 줄 유지, HKLM 표준화
    out.append('[Scheme.Reg]')
    hkcu_line = None
    if 'Scheme.Reg' in sections:
        for line in sections['Scheme.Reg']:
            stripped = line.strip()
            if stripped.startswith('HKCU,'):
                hkcu_line = stripped
                break

    if hkcu_line:
        out.append(hkcu_line)
    else:
        # 대체: Strings 기반으로 생성
        cursor_vars = [k for k in strings if k not in ('CUR_DIR', 'SCHEME_NAME')]
        refs = ','.join(f'%10%\\%CUR_DIR%\\%{v}%' for v in cursor_vars)
        out.append(f'HKCU,"Control Panel\\Cursors\\Schemes","%SCHEME_NAME%",,"{refs}"')

    # HKLM 줄 — 항상 표준 형식으로
    out.append('HKLM,"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Runonce\\Setup\\","",,"rundll32.exe shell32.dll,Control_RunDLL main.cpl,,1"')
    out.append('')

    # [Scheme.Cur] — 따옴표 제거
    out.append('[Scheme.Cur]')
    if 'Scheme.Cur' in sections:
        for line in sections['Scheme.Cur']:
            stripped = line.strip()
            if stripped:
                # 따옴표 제거
                cleaned = stripped.strip('"').strip("'")
                out.append(cleaned)
    out.append('')
    out.append('')

    # [Strings] — 공백 정렬 통일
    out.append('[Strings]')
    if 'Strings' in sections:
        # 순서 유지를 위해 원본 순서대로 처리
        keys_ordered = []
        for line in sections['Strings']:
            m = re.match(r'^(\w+)\s*=\s*"?([^"]*)"?\s*$', line.strip())
            if m:
                keys_ordered.append((m.group(1), m.group(2)))

        # 정렬 폭 계산: '=' 위치를 가장 긴 키 + 여유 공백으로
        if keys_ordered:
            max_key_len = max(len(k) for k, _ in keys_ordered)
            pad = max(max_key_len + 1, 14)  # 최소 14칸
            for key, val in keys_ordered:
                out.append(f'{key:<{pad}}= "{val}"')

    out.append('')
    return out


def convert(input_path, output_path):
    """INF 파일 변환 실행"""
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        raw = f.read()

    # CRLF 통일
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    lines = raw.split('\n')

    sections = parse_sections(lines)
    strings = get_strings(sections)
    result = build_standard(sections, strings)

    with open(output_path, 'wb') as f:
        f.write('\r\n'.join(result).encode('utf-8'))

    return True


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print("Usage: inf-convert <input.inf> [output.inf]")
        print()
        print("커서 install.inf 파일을 표준 형식으로 변환합니다.")
        print("output을 생략하면 standard.inf로 생성됩니다.")
        sys.exit(0)

    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"Error: '{input_path}' 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = 'standard.inf'

    try:
        convert(input_path, output_path)
        print(f"✓ 변환 완료: {input_path} → {output_path}")
    except Exception as e:
        print(f"Error: 변환 중 오류 발생 - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
