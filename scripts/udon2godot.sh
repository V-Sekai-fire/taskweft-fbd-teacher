#!/usr/bin/env bash
# Translate UdonSharp C# to SafeGDScript with the pinned udon2godot build, inside WSL.
#   udon2godot.sh <out dir (WSL path)> <file.cs or dir (WSL paths)>...
out="$1"; shift
cd /mnt/c/fabric-starforged/3-interactor/udon2godot || exit 1
exec ./target/release/udon2godot -q -o "$out" "$@"
