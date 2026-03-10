# ani2xcur-nix

Windows ANI 커서 테마를 Linux XCursor 형식으로 변환하고, NixOS overlay로 패키징하는 도구 모음입니다. [_BLZ_](https://ko-fi.com/blz_404/shop)의 커스텀 커서 테마를 NixOS에서 사용하기 위해 만들어졌습니다.

## 개요

기본적으로 32x32 크기의 ANI 파일을 48x48로 리사이즈하고, `win2xcurtheme`과 호환되도록 `install.inf`를 표준화한 뒤, XCursor 변환 및 Nix overlay 파일 생성까지 자동으로 수행합니다.

## 파이프라인

```
Cursors/*.ani + install.inf
        │
        ├─ [1] ani-scale-{lanczos,nearest}.py  ANI 프레임 리사이즈 (32→48)
        ├─ [2] inf-convert.py                  install.inf 표준화
        ├─ [3] win2xcurtheme      ANI → XCursor 변환 (win2xcur 패키지)
        ├─ [4] index.theme 생성
        └─ [5] Nix overlay 파일 생성
```

## 요구사항

- Python 3 + `Pillow`, `numpy`
- [`win2xcur`](https://github.com/quantum5/win2xcur) (`win2xcurtheme` 명령어 포함)

### 설치

```bash
pip install win2xcur
```

Nix 사용자는 `nix develop`로 Python 의존성(`Pillow`, `numpy`)을 자동으로 설정할 수 있습니다. `win2xcur`는 별도로 설치해야 합니다.

## 사용법

### 빠른 시작

1. `Cursors/` 디렉토리에 Windows 커서 파일(`.ani` + `install.inf`)을 넣습니다.
2. 테마 이름을 지정하여 스크립트를 실행합니다:

```bash
./make-cursor.sh <ThemeName> [lanczos|nearest]
```

예시:

```bash
./make-cursor.sh Klukai            # 기본값: lanczos
./make-cursor.sh Klukai nearest    # nearest neighbor 사용
```

#### 스케일링 방식 비교

| 방식 | 장점 | 단점 |
|------|------|------|
| **lanczos** (기본값) | 부드러운 가장자리, 고품질 안티앨리어싱 | 주변에 점 같은 유령 픽셀이 소수 남을 수 있음 |
| **nearest** | 유령 픽셀 없음, 선명한 원본 픽셀 유지 | 비정수 배율에서 약간의 불균일/계단 현상 |

> **유령 픽셀 조절 (`_cleanup_alpha`)**
>
> `ani-scale-lanczos.py`에는 리사이즈 후 알파 채널을 정리하는 `_cleanup_alpha(result, alpha_low=85, alpha_high=170)` 함수가 있습니다. 원본 커서는 대부분 binary alpha(0 또는 255)이므로, Lanczos 보간으로 생긴 극단적 반투명 값을 다음과 같이 정리합니다:
>
> - `alpha < alpha_low` → 0으로 변환 (유령 픽셀 제거)
> - `alpha > alpha_high` → 255로 변환 (거의 불투명한 픽셀 확정)
> - 중간값은 유지 (자연스러운 안티앨리어싱 가장자리)
>
> 이 값을 조절하면 가장자리 렌더링을 커서 테마에 맞게 미세 조정할 수 있습니다:
>
> | 조절 | 효과 |
> |------|------|
> | `alpha_low` ↑ (예: 85→120) | 유령 픽셀이 더 공격적으로 제거되지만, 안티앨리어싱 가장자리가 거칠어질 수 있음 |
> | `alpha_low` ↓ (예: 85→40) | 더 부드러운 가장자리를 유지하지만, 유령 픽셀이 남을 수 있음 |
> | `alpha_high` ↓ (예: 170→130) | 반투명 가장자리가 줄어들어 더 선명해지지만 거칠어질 수 있음 |
> | `alpha_high` ↑ (예: 170→210) | 더 부드러운 불투명 전환, 가장자리에 약간의 반투명 띠가 남을 수 있음 |

3. `<ThemeName>/` 디렉토리에 변환된 결과가 생성됩니다:
   - `cursors/` — XCursor 파일들
   - `index.theme` — 커서 테마 메타데이터
   - `<themename>-cursor.nix` — NixOS overlay 파일

### 개별 도구 사용

`install.inf`가 이미 `win2xcurtheme`과 호환되는 표준 형식이거나, 리사이즈 크기를 다르게 지정하고 싶다면 아래 스크립트를 개별적으로 사용할 수 있습니다.

#### ANI 리사이즈

두 가지 스케일링 방식을 제공합니다:

- **`ani-scale-lanczos.py`** — Premultiplied alpha + Lanczos 리샘플링. 부드러운 가장자리와 고품질 안티앨리어싱을 제공하지만, 주변에 점 같은 유령 픽셀이 소수 남을 수 있습니다.
- **`ani-scale-nearest.py`** — Nearest Neighbor 리샘플링. 보간 없이 원본 픽셀을 그대로 매핑하여 유령 픽셀이 없지만, 비정수 배율에서 약간의 불균일/계단 현상이 나타날 수 있습니다.

```bash
# Lanczos (부드러운 가장자리)
python ani-scale-lanczos.py input.ani -o output.ani -s 32 -t 48

# Nearest Neighbor (선명한 픽셀)
python ani-scale-nearest.py input.ani -o output.ani -s 32 -t 48

# 배치 처리
python ani-scale-lanczos.py *.ani -o output_dir/ -s 32 -t 48

# 소스 크기 자동 감지
python ani-scale-lanczos.py input.ani -o output.ani -t 48
```

| 옵션 | 설명 |
|------|------|
| `-s`, `--src-size` | 원본 크기 (생략 시 자동 감지) |
| `-t`, `--target-size` | 대상 크기 (기본값: 48) |
| `-o`, `--output` | 출력 파일 또는 디렉토리 |

#### INF 변환 (`inf-convert.py`)

Windows 커서 `install.inf`의 형식이 `win2xcurtheme`과 호환되지 않는 경우, 표준 형식으로 변환합니다.

```bash
python inf-convert.py input.inf output.inf
```

변환 규칙:
- `[Wreg]` 섹션 제거
- `rundll32` 호출 형식 표준화
- 파일명 따옴표 제거
- `[Strings]` 섹션 정렬 통일
- 누락된 HKLM 레지스트리 항목 자동 추가

## NixOS에서 사용하기

생성된 Nix 파일을 overlay로 사용할 수 있습니다:

```nix
# flake.nix 또는 configuration.nix에서
overlays = [
  (import ./path/to/<themename>-cursor.nix)
];

# 커서 테마 적용
home.pointerCursor = {
  name = "<ThemeName>";
  package = pkgs.<themename>-cursor;
};
```

## 라이선스

이 도구 모음은 [MIT License](LICENSE)로 배포됩니다. 커서 테마의 저작권은 원작자 [_BLZ_](https://ko-fi.com/blz_404/shop)에게 있습니다.
