"""`isaac_decrypt.py` 的单元测试。

覆盖 ISAAC64 伪随机数生成器的确定性、不同种子区分性、64 位输出范围,
以及 `decrypt_data` 的 XOR 对合(自反)特性与空输入处理。
"""

from __future__ import annotations

import pytest

from universal_video_downloader.platforms.wechat_channels.isaac_decrypt import (
    ISAAC64,
    decrypt_data,
)


def test_isaac64_initial_state_deterministic() -> None:
    """相同种子初始化的两个实例,前 5 次 next() 输出序列应完全一致。"""
    seed = bytes([1, 2, 3, 4])
    instance_a = ISAAC64(seed)
    instance_b = ISAAC64(seed)

    # 各取 5 个随机数
    seq_a = [instance_a.next() for _ in range(5)]
    seq_b = [instance_b.next() for _ in range(5)]

    # 序列应完全相等(确定性)
    assert seq_a == seq_b
    # 每个值都应为 int 类型
    assert all(isinstance(v, int) for v in seq_a)
    # 每个值都应落在 64 位无符号范围内
    assert all(0 <= v < 2**64 for v in seq_a)


def test_isaac64_different_seeds_different_output() -> None:
    """不同种子初始化的实例,首次 next() 输出应不同。"""
    instance_a = ISAAC64(bytes([1, 2, 3]))
    instance_b = ISAAC64(bytes([4, 5, 6]))

    assert instance_a.next() != instance_b.next()


def test_decrypt_data_round_trip() -> None:
    """XOR 为对合操作,对密文再次解密应还原明文。"""
    data = b"hello world, this is a test message for isaac xor decrypt"
    seed = bytes(range(32))

    # 第一次解密(实际为加密)
    encrypted = decrypt_data(data, seed)
    # 对密文再次执行同样操作应回到原明文
    decrypted = decrypt_data(encrypted, seed)

    assert decrypted == data


def test_decrypt_data_empty_input() -> None:
    """空输入应返回空字节串,且不触发密钥流生成。"""
    assert decrypt_data(b"", bytes([1, 2, 3])) == b""


def test_isaac64_keystream_length() -> None:
    """keystream(n) 应返回长度为 n 的 bytes 对象。"""
    instance = ISAAC64(bytes([10, 20, 30]))
    stream = instance.keystream(100)

    assert isinstance(stream, bytes)
    assert len(stream) == 100


def test_isaac64_64bit_range() -> None:
    """多次 next() 的返回值应始终落在 [0, 2**64) 区间内。

    验证 64 位掩码生效、无溢出或负值。调用 300 次以跨越结果池(256 个)
    重新生成的边界,覆盖 `_isaac_random` 的二次填充路径。
    """
    instance = ISAAC64(bytes(range(8)))
    for _ in range(300):
        value = instance.next()
        assert 0 <= value < 2**64
