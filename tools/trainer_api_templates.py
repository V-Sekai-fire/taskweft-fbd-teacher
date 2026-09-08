"""The trainer family: the microduck-shaped training surface (mjlab's task terms, the
command and action configs, the randomisation events) as CALL blocks over
`sigs/mjlab_trainer.sigs`, scored by the config the trainer would run.

A row is a configuration program: each CALL sets one term of the G1 flat velocity
task. `trainer_cfg_runner.py` (in mjlab_motionbricks, run in WSL) applies the calls to
a fresh task config and reads the term table back from the config objects; the effect
check compares that table to the numbers the intent names. rank3 carries a wrong
number, rank5 a signature outside the table. Two entries have no row, by name in
`UNCOVERED`: the microduck BAM and backlash actuator models have no mjlab actuator
class in this environment yet.
"""
from __future__ import annotations

import random
import re

from react_templates import ReactRow

EPS = 1e-6

UNCOVERED = {
    "Actuator.bam": "no BAM actuator class in the mjlab environment yet (microduck's FrictionDRBamActuator)",
    "Actuator.backlash": "no backlash actuator class in the mjlab environment yet",
}


def _f(x: float) -> str:
    s = f"{x:.4f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _close(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= max(EPS, 1e-4 * abs(float(b)))
    except (TypeError, ValueError):
        return False


def call(_blk: str, _sig: str, _target: str, _en: str | None, **args: str) -> str:
    pins = ([f"EN={_en}"] if _en else []) + [f"TARGET={_target}"] + [f'{k}="{v}"' for k, v in args.items()]
    return f"{_blk} = CALL[{_sig}](" + ", ".join(pins) + ")"


def prog(pid: str, steps: list[tuple]) -> str:
    lines = [f"program {pid}", "var done : BOOL"]
    prev = None
    for name, sig, args in steps:
        target = sig.split(".")[0].lower()
        lines.append(call(name, sig, f'"{target}"', f"{prev}.ENO" if prev else None, **args))
        prev = name
    lines.append(f"done = {prev}.ENO")
    return "\n".join(lines) + "\n"


def refuse(text: str) -> str:
    """rank5: a term the table does not have."""
    return re.sub(r"CALL\[[A-Za-z]+\.[A-Za-z_]+\]", "CALL[Reward.jump_height]", text, count=1)


def _get(table: dict, *path):
    cur = table
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


# ---- templates ---------------------------------------------------------------

def t_tracking(seed: int) -> ReactRow:
    rng = random.Random(seed)
    wl, wa = round(rng.uniform(0.5, 4.0), 2), round(rng.uniform(0.5, 4.0), 2)
    sl, sa = rng.choice([0.25, 0.5, 0.7071, 1.0]), rng.choice([0.25, 0.5, 0.7071, 1.0])

    def p(w: float) -> str:
        return prog("tracking", [
            ("a", "Reward.track_linear_velocity", {"weight": _f(w), "std": _f(sl)}),
            ("b", "Reward.track_angular_velocity", {"weight": _f(wa), "std": _f(sa)}),
        ])

    def expect(t: dict) -> bool:
        return (_close(_get(t, "rewards", "track_linear_velocity", "weight"), wl)
                and _close(_get(t, "rewards", "track_linear_velocity", "std"), sl)
                and _close(_get(t, "rewards", "track_angular_velocity", "weight"), wa)
                and _close(_get(t, "rewards", "track_angular_velocity", "std"), sa))

    frames = [f"reward linear velocity tracking at weight {_f(wl)} with std {_f(sl)} and angular at {_f(wa)} with std {_f(sa)}",
              f"track the twist command: linear weight {_f(wl)} (std {_f(sl)}), angular weight {_f(wa)} (std {_f(sa)})",
              f"velocity tracking rewards: lin {_f(wl)}/{_f(sl)}, ang {_f(wa)}/{_f(sa)}"]
    fid = seed % len(frames)
    return ReactRow("trainer_tracking", seed, frames[fid], p(wl), p(round(wl + 0.5, 2)), refuse(p(wl)), [], expect, fid, host="trainer")


