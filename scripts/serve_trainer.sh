#!/usr/bin/env bash
# The trainer config runner as a line server, run inside WSL by the writer.
export PATH="$HOME/.pixi/bin:$PATH"
cd /mnt/c/fabric-starforged/3-interactor/motion-bricks-cpp/mujoco || exit 1
exec pixi run -e default python -m mjlab_motionbricks.trainer_cfg_runner --serve
