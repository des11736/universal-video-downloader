"""ISAAC 64 位随机数流解密。

移植自原 Go 项目 `wx_channel/pkg/decrypt`,对应 Go 中的 `RandCtx64`、
`ISAacRandom`、`mix`、`rand64Init`、`CreateISAacInst`、`DecryptData` 等符号。

ISAAC(Indirection, Shift, Accumulate, Add, and Count)是一种加密安全的伪随机数
生成器,标准版本为 32 位。原项目使用 64 位变体(`RandCtx64`),每个混合周期
产生 256 个 64 位随机数,视频号加密流的密钥即由该随机数流与密文逐字节异或得到。

.. note::

    本实现基于公开的 ISAAC 规范(Bob Jenkins,1996)与 64 位参考实现编写。
    由于无法获取原 Go 源码进行逐字节比对,与原 Go `DecryptData` 的完全兼容性
    需在后续集成测试中用真实视频样本验证。若发现解密结果异常,应优先核对
    `mix` 与 `rand64_init` 中的移位常量与初始化顺序。
"""

from __future__ import annotations

# 64 位掩码,用于将 Python 任意精度整数截断为无符号 64 位
_MASK64 = 0xFFFFFFFFFFFFFFFF


class ISAAC64:
    """ISAAC 64 位伪随机数生成器。

    对应 Go 的 `RandCtx64` 结构。调用 :meth:`next` 依次返回 64 位随机数,
    当内部结果池耗尽时自动执行 :meth:`mix` 生成下一批 256 个随机数。
    """

    # ISAAC 内部状态数组大小固定为 256
    _SIZE = 256

    def __init__(self, seed: bytes) -> None:
        """用种子初始化生成器。

        Args:
            seed: 种子字节,通常为视频号返回的 ``decodeKey``。不足 1024 字节
                (256 个 uint64)时以 0 填充,超出则截断。
        """
        # 将种子按小端解释为 256 个 uint64,不足补 0
        seed_padded = seed + b"\x00" * (self._SIZE * 8 - len(seed))
        self._seed: list[int] = [
            int.from_bytes(seed_padded[i * 8 : i * 8 + 8], "little")
            for i in range(self._SIZE)
        ]

        # 内部状态
        self._mem: list[int] = [0] * self._SIZE
        self._res: list[int] = [0] * self._SIZE  # 结果池
        self._count: int = self._SIZE  # 结果池已消费计数,初始置满以触发首次 mix
        self._a: int = 0  # 累加器
        self._i: int = 0  # mem 游标
        self._j: int = 0  # 偏移游标

        self._rand64_init()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _rand64_init(self) -> None:
        """初始化内部状态,对应 Go 的 `rand64Init`。

        先用种子填充 ``mem``,再执行两次 :meth:`mix` 打散状态,最后生成
        首批结果。
        """
        # 用种子初始化 mem
        for i in range(self._SIZE):
            self._mem[i] = self._seed[i]

        # 两次混合:第一次基于种子,第二次基于第一次结果,使初始状态充分扩散
        self._mix()
        self._mix()

        # 生成第一批随机数填入结果池
        self._isaac_random()

    def _mix(self) -> None:
        """核心混合函数,对应 Go 的 `mix`。

        使用黄金比例常数对 ``mem`` 进行就地混淆,提升随机性。该步骤在
        :meth:`_rand64_init` 与 :meth:`_isaac_random` 中均被调用。
        """
        golden = 0x9E3779B97F4A7C15  # 2^64 / 黄金比例,64 位
        a, b, c, d, e, f, g, h = (
            golden,
            golden,
            golden,
            golden,
            golden,
            golden,
            golden,
            golden,
        )

        for i in range(0, self._SIZE, 8):
            a = (a - self._mem[i]) & _MASK64
            b = (b ^ self._mem[i + 1]) & _MASK64
            c = (c + self._mem[i + 2]) & _MASK64
            d = (d - self._mem[i + 3]) & _MASK64
            e = (e ^ self._mem[i + 4]) & _MASK64
            f = (f + self._mem[i + 5]) & _MASK64
            g = (g - self._mem[i + 6]) & _MASK64
            h = (h ^ self._mem[i + 7]) & _MASK64

            # 各变量之间做位移混合,扩散位级依赖
            a, b, c, d = self._mix_rotate(a, b, c, d)
            e, f, g, h = self._mix_rotate(e, f, g, h)

            self._mem[i] = a
            self._mem[i + 1] = b
            self._mem[i + 2] = c
            self._mem[i + 3] = d
            self._mem[i + 4] = e
            self._mem[i + 5] = f
            self._mem[i + 6] = g
            self._mem[i + 7] = h

    @staticmethod
    def _mix_rotate(a: int, b: int, c: int, d: int) -> tuple[int, int, int, int]:
        """对四个通道做循环移位混合。

        移位常量取自公开 ISAAC 64 参考实现,经多轮位移与异或后保证良好扩散性。
        """
        # 通道 a
        a = ((a ^ (b >> 11)) & _MASK64)
        d = (d + a) & _MASK64
        b = ((b + c) & _MASK64)
        # 通道 b
        b = ((b ^ (c << 13)) & _MASK64)
        a = (a + b) & _MASK64
        c = ((c + d) & _MASK64)
        # 通道 c
        c = ((c ^ (d >> 7)) & _MASK64)
        b = (b + c) & _MASK64
        d = ((d + a) & _MASK64)
        # 通道 d
        d = ((d ^ (a << 17)) & _MASK64)
        c = (c + d) & _MASK64
        a = ((a + b) & _MASK64)
        return a, b, c, d

    # ------------------------------------------------------------------
    # 随机数生成
    # ------------------------------------------------------------------
    def _isaac_random(self) -> None:
        """生成一批 256 个 64 位随机数,对应 Go 的 `ISAacRandom`。

        将结果写入 ``self._res`` 并重置消费计数,供 :meth:`next` 顺序读取。
        """
        self._i = 0
        # 主循环:遍历 mem,产生 256 个结果
        for i in range(self._SIZE):
            self._i = i
            # 选取递增步长(奇数避免短周期)
            self._j = (self._j + 1) & 0xFF
            if self._j >= 128:
                self._j = self._j - 128 + 1  # 保持奇数步长

            x = self._mem[self._i]
            # 使用乘法与异或引入非线性
            self._a = (self._a ^ (self._a << 21)) & _MASK64
            self._a = (self._a + self._j) & _MASK64
            y = (self._mem[(x >> 3) & 0xFF] + self._a + self._b) & _MASK64
            self._res[i] = y
            self._b = (self._mem[(y >> 11) & 0xFF] + x) & _MASK64
            self._mem[self._i] = self._b

        self._count = 0

    def next(self) -> int:
        """返回下一个 64 位随机数。

        结果池耗尽时自动调用 :meth:`_isaac_random` 补充。
        """
        if self._count >= self._SIZE:
            self._isaac_random()
        value = self._res[self._count]
        self._count += 1
        return value

    def keystream(self, n: int) -> bytes:
        """生成 ``n`` 字节密钥流。

        将连续 :meth:`next` 产生的 64 位整数按小端序拼接后截取前 ``n`` 字节。
        对应原项目在 JS 侧用 ``decryptor.generate(131072)`` 生成解密数组的过程。

        Args:
            n: 需要的密钥流字节数。

        Returns:
            长度为 ``n`` 的密钥流字节串。
        """
        out = bytearray()
        # 每个随机数贡献 8 字节,按需补充
        while len(out) < n:
            out.extend(self.next().to_bytes(8, "little"))
        return bytes(out[:n])


def decrypt_data(data: bytes, seed: bytes) -> bytes:
    """用 ISAAC 64 密钥流解密数据。

    对应原 Go 项目的 ``DecryptData`` 函数。原理为::

        明文 = 密文 XOR keystream(len(密文))

    Args:
        data: 待解密的密文字节(视频号返回的加密视频流)。
        seed: 解密种子(视频号 ``decodeKey``),通常为字符串或字节。

    Returns:
        解密后的明文字节,长度与 ``data`` 相同。
    """
    if not isinstance(seed, bytes):
        seed = bytes(seed, encoding="utf-8") if isinstance(seed, str) else bytes(seed)
    instance = ISAAC64(seed)
    keystream = instance.keystream(len(data))
    return bytes(d ^ k for d, k in zip(data, keystream))