def t_gait(seed: int) -> ReactRow:
    rng = random.Random(seed)
    wa, wc, ws, wp, wl = (round(rng.uniform(-1.0, 2.0), 2) for _ in range(5))
    hc, hs = round(rng.uniform(0.05, 0.2), 3), round(rng.uniform(0.05, 0.2), 3)

    def p(h: float) -> str:
        return prog("gait", [
            ("a", "Reward.air_time", {"weight": _f(wa)}),
            ("c", "Reward.foot_clearance", {"weight": _f(wc), "target_height": _f(h)}),
            ("s", "Reward.foot_swing_height", {"weight": _f(ws), "target_height": _f(hs)}),
            ("p", "Reward.foot_slip", {"weight": _f(wp)}),
            ("l", "Reward.soft_landing", {"weight": _f(wl)}),
        ])

    def expect(t: dict) -> bool:
        r = t.get("rewards", {})
        return (_close(_get(r, "air_time", "weight"), wa) and _close(_get(r, "foot_clearance", "weight"), wc)
                and _close(_get(r, "foot_clearance", "target_height"), hc)
                and _close(_get(r, "foot_swing_height", "weight"), ws) and _close(_get(r, "foot_swing_height", "target_height"), hs)
                and _close(_get(r, "foot_slip", "weight"), wp) and _close(_get(r, "soft_landing", "weight"), wl))

    frames = [f"gait shaping: air time {_f(wa)}, foot clearance {_f(wc)} toward {_f(hc)} m, swing height {_f(ws)} toward {_f(hs)} m, slip {_f(wp)}, soft landing {_f(wl)}",
              f"set the five foot rewards: air_time {_f(wa)}; clearance {_f(wc)} at {_f(hc)}; swing {_f(ws)} at {_f(hs)}; slip {_f(wp)}; landing {_f(wl)}",
              f"feet: reward air time {_f(wa)}, clearance {_f(wc)} (target {_f(hc)}), swing height {_f(ws)} (target {_f(hs)}), penalise slip {_f(wp)}, soft landing {_f(wl)}"]
    fid = seed % len(frames)
    return ReactRow("trainer_gait", seed, frames[fid], p(hc), p(round(hc + 0.05, 3)), refuse(p(hc)), [], expect, fid, host="trainer")


def t_regularisers(seed: int) -> ReactRow:
    rng = random.Random(seed)
    wr, wb, wm, wd, wc = (round(rng.uniform(-2.0, 0.0), 3) for _ in range(5))
    wu, wp = round(rng.uniform(0.2, 2.0), 2), round(rng.uniform(0.2, 2.0), 2)
    su = rng.choice([0.3, 0.4472, 0.6])
    ft = rng.choice([50.0, 100.0, 200.0])

    def p(w: float) -> str:
        return prog("regularisers", [
            ("r", "Reward.action_rate_l2", {"weight": _f(w)}),
            ("b", "Reward.body_ang_vel", {"weight": _f(wb)}),
            ("m", "Reward.angular_momentum", {"weight": _f(wm)}),
            ("d", "Reward.dof_pos_limits", {"weight": _f(wd)}),
            ("c", "Reward.self_collisions", {"weight": _f(wc), "force_threshold": _f(ft)}),
            ("u", "Reward.upright", {"weight": _f(wu), "std": _f(su)}),
            ("p", "Reward.pose", {"weight": _f(wp)}),
        ])

    def expect(t: dict) -> bool:
        r = t.get("rewards", {})
        return (_close(_get(r, "action_rate_l2", "weight"), wr) and _close(_get(r, "body_ang_vel", "weight"), wb)
                and _close(_get(r, "angular_momentum", "weight"), wm) and _close(_get(r, "dof_pos_limits", "weight"), wd)
                and _close(_get(r, "self_collisions", "weight"), wc) and _close(_get(r, "self_collisions", "force_threshold"), ft)
                and _close(_get(r, "upright", "weight"), wu) and _close(_get(r, "upright", "std"), su)
                and _close(_get(r, "pose", "weight"), wp))

    frames = [f"regularise: action rate {_f(wr)}, body angular velocity {_f(wb)}, angular momentum {_f(wm)}, joint limits {_f(wd)}, self-collision {_f(wc)} above {_f(ft)} N; upright {_f(wu)} (std {_f(su)}), pose {_f(wp)}",
              f"penalties {_f(wr)} action rate, {_f(wb)} body ang vel, {_f(wm)} momentum, {_f(wd)} dof limits, {_f(wc)} self collisions at {_f(ft)} N; upright {_f(wu)}/{_f(su)}; pose {_f(wp)}",
              f"the seven shaping terms: rate {_f(wr)}, ang vel {_f(wb)}, momentum {_f(wm)}, limits {_f(wd)}, collisions {_f(wc)} (threshold {_f(ft)}), upright {_f(wu)} std {_f(su)}, pose {_f(wp)}"]
    fid = seed % len(frames)
    return ReactRow("trainer_regularisers", seed, frames[fid], p(wr), p(round(wr - 0.25, 3)), refuse(p(wr)), [], expect, fid, host="trainer")


