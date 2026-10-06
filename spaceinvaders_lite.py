"""spaceinvaders-lite: 迷你太空入侵者克隆 + 自动演示。纯标准库。"""

from __future__ import annotations

import argparse
import random
import sys

W, H = 40, 22
PLAYER_Y = H - 2
INV_ROWS, INV_COLS = 4, 8
SHOOT_EVERY = 12  # 自动演示里玩家开火间隔（帧）
INV_SHOOT_P = 0.02  # 每帧每个入侵者向下开火概率


class Game:
    """可测试的核心状态机。坐标 (x, y)，y 向下递增。"""

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.w, self.h = W, H
        self.player_x = W // 2
        self.lives = 3
        self.score = 0
        self.kills = 0
        self.frame = 0
        self.over = False
        self.win = False
        # 入侵者：set of (x, y)
        self.invaders = set()
        for r in range(INV_ROWS):
            for c in range(INV_COLS):
                self.invaders.add((3 + c * 4, 2 + r * 2))
        self.inv_dx = 1  # 横向移动方向
        self.bullets = []  # [x, y, dy] 玩家 dy=-1，入侵者 dy=+1
        self.shields = set()  # (x, y)
        for sx in (6, 16, 26, 36):
            for ox, oy in ((0, 0), (1, 0), (2, 0), (0, 1), (2, 1)):
                self.shields.add((sx + ox, PLAYER_Y - 4 + oy))

    def _player_bullet(self):
        return [self.player_x, PLAYER_Y - 1, -1]

    def player_shoot(self):
        if not any(dy < 0 for _, _, dy in self.bullets):
            self.bullets.append(self._player_bullet())

    def move_player(self, dx):
        self.player_x = max(0, min(self.w - 1, self.player_x + dx))

    def _cadence(self):
        """入侵者移动节拍：数量越少越快（致敬原版的加速机制）"""
        n = len(self.invaders)
        return 3 if n > 20 else (2 if n > 10 else 1)

    def _move_invaders(self):
        if not self.invaders:
            return
        if self.frame % self._cadence() != 0:
            return
        xs = [x for x, _ in self.invaders]
        hit_edge = (self.inv_dx > 0 and max(xs) >= self.w - 1) or \
                   (self.inv_dx < 0 and min(xs) <= 0)
        if hit_edge:
            self.inv_dx *= -1
            self.invaders = {(x, y + 1) for x, y in self.invaders}
        else:
            self.invaders = {(x + self.inv_dx, y) for x, y in self.invaders}
        # 入侵者到底线 = 游戏结束
        if any(y >= PLAYER_Y for _, y in self.invaders):
            self.over = True

    def _invader_shoot(self):
        # 经典规则：每列只有最底下的入侵者会开火
        bottom = {}
        for x, y in self.invaders:
            if x not in bottom or y > bottom[x]:
                bottom[x] = y
        for x, y in bottom.items():
            if self.rng.random() < INV_SHOOT_P:
                self.bullets.append([x, y + 1, 1])

    def step(self):
        """推进一帧。"""
        if self.over:
            return
        self.frame += 1
        self._move_invaders()
        if self.over:
            return
        self._invader_shoot()
        new_bullets = []
        for x, y, dy in self.bullets:
            y += dy
            if y < 0 or y >= self.h:
                continue
            # 护盾挡子弹
            if (x, y) in self.shields:
                self.shields.discard((x, y))
                continue
            if dy < 0:
                if (x, y) in self.invaders:
                    self.invaders.discard((x, y))
                    self.kills += 1
                    self.score += 10
                    continue
            else:
                if y == PLAYER_Y and x == self.player_x:
                    self.lives -= 1
                    if self.lives <= 0:
                        self.over = True
                    continue
            new_bullets.append([x, y, dy])
        self.bullets = new_bullets
        if not self.invaders:
            self.win = True
            self.over = True

    def render(self):
        grid = [[" "] * self.w for _ in range(self.h)]
        for x, y in self.shields:
            if 0 <= y < self.h:
                grid[y][x] = "#"
        for x, y in self.invaders:
            if 0 <= y < self.h:
                grid[y][x] = "V"
        for x, y, dy in self.bullets:
            if 0 <= y < self.h:
                grid[y][x] = "|" if dy < 0 else "!"
        grid[PLAYER_Y][self.player_x] = "^"
        return "\n".join("".join(row) for row in grid)


