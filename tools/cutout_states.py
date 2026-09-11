# -*- coding: utf-8 -*-
"""
宠物立绘抠图工具（离线构建脚本，不参与程序运行）

把原始素材（白底 + 对话气泡 + UI 浮层的立绘）批量处理成
assets/states/*.png —— 透明背景、只有角色的表情图。

处理流程：
  1. 从四边泛洪吃掉白底（保护角色内部同样是白色的围裙/头饰）
  2. 从气泡内部种子点泛洪清掉气泡，再膨胀几像素吞掉描边环
  3. 按颜色擦除深色 UI 面板，断开它与角色的粘连
  4. 连通域分析，只保留最大的那个（也就是角色本体）
  5. 按 alpha 包围盒裁掉四周留白

用法：
    pip install pillow numpy scipy
    python tools/cutout_states.py [素材目录]

素材目录默认为 SRC_DEFAULT，输出固定写入 assets/states/。
想新增表情：把图放进素材目录，在 JOBS 里加一行（文件名前缀 -> 状态名），
必要时用 EXTRA 补种子点/裁剪框/擦除色。

依赖：pillow、numpy、scipy
"""
import sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from PIL import Image
from collections import deque
from scipy import ndimage

# 原始素材目录（可按需修改，或运行时用命令行参数覆盖）
SRC_DEFAULT = r'E:\毕业设计\shuchaiku'
# 输出目录：项目根下的 assets/states/
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'assets', 'states')

TOL_MIN, TOL_SAT = 225, 18      # 近白判定：最暗通道≥225 且 饱和度低


def near_white(a):
    r, g, b = (a[:, :, i].astype(np.int16) for i in range(3))
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    return (mn >= TOL_MIN) & ((mx - mn) <= TOL_SAT)


def flood_from(a, mask, seeds):
    """从种子点四连通泛洪近白像素，写入 mask"""
    h, w = mask.shape
    wi = near_white(a)
    dq = deque()
    for x, y in seeds:
        if 0 <= x < w and 0 <= y < h and wi[y, x] and not mask[y, x]:
            mask[y, x] = True
            dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and wi[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True
                dq.append((nx, ny))


def erase_color(a, rgb, tol, y_max=None):
    """按颜色擦除整块纯色浮层（如深色 UI 面板）"""
    d = np.abs(a[:, :, :3].astype(np.int16) - np.array(rgb, np.int16))
    m = (d <= np.array(tol, np.int16)).all(axis=2)
    if y_max is not None:
        m[y_max:] = False
    return m


def cutout(path, seeds=(), crop=None, keep_ratio=0.5, dilate=6,
           erase_rgb=None, erase_tol=(12, 12, 14), erase_y_max=None):
    img = Image.open(path).convert('RGBA')
    if crop:
        img = img.crop(crop)
        seeds = [(x - crop[0], y - crop[1]) for x, y in seeds]
    a = np.array(img)
    h, w = a.shape[:2]

    bg = np.zeros((h, w), bool)
    # 0) 纯色浮层（深色 UI 面板）直接按颜色抹掉，断开它与角色的粘连
    if erase_rgb is not None:
        panel = erase_color(a, erase_rgb, erase_tol, erase_y_max)
        bg |= ndimage.binary_dilation(panel, iterations=2)
    # 1) 从四边泛洪，吃掉外部背景
    flood_from(a, bg, [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
                      + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    # 2) 从气泡内部种子点泛洪（深色描边会挡住，不会溢到角色身上）
    if seeds:
        inner = np.zeros((h, w), bool)
        flood_from(a, inner, seeds)
        if dilate:
            # 膨胀几像素吞掉气泡描边；描边和角色粘连处只会留下肉眼不可见的小缺口
            inner = ndimage.binary_dilation(inner, iterations=dilate)
        bg |= inner

    fg = ~bg
    # 3) 连通域：只保留主体，丢弃气泡残壳/文字/音符等浮层
    lab, k = ndimage.label(fg, structure=np.ones((3, 3)))
    if k > 1:
        sizes = ndimage.sum(fg, lab, range(1, k + 1))
        biggest = sizes.max()
        drop = [i + 1 for i, s in enumerate(sizes) if s < biggest * keep_ratio]
        fg[np.isin(lab, drop)] = False

    a[:, :, 3] = np.where(fg, 255, 0)
    out = Image.fromarray(a, 'RGBA')
    # 4) 按 alpha 包围盒裁掉留白
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


# 素材文件名前缀 -> 状态名（输出 assets/states/<状态名>.png）
JOBS = {
    '1537bf84': 'greet',     # 举手打招呼
    '784df595': 'alert',     # 晕乎乎吐舌 -> 高负载
    '786ec64b': 'status',    # 半月眼嫌弃   -> 系统状态
    'a8419c92': 'chat',      # 眨眼俏皮     -> 对话
    'e1be2a88': 'idle',      # 眯眼微笑     -> 待机
    'f0419451': 'weather',   # 惊讶摊手     -> 天气
    'f31fce78': 'happy',     # 闭眼唱歌     -> 开心
}

# 每张图的额外参数：(种子点, 裁剪框)
PARAMS = {
    '784df595': (((200, 240), (145, 335), (185, 365)), None),
    '786ec64b': (((200, 240), (145, 335), (185, 365)), None),
    'a8419c92': (((600, 560), (300, 510)), None),
    'f31fce78': ((), (272, 232, 700, 720)),
}

# 深色 UI 面板按颜色擦除（面板 RGB(28,32,41) 与头发 RGB(82,104,167) 区分明显）
EXTRA = {'f31fce78': dict(erase_rgb=(28, 32, 41), erase_y_max=330)}


def main(src_dir: str):
    files = {os.path.basename(f)[:8]: f for f in glob.glob(os.path.join(src_dir, '*.png'))}
    if not files:
        print(f'素材目录里没有 PNG: {src_dir}')
        return 1
    os.makedirs(OUT, exist_ok=True)
    ok = 0
    for prefix, state in JOBS.items():
        if prefix not in files:
            print(f'  [跳过] {prefix} -> {state}（素材缺失）')
            continue
        seeds, crop = PARAMS.get(prefix, ((), None))
        out = cutout(files[prefix], seeds, crop, **EXTRA.get(prefix, {}))
        dest = os.path.join(OUT, f'{state}.png')
        out.save(dest)
        print(f'  {state:8} <- {prefix}  {out.width}x{out.height}  {dest}')
        ok += 1
    print(f'\n完成，共生成 {ok} 张到 {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else SRC_DEFAULT))
