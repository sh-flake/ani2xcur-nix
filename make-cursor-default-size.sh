#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <ThemeName>"
    echo "Example: $0 Klukai"
    exit 1
fi

THEME_NAME="$1"
THEME_LOWER="$(echo "$THEME_NAME" | tr '[:upper:]' '[:lower:]')"
CURSORS_DIR="$SCRIPT_DIR/Cursors"
OUTPUT_DIR="$SCRIPT_DIR/$THEME_NAME"

echo "=== Making cursor theme: $THEME_NAME (no scaling) ==="

# 1. ANI 파일 복사 (리사이즈 없이)
echo "[1/5] Copying ANI files..."
mkdir -p "$OUTPUT_DIR"
cp "$CURSORS_DIR"/*.ani "$OUTPUT_DIR"/

# 2. install.inf 포맷 변환
echo "[2/5] Converting install.inf..."
python "$SCRIPT_DIR/inf-convert.py" "$CURSORS_DIR/install.inf" "$OUTPUT_DIR/install.inf"

# 3. win2xcurtheme으로 ANI → XCursor 변환
echo "[3/5] Converting to xcursor format..."
mkdir -p "$OUTPUT_DIR/cursors"
win2xcurtheme "$OUTPUT_DIR/install.inf" -o "$OUTPUT_DIR/cursors"

# 4. index.theme 생성
echo "[4/5] Creating index.theme..."
cat > "$OUTPUT_DIR/index.theme" << EOF
[Icon Theme]
Name=$THEME_NAME
Comment=$THEME_NAME cursor theme

EOF

# 5. nix 파일 생성
echo "[5/5] Creating ${THEME_LOWER}-cursor.nix..."
NIX_FILE="$OUTPUT_DIR/${THEME_LOWER}-cursor.nix"
cat > "$NIX_FILE" << EOF
final: prev: {
  ${THEME_LOWER}-cursor = final.stdenvNoCC.mkDerivation {
    pname = "${THEME_LOWER}-cursor";
    version = "1.0.0";

    src = ../../assets/cursors/${THEME_NAME};

    dontBuild = true;

    installPhase = ''
      mkdir -p \$out/share/icons/${THEME_NAME}
      cp -rL \$src/* \$out/share/icons/${THEME_NAME}/
    '';
  };
}
EOF

# 6. 중간 파일 정리
echo "[6/6] Cleaning up intermediate files..."
rm -f "$OUTPUT_DIR"/*.ani "$OUTPUT_DIR"/install.inf

echo "=== Done! Output in: $OUTPUT_DIR ==="