def t_rom(seed: int) -> ReactRow:
    rng = random.Random(seed)
    w = round(rng.uniform(-2.0, -0.1), 2)

    def p(x: float) -> str:
        return prog("rom", [
            ("r", "Reward.rom_penalty", {"weight": _f(x)}),
            ("c", "Metric.rom_clearance", {}),
            ("m", "Metric.mean_action_acc", {}),
        ])

    def expect(t: dict) -> bool:
        return (_close(_get(t, "rewards", "rom_penalty", "weight"), w)
                and "rom_clearance" in t.get("metrics", []) and "mean_action_acc" in t.get("metrics", []))

    frames = [f"penalise leaving the range-of-motion envelope at weight {_f(w)}, and log the ROM clearance and mean action acceleration",
              f"rom_penalty {_f(w)}; keep the rom_clearance and mean_action_acc metrics",
              f"the E.3 envelope: penalty weight {_f(w)}, clearance metric on, action acceleration metric on"]
    fid = seed % len(frames)
    return ReactRow("trainer_rom", seed, frames[fid], p(w), p(round(w - 0.3, 2)), refuse(p(w)), [], expect, fid, host="trainer")


OBS = ["base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel"]


def t_observation_noise(seed: int) -> ReactRow:
    rng = random.Random(seed)
    noise = {o: rng.choice([0.0, 0.01, 0.02, 0.05, 0.1, 0.2]) for o in OBS}
    first = OBS[seed % len(OBS)]

    def p(n0: float) -> str:
        steps = []
        for i, o in enumerate(OBS):
            steps.append((f"o{i}", f"Observation.{o}", {"noise": _f(n0 if o == first else noise[o])}))
        steps += [("a", "Observation.actions", {}), ("c", "Observation.command", {})]
        return prog("observation_noise", steps)

    def expect(t: dict) -> bool:
        obs = t.get("observations", {})
        return (all(_close(_get(obs, o, "noise"), noise[o]) for o in OBS)
                and "actions" in obs and "command" in obs)

    desc = ", ".join(f"{o} {_f(noise[o])}" for o in OBS)
    frames = [f"observation noise: {desc}; keep the last action and the command in the observation",
              f"set uniform noise on the actor observation: {desc}; actions and command stay",
              f"noise per observation term ({desc}) with the action and command terms present"]
    fid = seed % len(frames)
    wrong = 0.3 if noise[first] != 0.3 else 0.15
    return ReactRow("trainer_observation_noise", seed, frames[fid], p(noise[first]), p(wrong), refuse(p(noise[first])), [], expect, fid, host="trainer")


