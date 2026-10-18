#!/usr/bin/env bash
# 为当前用户安装 QSerialTool 桌面入口与图标（Linux）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSET="$ROOT/src/qserialtool/ui/assets/qserialtool.png"
TEMPLATE="$ROOT/packaging/qserialtool.desktop.in"

usage() {
  echo "用法: $0 [--uninstall] [QSerialTool 路径]" >&2
  echo "  默认使用 $ROOT/dist/QSerialTool" >&2
  exit 2
}

UNINSTALL=0
BINARY=""
for argument in "$@"; do
  case "$argument" in
    --uninstall)
      UNINSTALL=1
      ;;
    -h | --help)
      usage
      ;;
    -*)
      usage
      ;;
    *)
      BINARY="$argument"
      ;;
  esac
done

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"
DESKTOP_FILE="$DESKTOP_DIR/qserialtool.desktop"
ICON_FILE="$ICON_DIR/qserialtool.png"

if [[ "$UNINSTALL" -eq 1 ]]; then
  rm -f "$DESKTOP_FILE" "$ICON_FILE"
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null || true
  fi
  echo "已卸载：$DESKTOP_FILE"
  echo "已卸载：$ICON_FILE"
  exit 0
fi

BINARY="${BINARY:-$ROOT/dist/QSerialTool}"
if [[ ! -x "$BINARY" ]]; then
  echo "可执行文件不存在或无执行权限：$BINARY" >&2
  exit 1
fi
BINARY="$(readlink -f "$BINARY")"

if [[ ! -f "$ASSET" ]]; then
  echo "缺少图标资源：$ASSET" >&2
  exit 1
fi
if [[ ! -f "$TEMPLATE" ]]; then
  echo "缺少桌面入口模板：$TEMPLATE" >&2
  exit 1
fi

mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
install -m 644 "$ASSET" "$ICON_FILE"
sed "s|@EXEC@|$BINARY|g" "$TEMPLATE" > "$DESKTOP_FILE"
chmod 644 "$DESKTOP_FILE"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null || true
fi

echo "已安装：$DESKTOP_FILE"
echo "已安装：$ICON_FILE"
echo "如桌面环境未刷新，可重新登录或重启文件管理器。"