def _intercept(g, ix, iy, horizon=40):
    """前向模拟阵型（含节拍、碰边反转+下沉），找出子弹拦截点。

    返回 (t, px)：现在从 px 开火，t 帧后子弹与目标在 (px, 19-t) 相遇。
    找不到时返回 None。
    """
    dx = g.inv_dx
    cad = g._cadence()
    min_x = min(x for x, _ in g.invaders)
    max_x = max(x for x, _ in g.invaders)
    tx, ty = ix, iy
    for t in range(1, horizon + 1):
        if (g.frame + t) % cad == 0:
            if (dx > 0 and max_x >= g.w - 1) or (dx < 0 and min_x <= 0):
                dx *= -1
                ty += 1
            else:
                tx += dx
                min_x += dx
                max_x += dx
        if ty == (PLAYER_Y - 1) - t:
            return t, tx
    return None


def auto_play(seed=None, frames=600, verbose=False):
    g = Game(seed)
    target = None  # 粘性目标：锁定一个入侵者直到它被击杀
    while not g.over and g.frame < frames:
        if target not in g.invaders:
            target = min(g.invaders, key=lambda p: (-p[1], abs(p[0] - g.player_x))) \
                if g.invaders else None
        # 1) 躲子弹：2 帧内会打中才躲
        dodge = 0
        for bx, by, dy in g.bullets:
            if dy > 0 and bx == g.player_x and 0 < PLAYER_Y - by <= 2:
                dodge = -1 if g.player_x > 0 else 1
                break
        if dodge:
            g.move_player(dodge)
        elif target is not None:
            # 2) 拦截点瞄准：算出"现在从 px 开火能命中"的 px，对齐就开火
            #    （player_shoot 自带"单发在膛"限速，无需额外门控）
            hit = _intercept(g, *target)
            px = hit[1] if hit else target[0]
            if px < g.player_x:
                g.move_player(-1)
            elif px > g.player_x:
                g.move_player(1)
            else:
                g.player_shoot()
        g.step()
        if verbose and g.frame % 100 == 0:
            print(g.render())
            print(f"帧 {g.frame}  击杀 {g.kills}  得分 {g.score}  生命 {g.lives}\n")
    status = "胜利" if g.win else ("失败" if g.over else "超时")
    print(f"自动演示结束：{status}，击杀 {g.kills}，得分 {g.score}，生命 {g.lives}，帧数 {g.frame}")
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="spaceinvaders-lite：迷你太空入侵者")
    ap.add_argument("--auto", action="store_true", help="自动演示")
    ap.add_argument("--frames", type=int, default=600, help="演示帧数上限")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="演示时打印画面")
    args = ap.parse_args(argv)

    if args.auto:
        auto_play(seed=args.seed, frames=args.frames, verbose=args.verbose)
        return 0

    # 简单回合制交互：每行输入 l/r/空格/q
    g = Game(args.seed)
    print("操作：l 左移 / r 右移 / s 射击 / q 退出，每行一个命令。")
    print(g.render())
    try:
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == "q":
                break
            elif cmd == "l":
                g.move_player(-1)
            elif cmd == "r":
                g.move_player(1)
            elif cmd == "s":
                g.player_shoot()
            else:
                print("未知命令（l/r/s/q）")
                continue
            g.step()
            print(g.render())
            print(f"得分 {g.score}  生命 {g.lives}  剩余入侵者 {len(g.invaders)}")
            if g.over:
                print("胜利！" if g.win else "游戏结束。")
                break
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