def t_terminations(seed: int) -> ReactRow:
    rng = random.Random(seed)
    deg = rng.choice([45.0, 60.0, 70.0, 80.0, 90.0])

    def p(d: float) -> str:
        return prog("terminations", [
            ("t", "Termination.time_out", {}),
            ("f", "Termination.fell_over", {"limit_deg": _f(d)}),
        ])

    def expect(t: dict) -> bool:
        return "time_out" in t.get("terminations", {}) and _close(_get(t, "terminations", "fell_over", "limit_deg"), deg)

    frames = [f"end an episode on time-out or when the torso tilts past {_f(deg)} degrees",
              f"terminations: time_out, and fell_over at {_f(deg)} deg",
              f"the robot has fallen at {_f(deg)} degrees of tilt; time-outs end episodes too"]
    fid = seed % len(frames)
    return ReactRow("trainer_terminations", seed, frames[fid], p(deg), p(deg + 5.0), refuse(p(deg)), [], expect, fid, host="trainer")


def t_action(seed: int) -> ReactRow:
    rng = random.Random(seed)
    scale = rng.choice([0.25, 0.3, 0.4, 0.5, 0.75])
    off = rng.choice([True, False])

    def p(s: float) -> str:
        return prog("action", [
            ("a", "Action.joint_pos", {"scale": _f(s), "use_default_offset": "TRUE" if off else "FALSE"}),
        ])

    def expect(t: dict) -> bool:
        return _close(_get(t, "actions", "joint_pos", "scale"), scale) and _get(t, "actions", "joint_pos", "use_default_offset") is off

    frames = [f"joint position actions scaled by {_f(scale)}, {'offset from the default pose' if off else 'absolute, no default offset'}",
              f"action scale {_f(scale)}, use_default_offset {'on' if off else 'off'}",
              f"the policy's outputs are joint targets at scale {_f(scale)} {'around the default pose' if off else 'with no offset'}"]
    fid = seed % len(frames)
    return ReactRow("trainer_action", seed, frames[fid], p(scale), p(round(scale + 0.1, 2)), refuse(p(scale)), [], expect, fid, host="trainer")


def t_command(seed: int) -> ReactRow:
    rng = random.Random(seed)
    vx = round(rng.uniform(0.5, 2.0), 2)
    vy = round(rng.uniform(0.2, 1.0), 2)
    wz = round(rng.uniform(0.3, 1.5), 2)
    back = rng.choice([True, False])

    def p(x: float) -> str:
        return prog("command", [
            ("c", "Command.twist", {"lin_vel_x_min": _f(-x if back else 0.0), "lin_vel_x_max": _f(x),
                                    "lin_vel_y_min": _f(-vy), "lin_vel_y_max": _f(vy),
                                    "ang_vel_z_min": _f(-wz), "ang_vel_z_max": _f(wz)}),
        ])

    def expect(t: dict) -> bool:
        c = _get(t, "commands", "twist") or {}
        lx, ly, az = c.get("lin_vel_x", [None, None]), c.get("lin_vel_y", [None, None]), c.get("ang_vel_z", [None, None])
        return (_close(lx[0], -vx if back else 0.0) and _close(lx[1], vx) and _close(ly[0], -vy) and _close(ly[1], vy)
                and _close(az[0], -wz) and _close(az[1], wz))

    frames = [f"command forward speeds up to {_f(vx)} m/s{' and backward as far' if back else ', never backward'}, lateral to {_f(vy)}, turning to {_f(wz)} rad/s",
              f"twist ranges: x [{_f(-vx if back else 0.0)}, {_f(vx)}], y [{_f(-vy)}, {_f(vy)}], yaw [{_f(-wz)}, {_f(wz)}]",
              f"sample velocity commands within {_f(vx)} m/s forward{' or backward' if back else ''}, {_f(vy)} sideways and {_f(wz)} rad/s of yaw"]
    fid = seed % len(frames)
    return ReactRow("trainer_command", seed, frames[fid], p(vx), p(round(vx + 0.5, 2)), refuse(p(vx)), [], expect, fid, host="trainer")


def t_sim_rate(seed: int) -> ReactRow:
    rng = random.Random(seed)
    ts, dec = rng.choice([(0.005, 4), (0.005, 2), (0.004, 5), (0.002, 10), (0.01, 2)])
    length = rng.choice([10.0, 15.0, 20.0, 30.0])

    def p(d: int) -> str:
        return prog("sim_rate", [
            ("c", "Sim.control", {"timestep": _f(ts), "decimation": str(d)}),
            ("e", "Sim.episode", {"length_s": _f(length)}),
        ])

    hz = 1.0 / (ts * dec)

    def expect(t: dict) -> bool:
        s = t.get("sim", {})
        return (_close(s.get("timestep"), ts) and s.get("decimation") == dec and _close(s.get("control_hz"), hz)
                and _close(s.get("episode_length_s"), length))

    frames = [f"a {_f(ts * 1000)} ms physics step with decimation {dec} ({_f(hz)} Hz control) and {_f(length)} s episodes",
              f"sim: timestep {_f(ts)}, decimation {dec}, episode length {_f(length)} s",
              f"control at {_f(hz)} Hz from a {_f(ts)} s step over {dec} substeps; episodes last {_f(length)} seconds"]
    fid = seed % len(frames)
    return ReactRow("trainer_sim_rate", seed, frames[fid], p(dec), p(dec + 1), refuse(p(dec)), [], expect, fid, host="trainer")


def t_scene(seed: int) -> ReactRow:
    rng = random.Random(seed)
    n = rng.choice([16, 64, 256, 512, 1024, 2048, 4096])

    def p(k: int) -> str:
        return prog("scene", [("s", "Scene.num_envs", {"n": str(k)})])

    def expect(t: dict) -> bool:
        return _get(t, "scene", "num_envs") == n

    frames = [f"simulate {n} environments in parallel", f"num_envs {n}", f"a scene of {n} robots"]
    fid = seed % len(frames)
    return ReactRow("trainer_scene", seed, frames[fid], p(n), p(n * 2), refuse(p(n)), [], expect, fid, host="trainer")


def t_randomisation(seed: int) -> ReactRow:
    rng = random.Random(seed)
    fmin, fmax = round(rng.uniform(0.2, 0.6), 2), round(rng.uniform(0.8, 1.5), 2)
    bias = rng.choice([0.005, 0.01, 0.015, 0.02, 0.03])
    cx, cy, cz = (rng.choice([0.01, 0.02, 0.025, 0.03, 0.05]) for _ in range(3))

    def p(fm: float) -> str:
        return prog("randomisation", [
            ("f", "Event.foot_friction", {"min": _f(fm), "max": _f(fmax)}),
            ("e", "Event.encoder_bias", {"min": _f(-bias), "max": _f(bias)}),
            ("c", "Event.base_com", {"x": _f(cx), "y": _f(cy), "z": _f(cz)}),
        ])

    def expect(t: dict) -> bool:
        ev = t.get("events", {})
        return (_close(_get(ev, "foot_friction", "min"), fmin) and _close(_get(ev, "foot_friction", "max"), fmax)
                and _close(_get(ev, "encoder_bias", "min"), -bias) and _close(_get(ev, "encoder_bias", "max"), bias)
                and _close(_get(ev, "base_com", "x"), cx) and _close(_get(ev, "base_com", "y"), cy) and _close(_get(ev, "base_com", "z"), cz))

    frames = [f"randomise foot friction between {_f(fmin)} and {_f(fmax)}, encoder bias within {_f(bias)} rad, and the base centre of mass by up to ({_f(cx)}, {_f(cy)}, {_f(cz)}) m",
              f"domain randomisation: friction [{_f(fmin)}, {_f(fmax)}], encoder bias +-{_f(bias)}, COM offsets {_f(cx)}/{_f(cy)}/{_f(cz)}",
              f"at startup draw friction in [{_f(fmin)}, {_f(fmax)}], joint encoder bias in +-{_f(bias)}, and shift the base COM within +-({_f(cx)}, {_f(cy)}, {_f(cz)})"]
    fid = seed % len(frames)
    return ReactRow("trainer_randomisation", seed, frames[fid], p(fmin), p(round(fmin + 0.1, 2)), refuse(p(fmin)), [], expect, fid, host="trainer")


def t_push(seed: int) -> ReactRow:
    rng = random.Random(seed)
    a, b = rng.choice([(1.0, 3.0), (2.0, 5.0), (0.5, 2.0), (3.0, 8.0)])
    vel = rng.choice([0.3, 0.5, 0.8, 1.0])

    def p(v: float) -> str:
        return prog("push", [
            ("p", "Event.push_robot", {"interval_min_s": _f(a), "interval_max_s": _f(b), "vel": _f(v)}),
        ])

    def expect(t: dict) -> bool:
        e = _get(t, "events", "push_robot") or {}
        return _close(e.get("interval_min_s"), a) and _close(e.get("interval_max_s"), b) and _close(e.get("vel"), vel)

    frames = [f"shove the robot every {_f(a)} to {_f(b)} seconds with up to {_f(vel)} m/s of velocity",
              f"push_robot: interval [{_f(a)}, {_f(b)}] s, velocity {_f(vel)}",
              f"random pushes of {_f(vel)} m/s between {_f(a)} and {_f(b)} seconds apart"]
    fid = seed % len(frames)
    return ReactRow("trainer_push", seed, frames[fid], p(vel), p(round(vel + 0.2, 2)), refuse(p(vel)), [], expect, fid, host="trainer")


def t_actuator_pd(seed: int) -> ReactRow:
    rng = random.Random(seed)
    kp = rng.choice([20.0, 30.0, 40.0, 60.0, 80.0])
    kd = rng.choice([1.0, 1.5, 2.0, 3.0, 4.0])
    lim = rng.choice([25.0, 50.0, 88.0, 139.0])

    def p(k: float) -> str:
        return prog("actuator_pd", [
            ("a", "Actuator.pd", {"stiffness": _f(k), "damping": _f(kd), "effort_limit": _f(lim)}),
        ])

    def expect(t: dict) -> bool:
        pd = _get(t, "actuators", "pd") or {}
        return (all(_close(v, kp) for v in pd.get("stiffness", [])) and all(_close(v, kd) for v in pd.get("damping", []))
                and all(_close(v, lim) for v in pd.get("effort_limit", [])) and len(pd.get("stiffness", [])) > 0)

    frames = [f"drive every joint with a PD actuator of stiffness {_f(kp)}, damping {_f(kd)} and an effort limit of {_f(lim)} N m",
              f"PD actuators: kp {_f(kp)}, kd {_f(kd)}, torque limit {_f(lim)}",
              f"uniform PD gains {_f(kp)}/{_f(kd)} on all actuators, clamped at {_f(lim)} N m"]
    fid = seed % len(frames)
    return ReactRow("trainer_actuator_pd", seed, frames[fid], p(kp), p(kp + 10.0), refuse(p(kp)), [], expect, fid, host="trainer")


TRAINER_TEMPLATES = {
    "trainer_actuator_pd": t_actuator_pd,
    "trainer_tracking": t_tracking,
    "trainer_gait": t_gait,
    "trainer_regularisers": t_regularisers,
    "trainer_rom": t_rom,
    "trainer_observation_noise": t_observation_noise,
    "trainer_terminations": t_terminations,
    "trainer_action": t_action,
    "trainer_command": t_command,
    "trainer_sim_rate": t_sim_rate,
    "trainer_scene": t_scene,
    "trainer_randomisation": t_randomisation,
    "trainer_push": t_push,
}


def trainer_row_for(template_id: str, seed: int) -> ReactRow:
    return TRAINER_TEMPLATES[template_id](seed)


def signatures_of(text: str) -> list[str]:
    return re.findall(r"CALL\[([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\]", text)


if __name__ == "__main__":
    import sys
    seen: set[str] = set()
    for tid, fn in TRAINER_TEMPLATES.items():
        row = fn(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
        seen |= set(signatures_of(row.rank1))
        print(tid, "|", row.intent)
    print(len(seen), "signature(s) covered")
